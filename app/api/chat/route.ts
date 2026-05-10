import {
    convertToModelMessages,
    createUIMessageStream,
    createUIMessageStreamResponse,
    generateObject,
    streamText,
    type UIMessage,
} from "ai"
import { z } from "zod"
import {
    type ClientOverrides,
    getAIModel,
} from "@/lib/ai-providers"
import {
    buildClarificationPrompt,
    buildFallbackClarificationText,
    buildReadinessStatusText,
    type ClarifyLanguage,
    type GenerationRoute,
    evaluateClarificationNeed,
    mergeSlotSnapshots,
} from "@/lib/bim/clarification-loop"
import {
    type NexusArchitectProgressSnapshot,
    runNexusArchitectAdapter,
    type NexusArchitectAdapterOutput,
} from "@/lib/bim/forge-architect-adapter"
import { validateFileParts } from "@/lib/chat-helpers"
import {
    checkAndIncrementRequest,
    isQuotaEnabled,
} from "@/lib/dynamo-quota-manager"
import {
    setTraceInput,
    setTraceOutput,
} from "@/lib/langfuse"
import { getSystemPrompt } from "@/lib/system-prompts"
import { getUserIdFromRequest } from "@/lib/user-id"

export const maxDuration = 120

function buildClarificationOverrides(
    req: Request,
    mainOverrides: ClientOverrides,
): ClientOverrides {
    const clarifyProvider = req.headers.get("x-clarify-provider")
    const clarifyBaseUrl = req.headers.get("x-clarify-base-url")
    const clarifyApiKey = req.headers.get("x-clarify-api-key")
    const clarifyModel = req.headers.get("x-clarify-model")
    const clarifyVertexApiKey = req.headers.get("x-clarify-vertex-api-key")

    const finalProvider = clarifyProvider || "ollama"
    const finalModel = clarifyModel || "qwen2.5-coder:7b-instruct-q4_K_M"
    const finalBaseUrl = clarifyBaseUrl || "http://127.0.0.1:11434"

    return {
        ...mainOverrides,
        provider: finalProvider,
        baseUrl: finalBaseUrl,
        apiKey: clarifyApiKey || (finalProvider === "ollama" ? "ollama" : mainOverrides.apiKey),
        modelId: finalModel,
        vertexApiKey: clarifyVertexApiKey || mainOverrides.vertexApiKey,
    }
}

interface ChatTextPart {
    type: "text"
    text?: string
}

interface MinimalChatMessage {
    role: string
    parts?: Array<{ type: string; text?: string } | ChatTextPart>
}

type ChatMessage = UIMessage | MinimalChatMessage

function getConversationUserText(messages: ChatMessage[]): string {
    return messages
        .filter((m) => m.role === "user")
        .map((m) => {
            const textPart = m.parts?.find(
                (p): p is ChatTextPart => p.type === "text",
            )
            return typeof textPart?.text === "string" ? textPart.text : ""
        })
        .filter(Boolean)
        .join("\n\n")
}

function getVerboseWebLogsEnabled(): boolean {
    return process.env.OPENBIMFORGE_VERBOSE_WEB_LOGS === "1"
}

function summarizeExecutionLog(text: string): string | null {
    const closedMatch = text.match(/<execution-log>([\s\S]*?)<\/execution-log>/)
    const openMatch = closedMatch || text.match(/<execution-log>([\s\S]*)$/)
    if (!openMatch) return null

    try {
        let jsonText = openMatch[1].trim()
        if (!closedMatch) {
            const lastBrace = jsonText.lastIndexOf("}")
            if (lastBrace < 0) return null
            jsonText = jsonText.slice(0, lastBrace + 1)
        }
        const payload = JSON.parse(jsonText)
        const stages = Array.isArray(payload.stages) ? payload.stages : []
        const lastStage = stages.at(-1)
        const stageLabel = lastStage
            ? `${lastStage.status || "unknown"}:${lastStage.name || lastStage.id || "stage"}`
            : "no-stage"
        return [
            `status=${payload.status || "unknown"}`,
            `mode=${payload.mode || "unknown"}`,
            `stages=${stages.length}`,
            `last=${stageLabel}`,
            `summary=${payload.summary || "n/a"}`,
        ].join(" | ")
    } catch {
        return null
    }
}

