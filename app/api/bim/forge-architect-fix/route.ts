import { generateText } from "ai"
import { promises as fs } from "fs"
import { jsonrepair } from "jsonrepair"
import { NextResponse } from "next/server"
import path from "path"
import { getNexusRuntimeRoots, isPathInsideRoots } from "@/lib/bim/openbimforge-paths"
import { z } from "zod"
import { getAIModel } from "@/lib/ai-providers"

export const runtime = "nodejs"

const FixRequestSchema = z.object({
    fixRequestPath: z.string().optional(),
    handoffPath: z.string().optional(),
    resultPath: z.string().optional(),
    note: z.string().optional(),
})

function getAllowedRoots(): string[] {
    return getNexusRuntimeRoots([
        "runtime_handoffs",
        "runtime_artifacts",
    ])
}

function isAllowedPath(targetPath: string): boolean {
    return isPathInsideRoots(targetPath, getAllowedRoots())
}

async function readJsonFile(filePath: string): Promise<Record<string, unknown>> {
    const content = await fs.readFile(filePath, "utf-8")
    return JSON.parse(content) as Record<string, unknown>
}

function stripCodeFence(code: string): string {
    let text = code.trim()
    if (text.startsWith("```")) {
        text = text.replace(/^```[a-zA-Z0-9_-]*\s*/, "")
        text = text.replace(/\s*```$/, "")
    }
    return text.trim()
}

function parseFixerJson(text: string): {
    decision: "retry" | "stop"
    reasoning?: string
    fix_strategy?: string[]
    patched_code?: string
    notes_for_ui?: string
} {
    const trimmed = text.trim()
    const candidate = trimmed.startsWith("{")
        ? trimmed
        : trimmed.slice(trimmed.indexOf("{"), trimmed.lastIndexOf("}") + 1)
    return JSON.parse(jsonrepair(candidate))
}

function getResultPathFromPayload(
    payload: Record<string, unknown>,
    fallbackPayloadPath: string,
): string {
    const executionConfig = (payload.execution_config || {}) as Record<string, unknown>
    const resultPath = String(executionConfig.resultPath || "")
    if (resultPath) return resultPath
    return fallbackPayloadPath.replace(/\.json$/i, ".result.json")
}

function buildNexusFixPrompt(params: {
    payload: Record<string, unknown>
    result: Record<string, unknown>
    note?: string
}): string {
    const result = params.result
    const payload = params.payload
    const executionResult = (result.result || {}) as Record<string, unknown>
    const attempts = executionResult.attempts || []
    const code = String(executionResult.code_result || "") || String(payload.code_result || "")

    return [
        "You are the Nexus-Orchestration Diagnostic Agent.",
        "Your objective is to repair Constructor Synthesis Code that failed during the BIM synthesis phase.",
        "",
        "Rigorous Synthesis Rules:",
        "- Output must be valid JSON only.",
        "- Preserve the original Architect-Agent's semantic intent and BIM geometry logic.",
        "- Provide the COMPLETE patched Python synthesis script, not a partial diff.",
        "- Adhere strictly to the Nexus synthesis tool namespace.",
        "- Valid Nexus Tools: create_story_layer, set_active_story_layer, create_functional_area, create_wall, set_wall_thickness, set_wall_elevation, add_window_to_wall, add_door_to_wall, create_polygon, create_slab, set_slab_height, set_slab_style, duplicate_obj, rotate_obj, move, delete_element.",
        "",
        "Response Schema:",
        JSON.stringify({
            decision: "retry",
            reasoning: "Deep synthesis failure analysis",
            fix_strategy: ["Geometric correction", "Symbol fallback"],
            patched_code: "Full constructor-ready python code",
            notes_for_ui: "Nexus-Constructor status update in Chinese"
        }, null, 2),
        "",
        `Architect Intent:\n${String(payload.query || "")}`,
        "",
        `Capability Contract Snapshot:\n${JSON.stringify(payload.style_manifest || {}, null, 2)}`,
        "",
        `Synthesis Disruption History:\n${JSON.stringify(attempts, null, 2).slice(0, 10000)}`,
        "",
        `Critical Diagnostic Traceback:\n${String(result.error_traceback || result.error || "").slice(0, 8000)}`,
        "",
        params.note ? `Contextual Note:\n${params.note}` : "",
        "",
        `Original Synthesis Script:\n\`\`\`python\n${stripCodeFence(code)}\n\`\`\``,
    ].join("\n")
}