function mirrorConsoleBlock(prefix: string, text: string): void {
    const normalized = text.replace(/\r/g, "\n").trim()
    if (!normalized) return
    const verbose = getVerboseWebLogsEnabled()

    if (!verbose) {
        if (prefix.endsWith("-LLM]")) return
        if (prefix === "[Nexus-Web-Progress]") {
            const summary = summarizeExecutionLog(normalized)
            if (summary) console.log(`${prefix} ${summary}`)
            return
        }
        if (prefix === "[Nexus-Web-Final]") {
            console.log(`${prefix} emitted ${normalized.length} chars to chat UI`)
            return
        }
    }

    for (const line of normalized.split("\n")) {
        const outputLine = line.trimEnd()
        if (!outputLine) {
            console.log(prefix)
            continue
        }
        for (let index = 0; index < outputLine.length; index += 1800) {
            console.log(`${prefix} ${outputLine.slice(index, index + 1800)}`)
        }
    }
}

function isNexusContinuationIntent(userInputText: string): boolean {
    const normalized = userInputText.toLowerCase()
    return /确认|继续|直接交付|全链路|实时|日志|合成|生成|执行|交付|导出|下载|ifc|web-?gl|confirm|continue|run|execute|deliver|export|logs/.test(normalized)
}

function hasNexusConversationContext(conversationText: string): boolean {
    return /nexus|bim|ifc|vectorworks|transit-payload|constructor|architect|web-?gl|建筑|办公|层高|面积|楼层|模型|构筑|合成/i.test(conversationText)
}

function shouldForceNexusSynthesis(userInputText: string, conversationText: string): boolean {
    return isNexusContinuationIntent(userInputText) && hasNexusConversationContext(conversationText)
}

function hasForgeVisionFormContext(text: string): boolean {
    return /ForgeVision(?:Layout)?Constraints|forgevision-(?:form|layout)|cadVectorPath|stlPaths|previewPaths|layoutTopologyPath|forgeVisionLayoutConstraints/i.test(text)
}

function extractForgeVisionComplexityScore(text: string): number {
    const patterns = [
        /"complexity_score"\s*:\s*(\d+)/i,
        /complexity score:\s*(\d+)\s*\/\s*100/i,
    ]
    for (const pattern of patterns) {
        const match = text.match(pattern)
        if (!match) continue
        const score = Number(match[1])
        if (Number.isFinite(score)) return Math.max(0, Math.min(100, Math.round(score)))
    }
    return 92
}

function buildForgeVisionReadinessText(baseText: string, complexityScore: number, language: ClarifyLanguage, sourceText = ""): string {
    const isLayout = /ForgeVisionLayoutConstraints|forgevision-layout|layoutTopologyPath|forgeVisionLayoutConstraints/i.test(sourceText)
    const modeLine = isLayout
        ? language === "en"
            ? `Readiness score: ${Math.max(complexityScore, 85)}/100. ForgeVision-Layout spatial topology is loaded; layout-guided BIM workflow is enabled.`
            : `需求整备完成度：${Math.max(complexityScore, 85)}/100。ForgeVision-Layout 空间拓扑已载入，系统将进入布局驱动 BIM 工作流。`
        : complexityScore > 10
        ? language === "en"
            ? `Readiness score: ${complexityScore}/100. High-precision vector features detected; CAD-First construction workflow is enabled.`
            : `需求整备完成度：${complexityScore}/100。检测到高精度矢量特征，系统已自动切换至 [CAD-First] 构筑工作流。`
        : language === "en"
            ? `Readiness score: ${complexityScore}/100. ForgeVision-Form massing reference is loaded; standard visual-BIM workflow is enabled.`
            : `需求整备完成度：${complexityScore}/100。ForgeVision-Form 形体参考已载入，系统将进入标准图生 BIM 工作流。`
    return `${modeLine}\n${baseText}`
}

function buildForgeVisionSlotSnapshot(text: string): Record<string, string> {
    const snapshot: Record<string, string> = {}
    if (/\b(office|办公|写字楼)\b/i.test(text)) snapshot.building_type = "office"
    else if (/\b(residential|住宅|公寓)\b/i.test(text)) snapshot.building_type = "residential"
    else snapshot.building_type = "image-guided building"

    const floorMatch = text.match(/(\d+(?:\.\d+)?)\s*(?:层|楼|floors?|storeys?)/i)
    if (floorMatch) snapshot.storey_count = floorMatch[1]

    const areaMatch = text.match(/(\d+(?:\.\d+)?)\s*(?:㎡|m2|m²|square meters?)/i)
    if (areaMatch) snapshot.target_area = `${areaMatch[1]} m2`

    const heightMatch = text.match(/(?:层高|floor height|storey height)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:m|米|meters?)/i)
    snapshot.floor_height = heightMatch ? `${heightMatch[1]} m` : "3.6 m"
    return snapshot
}

function buildPlainTextStreamResponse(text: string): Response {
    const textId = `plain-text-${Date.now()}`
    const stream = createUIMessageStream({
        execute: ({ writer }) => {
            writer.write({ type: "start" })
            writer.write({ type: "text-start", id: textId })
            writer.write({ type: "text-delta", id: textId, delta: text })
            writer.write({ type: "text-end", id: textId })
            writer.write({ type: "finish" })
        },
    })

    return createUIMessageStreamResponse({ stream })
}

function buildStatusPrefixedStreamResponse(
    statusText: string,
    result: ReturnType<typeof streamText>,
): Response {
    const textId = `bim-status-${Date.now()}`
    const stream = createUIMessageStream({
        execute: ({ writer }) => {
            writer.write({ type: "start" })
            writer.write({ type: "text-start", id: textId })
            const prefixedStatusText = `[Nexus-Orchestrator] Orchestration engine warming up...\n\n${statusText}\n\n`
            mirrorConsoleBlock("[Nexus-Web-Status]", prefixedStatusText)
            writer.write({
                type: "text-delta",
                id: textId,
                delta: prefixedStatusText,
            })
            writer.write({ type: "text-end", id: textId })
            writer.write({ type: "finish" })
            writer.merge(result.toUIMessageStream({ sendReasoning: true }))
        },
    })

    return createUIMessageStreamResponse({ stream })
}

function buildNexusSynthesisResultText(
    _statusText: string,
    architectResult: NexusArchitectAdapterOutput,
    language: ClarifyLanguage,
): string {
    const live = (architectResult.raw?.live || {}) as Record<string, unknown>
    const diagnostics = (architectResult.diagnostics || {}) as Record<string, unknown>
    const stageEvents = Array.isArray(live.stage_events) ? live.stage_events : []
    const isWaitingForVm = stageEvents.some((stage) => {
        const item = stage as Record<string, unknown>
        return item.id === "nexus_execute" && ["waiting", "running"].includes(String(item.status))
    })
    const executionLog = buildExecutionLogBlock(language, isWaitingForVm ? "running" : "success", live, diagnostics)
    const summary = isWaitingForVm
        ? language === "en"
            ? "Nexus payload is ready. Waiting for Vectorworks VM to execute the final construction step."
            : "Nexus \u8f7d\u8377\u5df2\u4ea4\u4ed8\uff0c\u6b63\u5728\u7b49\u5f85 Vectorworks VM \u6267\u884c\u6700\u540e\u7684\u7269\u7406\u6784\u7b51\u9636\u6bb5\u3002"
        : language === "en"
            ? "Nexus pipeline completed. All stages finished successfully."
            : "Nexus \u534f\u540c\u7f16\u6392\u5b8c\u6210\uff0c\u6240\u6709\u9636\u6bb5\u5df2\u6210\u529f\u6267\u884c\u3002"
    return [executionLog, summary].filter(Boolean).join("\n\n")
}

function buildNexusOrchestrationFailureText(
    statusText: string,
    architectResult: NexusArchitectAdapterOutput,
    language: ClarifyLanguage,
): string {
    const diagnostics = (architectResult.diagnostics || {}) as Record<string, unknown>
    const live = (architectResult.raw?.live || {}) as Record<string, unknown>
    const heading = language === "en" ? "Nexus Orchestration reached execution phase, but synthesis failed." : "Nexus \u5df2\u8fdb\u5165\u7f16\u6392\u9636\u6bb5\uff0c\u4f46\u6784\u9020\u5408\u6210\u5931\u8d25\u3002"
    const errorLabel = language === "en" ? "Disruption details" : "\u4e2d\u65ad\u8be6\u60c5"
    const errorText = String(diagnostics.live_error || diagnostics.fatal_error || "").trim() || (language === "en" ? "Unknown Nexus-Framework runtime disruption." : "\u672a\u77e5\u7684 Nexus \u8fd0\u884c\u65f6\u4e2d\u65ad\u3002")

    const executionLog = buildExecutionLogBlock(language, "failed", live, diagnostics)
    const sections = [statusText, heading, executionLog, `${errorLabel}:\n${errorText}`].filter(Boolean)
    return sections.join("\n\n")
}