function buildRetryPayloadPath(payloadPath: string): string {
    const parsed = path.parse(payloadPath)
    const timestamp = new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14)
    return path.join(parsed.dir, `${parsed.name}_synthesis_retry_${timestamp}.json`)
}

export async function POST(req: Request) {
    try {
        const body = FixRequestSchema.parse(await req.json())
        let payloadPath = body.handoffPath || ""
        let resultPath = body.resultPath || ""
        let note = body.note

        if (body.fixRequestPath) {
            if (!isAllowedPath(body.fixRequestPath)) {
                return NextResponse.json({ ok: false, error: "Diagnostic path is restricted." }, { status: 403 })
            }
            const fixRequest = await readJsonFile(body.fixRequestPath)
            payloadPath = String(fixRequest.handoffPath || payloadPath)
            resultPath = String(fixRequest.resultPath || resultPath)
            note = note || String(fixRequest.note || "")
        }

        if (!payloadPath || !isAllowedPath(payloadPath)) {
            return NextResponse.json({ ok: false, error: "Transit-Payload path is restricted." }, { status: 403 })
        }

        const payload = await readJsonFile(payloadPath)
        resultPath = resultPath || getResultPathFromPayload(payload, payloadPath)
        if (!isAllowedPath(resultPath)) {
            return NextResponse.json({ ok: false, error: "Synthesis result path is restricted." }, { status: 403 })
        }
        const result = await readJsonFile(resultPath)

        const overrides = {
            provider: req.headers.get("x-ai-provider"),
            modelId: req.headers.get("x-ai-model"),
            baseUrl: req.headers.get("x-ai-base-url"),
            apiKey: req.headers.get("x-ai-api-key"),
            vertexApiKey: req.headers.get("x-vertex-api-key"),
        }
        const { model, providerOptions, headers } = getAIModel(overrides)
        const diagnosticPrompt = buildNexusFixPrompt({ payload, result, note })

        const diagnosticResult = await generateText({
            model,
            messages: [{ role: "user", content: diagnosticPrompt }],
            temperature: 0,
            ...(providerOptions && { providerOptions }),
            ...(headers && { headers }),
        })

        const diagnosticOutput = parseFixerJson(diagnosticResult.text)
        if (diagnosticOutput.decision !== "retry" || !diagnosticOutput.patched_code) {
            return NextResponse.json({ ok: false, decision: diagnosticOutput.decision, diagnosticOutput }, { status: 422 })
        }

        const retryPayloadPath = buildRetryPayloadPath(payloadPath)
        const retryResultPath = retryPayloadPath.replace(/\.json$/i, ".result.json")
        const previousFixes = Array.isArray(payload.fixer_history) ? payload.fixer_history : []
        
        const retryPayload = {
            ...payload,
            code_result: `\`\`\`python\n${stripCodeFence(diagnosticOutput.patched_code)}\n\`\`\``,
            previous_payload_path: payloadPath,
            previous_result_path: resultPath,
            synthesis_diagnostic_history: [
                ...previousFixes,
                {
                    created_at: new Date().toISOString(),
                    reasoning: diagnosticOutput.reasoning || "",
                    fix_strategy: diagnosticOutput.fix_strategy || [],
                    notes_for_ui: diagnosticOutput.notes_for_ui || "",
                },
            ],
            execution_config: {
                ...((payload.execution_config || {}) as Record<string, unknown>),
                resultPath: retryResultPath,
            },
        }

        await fs.writeFile(retryPayloadPath, JSON.stringify(retryPayload, null, 2), "utf-8")

        return NextResponse.json({
            ok: true,
            retryPayloadPath,
            retryResultPath,
            diagnosticOutput: {
                decision: diagnosticOutput.decision,
                reasoning: diagnosticOutput.reasoning,
                fix_strategy: diagnosticOutput.fix_strategy,
                notes_for_ui: diagnosticOutput.notes_for_ui,
            },
        })
    } catch (error) {
        return NextResponse.json({ ok: false, error: error instanceof Error ? error.message : "Nexus-Fixer runtime disruption." }, { status: 500 })
    }
}