function buildExecutionLogBlock(
    language: ClarifyLanguage,
    status: "success" | "failed" | "running",
    live: Record<string, unknown>,
    diagnostics: Record<string, unknown>,
): string {
    const stageEvents = Array.isArray(live.stage_events) ? live.stage_events : []
    const bridgeLogs = Array.isArray(diagnostics.bridge_logs) ? diagnostics.bridge_logs : []
    const quality =
        (live.quality as Record<string, unknown>) ||
        (diagnostics.quality as Record<string, unknown>) ||
        undefined
    const requirementSlots =
        (live.requirement_slots as Record<string, unknown>) ||
        (diagnostics.requirement_slots as Record<string, unknown>) ||
        undefined
    const typologyKey =
        (live.typology_key as string | undefined) ||
        (diagnostics.typology_key as string | undefined) ||
        undefined
    const mep =
        (live.mep as Record<string, unknown>) ||
        (diagnostics.mep as Record<string, unknown>) ||
        undefined
    const payload = {
        title: language === "en" ? "Nexus Orchestration Flow" : "\u534f\u540c\u7f16\u6392\u6d41",
        status,
        mode: String(live.execution_mode || "dry-run"),
        agent: String(live.model_used || "") || undefined,
        state_path: String(live.state_path || "") || undefined,
        result_path: String(live.result_path || "") || undefined,
        handoff_path: String(live.handoff_path || "") || undefined,
        summary: String(live.summary_note || "") || undefined,
        exit_code: diagnostics.bridge_exit_code ?? undefined,
        stages: stageEvents,
        logs: bridgeLogs,
        quality,
        requirement_slots: requirementSlots,
        typology_key: typologyKey,
        mep,
    }
    return `<execution-log>${JSON.stringify(payload)}</execution-log>`
}

function buildExecutionProgressBlock(
    progress: NexusArchitectProgressSnapshot,
): string {
    return `<execution-log>${JSON.stringify(progress)}</execution-log>`
}

function createStreamingNexusResponse(params: {
    bimStatusText: string
    language: ClarifyLanguage
    run: (emitProgress: (progress: NexusArchitectProgressSnapshot) => void) => Promise<NexusArchitectAdapterOutput>
}): Response {
    const textId = `nexus-orchestration-stream-${Date.now()}`

    return createUIMessageStreamResponse({
        stream: createUIMessageStream({
            execute: async ({ writer }) => {
                const streamStart = Date.now()
                console.log(`[Nexus-Stream] Starting response stream`)
                writer.write({ type: "start" })
                writer.write({ type: "text-start", id: textId })
                const initialText = params.bimStatusText + "\n\nInitializing Nexus Orchestration Engine...\n"
                mirrorConsoleBlock("[Nexus-Web-Status]", initialText)
                writer.write({
                    type: "text-delta",
                    id: textId,
                    delta: initialText,
                })

                let lastProgressPayload = ""
                let lastProgressSummary = ""
                const emitProgress = (progress: NexusArchitectProgressSnapshot) => {
                    const block = buildExecutionProgressBlock(progress)
                    if (block === lastProgressPayload) return
                    lastProgressPayload = block
                    const progressSummary = summarizeExecutionLog(block)
                    if (progressSummary && progressSummary !== lastProgressSummary) {
                        lastProgressSummary = progressSummary
                        mirrorConsoleBlock("[Nexus-Web-Progress]", block)
                    }
                    writer.write({
                        type: "text-delta",
                        id: textId,
                        delta: `${block}\n\n`,
                    })
                }

                let result: NexusArchitectAdapterOutput
                try {
                    result = await params.run(emitProgress)
                } catch (error) {
                    const failureResult: NexusArchitectAdapterOutput = {
                        ok: false,
                        mode: "live",
                        source: "nexus-architect-bridge",
                        unifiedBimJson: {},
                        diagnostics: {
                            live_error: error instanceof Error ? error.message : "Nexus runtime disruption.",
                            bridge_logs: [],
                        },
                        raw: { live: { stage_events: [], output_sum: "" } },
                    }
                    const failureText = buildNexusOrchestrationFailureText(params.bimStatusText, failureResult, params.language)
                    mirrorConsoleBlock("[Nexus-Web-Final]", failureText)
                    writer.write({ type: "text-delta", id: textId, delta: failureText })
                    writer.write({ type: "text-end", id: textId })
                    writer.write({ type: "finish" })
                    return
                }

                const finalText = result.ok
                    ? buildNexusSynthesisResultText(params.bimStatusText, result, params.language)
                    : buildNexusOrchestrationFailureText(params.bimStatusText, result, params.language)

                mirrorConsoleBlock("[Nexus-Web-Final]", finalText)
                writer.write({ type: "text-delta", id: textId, delta: finalText })
                writer.write({ type: "text-end", id: textId })
                const streamDuration = ((Date.now() - streamStart) / 1000).toFixed(1)
                console.log(`[Nexus-Stream] Response stream complete in ${streamDuration}s (ok=${result.ok})`)
                writer.write({ type: "finish" })
            },
        }),
    })
}

async function handleChatRequest(req: Request): Promise<Response> {
    const accessCodes = process.env.ACCESS_CODE_LIST?.split(",").map((code) => code.trim()).filter(Boolean) || []
    if (accessCodes.length > 0) {
        const accessCodeHeader = req.headers.get("x-access-code")
        if (!accessCodeHeader || !accessCodes.includes(accessCodeHeader)) {
            return Response.json({ error: "Invalid or missing access code." }, { status: 401 })
        }
    }

    const body = await req.json()
    const { messages, sessionId } = body
    const customSystemMessage = typeof body.customSystemMessage === "string" ? body.customSystemMessage.slice(0, 5000) : ""
    const userId = getUserIdFromRequest(req)
    const validSessionId = sessionId && typeof sessionId === "string" && sessionId.length <= 200 ? sessionId : undefined
    const lastUserMessage = [...(messages as ChatMessage[])].reverse().find((m) => m.role === "user")
    const userInputText =
        lastUserMessage?.parts?.find(
            (p): p is ChatTextPart => p.type === "text",
        )?.text || ""

    setTraceInput({ input: userInputText, sessionId: validSessionId, userId })

    const hasOwnApiKey = !!(req.headers.get("x-ai-provider") && (req.headers.get("x-ai-api-key") || req.headers.get("x-aws-access-key-id") || req.headers.get("x-vertex-api-key")))

    if (isQuotaEnabled() && !hasOwnApiKey && userId !== "anonymous") {
        const quotaCheck = await checkAndIncrementRequest(userId, {
            requests: Number(process.env.DAILY_REQUEST_LIMIT) || 10,
            tokens: Number(process.env.DAILY_TOKEN_LIMIT) || 200000,
            tpm: Number(process.env.TPM_LIMIT) || 20000,
        })
        if (!quotaCheck.allowed) {
            return Response.json({ error: quotaCheck.error, type: quotaCheck.type }, { status: 429 })
        }
    }

    const fileValidation = validateFileParts(messages)
    if (!fileValidation.valid) {
        return Response.json({ error: fileValidation.error }, { status: 400 })
    }

    const provider = req.headers.get("x-ai-provider")
    const baseUrl = req.headers.get("x-ai-base-url")

    const clientOverrides: ClientOverrides = {
        provider: provider || "openai",
        baseUrl: baseUrl || undefined,
        apiKey: req.headers.get("x-ai-api-key") || undefined,
        modelId: req.headers.get("x-ai-model") || "gpt-4o",
        vertexApiKey: req.headers.get("x-vertex-api-key") || undefined,
    }

    // Diagnostic: show which credentials arrived from the frontend so we can
    // tell at a glance whether the problem is "key not sent" or "key not
    // reaching Python". We never log the key itself, only its length/origin.
    const selectedModelIdHeader = req.headers.get("x-selected-model-id") || ""
    console.log(
        "[Nexus-Route] client credentials | " +
            `provider=${clientOverrides.provider || "(empty)"} ` +
            `modelId=${clientOverrides.modelId || "(empty)"} ` +
            `baseUrl=${clientOverrides.baseUrl || "(empty)"} ` +
            `apiKey=${clientOverrides.apiKey ? "present(" + clientOverrides.apiKey.length + ")" : "(empty)"} ` +
            `selectedModelId=${selectedModelIdHeader || "(empty)"}`,
    )

    // Optional per-agent model specialisation. Clients send a JSON blob in
    // `x-agent-overrides` matching `{ architect?, constructor?, checker? }`.
    // Missing agents fall back to the main model.
    const agentOverridesHeader = req.headers.get("x-agent-overrides") || ""
    const agentOverrides: Record<
        string,
        { provider?: string; modelId?: string; baseUrl?: string; apiKey?: string }
    > = {}
    if (agentOverridesHeader) {
        try {
            const parsed = JSON.parse(agentOverridesHeader)
            if (parsed && typeof parsed === "object") {
                for (const key of ["architect", "constructor", "checker"] as const) {
                    const entry = parsed[key]
                    if (entry && typeof entry === "object") {
                        agentOverrides[key] = {
                            provider: typeof entry.provider === "string" ? entry.provider : undefined,
                            modelId: typeof entry.modelId === "string" ? entry.modelId : undefined,
                            baseUrl: typeof entry.baseUrl === "string" ? entry.baseUrl : undefined,
                            apiKey: typeof entry.apiKey === "string" ? entry.apiKey : undefined,
                        }
                    }
                }
            }
        } catch {
            console.warn("[Nexus-Route] Ignoring malformed x-agent-overrides header")
        }
    }

    const bimModeEnabled = req.headers.get("x-bim-mode") === "true"
    const mepModeEnabled = req.headers.get("x-mep-mode") === "true"
    let bimStatusText: string | null = null
    let bimRouteSuggestion: GenerationRoute | null = null
    let bimClarifyLanguage: ClarifyLanguage = "zh"

    if (bimModeEnabled) {
        const clarifyLanguage = (req.headers.get("x-clarify-language") as ClarifyLanguage) || "zh"
        bimClarifyLanguage = clarifyLanguage
        const conversationUserText = getConversationUserText(messages)
        const forgeVisionContextDetected = hasForgeVisionFormContext(conversationUserText || userInputText)
        if (forgeVisionContextDetected) {
            const forgeVisionText = conversationUserText || userInputText
            const visionSnapshot = buildForgeVisionSlotSnapshot(forgeVisionText)
            const forgeVisionComplexityScore = extractForgeVisionComplexityScore(forgeVisionText)
            bimRouteSuggestion = "nexus-synthesis"
            bimStatusText = buildForgeVisionReadinessText(
                buildReadinessStatusText(clarifyLanguage, forgeVisionComplexityScore, "nexus-synthesis", visionSnapshot),
                forgeVisionComplexityScore,
                clarifyLanguage,
                forgeVisionText,
            )
            console.log("[Nexus-Route] ForgeVision context detected. Skipping clarification and routing to nexus-synthesis.")
        }
        const clarificationDecision = evaluateClarificationNeed(conversationUserText || userInputText)
        const ruleSnapshot = clarificationDecision.slotSnapshot
        const passScore = Number(req.headers.get("x-clarify-pass-score") || 85)

        try {
            if (forgeVisionContextDetected) {
                throw new Error("__OPENBIMFORGE_SKIP_CLARIFICATION__")
            }
            const clarifyOverrides = buildClarificationOverrides(req, clientOverrides)
            const { model: clarificationModel, providerOptions: clarificationProviderOptions, headers: clarificationHeaders } = getAIModel(clarifyOverrides)

            const rules = `\n[Routing Rules]\n- "nexus-synthesis": If the user wants to generate/build a BIM model, floor plan, or architecture.\n- "nexus-visionary": Only for general chatting or questions.`
            const assessmentPrompt = clarifyLanguage === "zh"
                ? `你是 openBIMForge 需求完整度评估器。${rules}\n已提取：${JSON.stringify(ruleSnapshot)}\n输入：${conversationUserText || userInputText}`
                : `You are an openBIMForge requirement completeness evaluator.${rules}\nConfirmed: ${JSON.stringify(ruleSnapshot)}\nInput: ${conversationUserText || userInputText}`

            const clarifySchema = z.object({
                ready_to_generate: z.boolean(),
                completion_score: z.number(),
                missing_fields: z.array(z.string()),
                route_suggestion: z.enum(["nexus-synthesis", "nexus-visionary"]),
                clarification_message: z.string(),
                extracted_slots: z.object({
                    building_type: z.string().optional(),
                    storey_count: z.string().optional(),
                    target_area: z.string().optional(),
                    floor_height: z.string().optional(),
                }),
            })

            const assessment = await generateObject({
                model: clarificationModel,
                schema: clarifySchema,
                messages: [{ role: "user", content: assessmentPrompt }],
                ...(clarificationProviderOptions && { providerOptions: clarificationProviderOptions }),
                ...(clarificationHeaders && { headers: clarificationHeaders }),
            })

            const assessmentObject = assessment.object as z.infer<typeof clarifySchema>
            const mergedSnapshot = mergeSlotSnapshots(ruleSnapshot, assessmentObject.extracted_slots)

            // Log clarification assessment to Node.js console
            console.log(`\n[Nexus-Stage 0] Clarification Assessment`)
            console.log(`  └─ score: ${assessmentObject.completion_score}/100, ready: ${assessmentObject.ready_to_generate}, threshold: ${passScore}`)
            console.log(`  └─ route: ${assessmentObject.route_suggestion}`)
            console.log(`  └─ missing: ${JSON.stringify(assessmentObject.missing_fields)}`)
            console.log(`  └─ slots: ${JSON.stringify(mergedSnapshot)}`)

            const readyByScore = assessmentObject.ready_to_generate && assessmentObject.completion_score >= passScore

            if (!readyByScore) {
                console.log(`  └─ → NOT READY, sending clarification question`)
                const clarificationPrompt = buildClarificationPrompt(conversationUserText || userInputText, assessmentObject.missing_fields, clarifyLanguage, mergedSnapshot)
                const clarificationResult = streamText({
                    model: clarificationModel,
                    messages: [{ role: "user", content: clarificationPrompt }],
                    ...(clarificationProviderOptions && { providerOptions: clarificationProviderOptions }),
                    onFinish: ({ text }) => mirrorConsoleBlock("[Nexus-Web-Clarify]", text),
                })
                return clarificationResult.toUIMessageStreamResponse({ sendReasoning: false })
            }

            bimStatusText = buildReadinessStatusText(clarifyLanguage, assessmentObject.completion_score, assessmentObject.route_suggestion, mergedSnapshot)
            bimRouteSuggestion = assessmentObject.route_suggestion
            if (
                bimRouteSuggestion !== "nexus-synthesis" &&
                shouldForceNexusSynthesis(userInputText, conversationUserText || userInputText)
            ) {
                bimRouteSuggestion = "nexus-synthesis"
                console.log("[Nexus-Route] Continuation intent detected. Forcing nexus-synthesis instead of normal chat.")
            }
            console.log(`  └─ → READY, routing to ${bimRouteSuggestion}`)
        } catch (err) {
            if (err instanceof Error && err.message === "__OPENBIMFORGE_SKIP_CLARIFICATION__") {
                // Route was already resolved from the ForgeVision context above.
            } else {
            console.warn("[Clarification Loop] Fallback triggered", err)
            if (shouldForceNexusSynthesis(userInputText, conversationUserText || userInputText) || !clarificationDecision.shouldClarify) {
                bimRouteSuggestion = "nexus-synthesis"
                bimStatusText = buildReadinessStatusText(clarifyLanguage, passScore, "nexus-synthesis", ruleSnapshot)
                console.log("[Nexus-Route] Clarification fallback routed to nexus-synthesis.")
            } else {
                const fallbackText = buildFallbackClarificationText(clarificationDecision.missingRequiredSlots, clarifyLanguage, ruleSnapshot)
                mirrorConsoleBlock("[Nexus-Web-Clarify]", fallbackText)
                return buildPlainTextStreamResponse(fallbackText)
            }
            }
        }
    } else {
        // Clarification loop is OFF: bypass assessment and route directly to Nexus synthesis
        bimStatusText = "需求追问已关闭，直接进入 Nexus 物理构筑阶段..."
        bimRouteSuggestion = "nexus-synthesis"
        console.log(`[Nexus-Route] Clarification disabled. Direct routing to ${bimRouteSuggestion}`)
    }

    // Force execution if route is synthesis
    if (bimRouteSuggestion === "nexus-synthesis") {
        const nexusExecutionMode = (process.env.OPENBIMFORGE_DEFAULT_EXECUTION_MODE || process.env.TEXT2BIM_DEFAULT_EXECUTION_MODE) === "vectorworks" ? "vectorworks" : "dry-run"
        console.log(`[Nexus-Route] Execution mode: ${nexusExecutionMode}`)

        // For server-side models the clientOverrides.apiKey is intentionally
        // empty (the key lives in the server environment). We call getAIModel()
        // here so the resolved provider/modelId are available, then read the
        // actual API key from the server environment for the Python bridge.
        let nexusProvider = clientOverrides.provider || "openai"
        let nexusModelId = clientOverrides.modelId || "gpt-4o"
        let nexusApiKey = clientOverrides.apiKey || undefined
        let nexusBaseUrl = clientOverrides.baseUrl || undefined
        try {
            const resolved = getAIModel(clientOverrides)
            nexusProvider = resolved.provider
            nexusModelId = resolved.modelId

            const selectedId = req.headers.get("x-selected-model-id") || ""
            if (!nexusApiKey && selectedId.startsWith("server:")) {
                // Server model: look up the apiKeyEnv from ai-models.json,
                // then read the actual key from the process environment.
                const { findServerModelById } = await import("@/lib/server-model-config")
                const serverModel = await findServerModelById(selectedId)
                if (serverModel?.apiKeyEnv) {
                    const envNames = Array.isArray(serverModel.apiKeyEnv)
                        ? serverModel.apiKeyEnv
                        : [serverModel.apiKeyEnv]
                    for (const envName of envNames) {
                        const val = process.env[envName]
                        if (val) { nexusApiKey = val; break }
                    }
                }
                if (!nexusApiKey) {
                    // Fall back to the standard provider env var.
                    const providerEnvMap: Record<string, string> = {
                        openai: "OPENAI_API_KEY",
                        anthropic: "ANTHROPIC_API_KEY",
                        google: "GOOGLE_GENERATIVE_AI_API_KEY",
                        deepseek: "DEEPSEEK_API_KEY",
                        siliconflow: "SILICONFLOW_API_KEY",
                        openrouter: "OPENROUTER_API_KEY",
                    }
                    const envVarName = providerEnvMap[nexusProvider] || ""
                    if (envVarName) nexusApiKey = process.env[envVarName] || undefined
                }
                if (!nexusBaseUrl && serverModel?.baseUrlEnv) {
                    nexusBaseUrl = process.env[serverModel.baseUrlEnv] || undefined
                }
                if (!nexusBaseUrl) {
                    const baseUrlEnvMap: Record<string, string> = {
                        openai: "OPENAI_BASE_URL",
                        anthropic: "ANTHROPIC_BASE_URL",
                        deepseek: "DEEPSEEK_BASE_URL",
                        siliconflow: "SILICONFLOW_BASE_URL",
                        openrouter: "OPENROUTER_BASE_URL",
                        ollama: "OLLAMA_BASE_URL",
                    }
                    const baseUrlEnvName = baseUrlEnvMap[nexusProvider] || ""
                    if (baseUrlEnvName) nexusBaseUrl = process.env[baseUrlEnvName] || undefined
                }
            }
        } catch {
            // getAIModel may throw if credentials are missing; fall back to
            // clientOverrides so the Python bridge can emit a clear error.
        }

        console.log(
            "[Nexus-Route] python payload | " +
                `provider=${nexusProvider} ` +
                `modelId=${nexusModelId} ` +
                `baseUrl=${nexusBaseUrl || "(empty)"} ` +
                `apiKey=${nexusApiKey ? "present(" + nexusApiKey.length + ")" : "(empty)"}`,
        )

        return createStreamingNexusResponse({
            bimStatusText: bimStatusText || "",
            language: bimClarifyLanguage,
            run: (emitProgress) => runNexusArchitectAdapter({
                query: userInputText,
                chatHistory: getConversationUserText(messages),
                sessionId: validSessionId,
                mode: "live",
                llmConfig: {
                    provider: nexusProvider,
                    modelId: nexusModelId,
                    baseUrl: nexusBaseUrl,
                    apiKey: nexusApiKey,
                    ...(Object.keys(agentOverrides).length > 0 && {
                        agentOverrides: agentOverrides as {
                            architect?: { provider?: string; modelId?: string; baseUrl?: string; apiKey?: string }
                            constructor?: { provider?: string; modelId?: string; baseUrl?: string; apiKey?: string }
                            checker?: { provider?: string; modelId?: string; baseUrl?: string; apiKey?: string }
                        },
                    }),
                },
                executionConfig: {
                    executionMode: nexusExecutionMode,
                    mepMode: mepModeEnabled ? "drainage" : undefined,
                },
            }, { onProgress: emitProgress }),
        })
    }

    const minimalStyle = req.headers.get("x-minimal-style") === "true"
    const { model, providerOptions, headers, modelId } = getAIModel(clientOverrides)
    const systemMessage = getSystemPrompt(modelId, minimalStyle)
    const nexusExecutionGuard = bimModeEnabled
        ? [
            "Nexus execution integrity rules:",
            "- Do not invent Nexus stages, timestamps, logs, file names, download links, IFC/WebGL exports, or completion states.",
            "- Only report execution details that came from backend <execution-log> payloads or explicit tool/runtime output.",
            "- If the user asks to execute, deliver, stream logs, or force the full chain, route through the Nexus backend instead of role-playing progress.",
            "- If no backend execution is active, say that no real Nexus runtime output is available yet.",
        ].join("\n")
        : ""
    const finalSystemMessage = [systemMessage, customSystemMessage, nexusExecutionGuard].filter(Boolean).join("\n\n")

    const result = streamText({
        model,
        messages: [{ role: "system", content: finalSystemMessage }, ...(await convertToModelMessages(messages))],
        ...(providerOptions && { providerOptions }),
        ...(headers && { headers }),
        onFinish: ({ text }) => {
            setTraceOutput(text)
            mirrorConsoleBlock(bimModeEnabled ? "[Nexus-Web-LLM]" : "[Chat-Web-LLM]", text)
        },
    })

    if (bimStatusText) return buildStatusPrefixedStreamResponse(bimStatusText, result)
    return result.toUIMessageStreamResponse({ sendReasoning: true })
}

export async function POST(req: Request) {
    try {
        return await handleChatRequest(req)
    } catch (error) {
        console.error("Chat Error:", error)
        return Response.json({ error: error instanceof Error ? error.message : "Internal Error" }, { status: 500 })
    }
}
