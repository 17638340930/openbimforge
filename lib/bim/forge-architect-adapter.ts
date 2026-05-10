import { spawn } from "node:child_process"
import { promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"
import {
    getNexusArchitectRoot,
    getNexusRuntimeRoot,
} from "@/lib/bim/openbimforge-paths"

export interface NexusArchitectAgentOverride {
    provider?: string
    modelId?: string
    baseUrl?: string
    apiKey?: string
}

export interface NexusArchitectAdapterInput {
    query: string
    chatHistory?: string
    sessionId?: string
    modelHint?: string
    mode?: "mock" | "live"
    llmConfig?: {
        provider: string
        modelId: string
        baseUrl?: string
        apiKey?: string
        vertexApiKey?: string
        /**
         * Per-agent overrides. When present, the sub-agent uses the
         * specified provider/model instead of the top-level one. Missing
         * keys fall back to the top-level config.
         */
        agentOverrides?: {
            architect?: NexusArchitectAgentOverride
            constructor?: NexusArchitectAgentOverride
            checker?: NexusArchitectAgentOverride
        }
    }
    executionConfig?: {
        executionMode?: "dry-run" | "vectorworks"
        solibriPath?: string
        outputRoot?: string
        mepMode?: "drainage"
    }
}

export interface NexusArchitectAdapterOutput {
    ok: boolean
    mode: "mock" | "live"
    source: "nexus-architect-bridge"
    unifiedBimJson: Record<string, unknown>
    diagnostics?: Record<string, unknown>
    raw?: Record<string, unknown>
}

function getCapabilityManifestPath(): string {
    return path.join(
        getNexusRuntimeRoot("runtime_capabilities"),
        "vectorworks_styles.json",
    )
}

function buildVectorworksCapabilityScanScript(projectRoot: string): string {
    const manifestPath = getCapabilityManifestPath()
    return [
        "import sys",
        "",
        `project_root = r"${projectRoot}"`,
        "if project_root not in sys.path:",
        "    sys.path.insert(0, project_root)",
        "",
        "from tool_agent_bridge.vectorworks_capability_scan import write_manifest",
        "",
        `path = write_manifest(r"${manifestPath}")`,
        "print(path)",
    ].join("\n")
}

async function getVectorworksCapabilityStatus(projectRoot: string): Promise<{
    ready: boolean
    manifestPath: string
    scanScript: string
    manifest?: Record<string, unknown>
}> {
    const manifestPath = getCapabilityManifestPath()
    const scanScript = buildVectorworksCapabilityScanScript(projectRoot)
    try {
        const content = await fs.readFile(manifestPath, "utf-8")
        return {
            ready: true,
            manifestPath,
            scanScript,
            manifest: JSON.parse(content) as Record<string, unknown>,
        }
    } catch {
        return {
            ready: false,
            manifestPath,
            scanScript,
        }
    }
}

export interface NexusArchitectProgressStage {
    id?: string
    label?: string
    status?: string
    duration_ms?: number
    detail?: string
}

export interface NexusArchitectProgressSnapshot {
    title: string
    status: "running" | "success" | "failed"
    mode: string
    agent?: string
    state_path?: string
    exit_code?: number | null
    stages: NexusArchitectProgressStage[]
    logs: string[]
    summary?: string
}

interface RunNexusArchitectAdapterOptions {
    onProgress?: (snapshot: NexusArchitectProgressSnapshot) => void
}

function buildCommandFailureOutput(
    message: string,
    stderr: string,
    input?: NexusArchitectAdapterInput,
    progress?: {
        stages?: NexusArchitectProgressStage[]
        logs?: string[]
        statePath?: string
        exitCode?: number | null
    },
): NexusArchitectAdapterOutput {
    const bridgeLogs = extractBridgeLogLines(stderr)
    const logs = bridgeLogs.length > 0 ? bridgeLogs : progress?.logs || []
    const diagnostics: Record<string, unknown> = {
        live_call: "failed",
        live_error: message,
        live_error_type: "NexusBridgeCommandError",
        bridge_logs: logs,
        bridge_exit_code: progress?.exitCode ?? null,
        progress_stages: progress?.stages || [],
        progress_state_path: progress?.statePath || "",
    }

    return {
        ok: false,
        mode: "live",
        source: "nexus-architect-bridge",
        unifiedBimJson: {},
        diagnostics,
        raw: {
            ok: false,
            mode: "live",
            diagnostics,
            live: {
                stage_events: progress?.stages || [],
                output_sum: logs.join("\n"),
                execution_mode: input?.executionConfig?.executionMode || "dry-run",
                model_used: input?.llmConfig?.modelId || "",
                state_path: progress?.statePath || "",
            },
        },
    }
}

function extractBridgeLogLines(stderr: string): string[] {
    return stderr
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .filter(
            (line) =>
                line.startsWith("[Nexus-") ||
                line.startsWith("Architect:") ||
                line.startsWith("Constructor:") ||
                line.includes("Traceback") ||
                line.includes("Error")
        )
}

function summarizeProgress(
    stages: NexusArchitectProgressStage[],
    status: "running" | "success" | "failed",
): string {
    const completedCount = stages.filter(
        (stage) => stage.status === "completed",
    ).length
    const totalCount = 5 // Stage 0 to 4
    if (status === "running") {
        return `Nexus-Framework: ${completedCount}/${totalCount} stages completed...`
    }
    if (status === "failed") {
        return `Nexus-Framework: Orchestration interrupted at stage ${completedCount}/${totalCount}`
    }
    return `Nexus-Framework: Digital BIM Asset synthesis finished successfully (${completedCount}/${totalCount} stages).`
}

function createProgressSnapshot(params: {
    input: NexusArchitectAdapterInput
    logs: string[]
    stages: NexusArchitectProgressStage[]
    status: "running" | "success" | "failed"
    exitCode?: number | null
    statePath?: string
}): NexusArchitectProgressSnapshot {
    return {
        title: "Nexus-Architect Execution Flow",
        status: params.status,
        mode: params.input.executionConfig?.executionMode || "dry-run",
        agent: params.input.llmConfig?.modelId,
        state_path: params.statePath,
        exit_code: params.exitCode,
        stages: params.stages,
        logs: params.logs.slice(-80),
        summary: summarizeProgress(params.stages, params.status),
    }
}

function upsertStage(
    stages: NexusArchitectProgressStage[],
    stage: NexusArchitectProgressStage,
): NexusArchitectProgressStage[] {
    const stageId = stage.id || stage.label
    if (!stageId) {
        return [...stages, stage]
    }
    const nextStages = [...stages]
    const index = nextStages.findIndex(
        (item) => (item.id || item.label) === stageId,
    )
    if (index >= 0) {
        nextStages[index] = {
            ...nextStages[index],
            ...stage,
        }
    } else {
        nextStages.push(stage)
    }
    return nextStages
}

function parseStageEventLine(line: string): NexusArchitectProgressStage | null {
    const prefix = "[Nexus-Stage]"
    if (!line.startsWith(prefix)) {
        return null
    }

    const jsonText = line.slice(prefix.length).trim()
    if (!jsonText) return null

    try {
        return JSON.parse(jsonText) as NexusArchitectProgressStage
    } catch {
        return null
    }
}

function parseBridgeJson(stdout: string): Record<string, unknown> {
    const trimmed = stdout.trim()
    if (!trimmed) {
        throw new Error("Nexus-Orchestrator returned empty stdout.")
    }

    try {
        return JSON.parse(trimmed) as Record<string, unknown>
    } catch {
        const lines = trimmed
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter(Boolean)
        for (let index = lines.length - 1; index >= 0; index -= 1) {
            const line = lines[index]
            if (!line.startsWith("{") && !line.startsWith("[")) {
                continue
            }
            try {
                return JSON.parse(line) as Record<string, unknown>
            } catch {}
        }
    }

    throw new Error(
        `Nexus-Orchestrator returned invalid JSON output.`
    )
}

async function resolvePythonCommand(projectRoot: string): Promise<string> {
    const candidates = [
        process.env.OPENBIMFORGE_PYTHON_COMMAND || "",
        path.join(projectRoot, ".venv", "Scripts", "python.exe"),
        path.join(projectRoot, ".venv", "bin", "python"),
        "python"
    ]

    for (const candidate of candidates.filter(Boolean)) {
        try {
            await fs.access(candidate)
            return candidate
        } catch {
            // Try next
        }
    }

    return "python"
}

function spawnBridgeProcess(
    command: string,
    args: string[],
    cwd: string,
    env: NodeJS.ProcessEnv,
    timeoutMs: number,
    input: NexusArchitectAdapterInput,
    onProgress?: (snapshot: NexusArchitectProgressSnapshot) => void,
): Promise<{
    stdout: string
    stderr: string
    exitCode: number | null
    stages: NexusArchitectProgressStage[]
    logs: string[]
    statePath?: string
}> {
    return new Promise((resolve, reject) => {
        console.log(`[Nexus-Bridge] Executing: ${command} ${args.join(" ")}`)
        console.log(`[Nexus-Bridge] CWD: ${cwd}`)
        
        const child = spawn(command, args, {
            cwd,
            env,
            stdio: ["ignore", "pipe", "pipe"],
            windowsHide: true,
        })

        let stdout = ""
        let stderr = ""
        let stdoutBuffer = ""
        let stderrBuffer = ""
        let settled = false
        let exitCode: number | null = null
        let statePath = ""
        let stages: NexusArchitectProgressStage[] = []
        let logs: string[] = ["[Nexus-Orchestrator] Warming up synthesis engine..."]

        const emitProgress = (status: "running" | "success" | "failed") => {
            onProgress?.(
                createProgressSnapshot({
                    input,
                    logs,
                    stages,
                    status,
                    exitCode,
                    statePath,
                }),
            )
        }

        emitProgress("running")

        const handleStderrLine = (line: string) => {
            const trimmed = line.trim()
            if (!trimmed) return
            stderr += `${line}\n`

            const stageEvent = parseStageEventLine(trimmed)
            if (stageEvent) {
                stages = upsertStage(stages, stageEvent)
                const stageLabel = stageEvent.label || stageEvent.id || "unknown"
                const stageStatus = stageEvent.status || "event"
                const duration = stageEvent.duration_ms != null
                    ? ` (${(stageEvent.duration_ms / 1000).toFixed(2)}s)`
                    : ""
                if (stageStatus === "failed") {
                    console.error(
                        `[Nexus-Stage] FAILED     ${stageLabel}${duration}`,
                    )
                } else {
                    console.log(
                        `[Nexus-Stage] ${stageStatus.toUpperCase().padEnd(10)} ${stageLabel}${duration}`,
                    )
                }
                if (stageEvent.detail) {
                    console.log(`  └─ ${stageEvent.detail}`)
                }
                emitProgress("running")
                return
            }

            if (trimmed.includes("Using isolated state file:")) {
                statePath = trimmed.split("Using isolated state file:")[1]?.trim() || statePath
            }

            // Print ALL stderr to Node.js console for full diagnostic trace
            console.log(`[Nexus-Log] ${trimmed}`)

            // Capture ALL stderr output for complete diagnostic traces in the UI
            logs = [...logs, trimmed].slice(-150)
            emitProgress("running")
        }

        const flushLines = (
            buffer: string,
            handler: (line: string) => void,
        ): string => {
            const normalized = buffer.replace(/\r/g, "")
            const lines = normalized.split("\n")
            const rest = lines.pop() ?? ""
            for (const line of lines) {
                handler(line)
            }
            return rest
        }

        const timeout = setTimeout(() => {
            if (settled) return
            exitCode = null
            logs = [...logs, `[Nexus-Orchestrator] Timeout after ${timeoutMs} ms`].slice(-80)
            emitProgress("failed")
            child.kill()
        }, timeoutMs)

        child.stdout.setEncoding("utf8")
        child.stderr.setEncoding("utf8")

        child.stdout.on("data", (chunk: string) => {
            stdout += chunk
            stdoutBuffer += chunk
            stdoutBuffer = flushLines(stdoutBuffer, () => {})
        })

        child.stderr.on("data", (chunk: string) => {
            stderrBuffer += chunk
            stderrBuffer = flushLines(stderrBuffer, handleStderrLine)
        })

        child.on("error", (error) => {
            if (settled) return
            settled = true
            clearTimeout(timeout)
            reject(new Error(`Nexus-Orchestrator command failed: ${error.message}`))
        })

        child.on("close", (code) => {
            if (settled) return
            settled = true
            clearTimeout(timeout)
            exitCode = code
            if (stderrBuffer.trim()) handleStderrLine(stderrBuffer)
            if (stdoutBuffer.trim()) stdout += stdoutBuffer

            // Print completion summary to Node.js console
            const completedStages = stages.filter((s) => s.status === "completed").length
            const totalStages = stages.length
            console.log(`\n${"═".repeat(60)}`)
            console.log(`[Nexus-Bridge] Process exited with code ${code}`)
            console.log(`[Nexus-Bridge] Stages: ${completedStages}/${totalStages} completed`)
            if (statePath) console.log(`[Nexus-Bridge] State: ${statePath}`)
            console.log(`[Nexus-Bridge] Stdout length: ${stdout.length} chars`)
            console.log(`[Nexus-Bridge] Stderr length: ${stderr.length} chars`)
            console.log(`${"═".repeat(60)}\n`)

            if (code && !stdout.trim()) {
                reject(new Error(`Nexus-Orchestrator failed with exit code ${code}. Check internal logs for details.`))
                return
            }
            resolve({ stdout, stderr, exitCode: code, stages, logs, statePath })
        })
    })
}

export async function runNexusArchitectAdapter(
    input: NexusArchitectAdapterInput,
    options: RunNexusArchitectAdapterOptions = {},
): Promise<NexusArchitectAdapterOutput> {
    const projectRoot = getNexusArchitectRoot()
    const _capabilityStatus = await getVectorworksCapabilityStatus(projectRoot)
    
    const bridgeScript = path.join(projectRoot, "forge_core", "build_agent", "adapter_entry.py")
    const pythonCommand = await resolvePythonCommand(projectRoot)
    const timeoutMs = Number(process.env.OPENBIMFORGE_BRIDGE_TIMEOUT_MS || 1800000) // 30 minutes default

    const payloadPath = path.join(
        os.tmpdir(),
        `nexus_payload_${Date.now()}.json`,
    )
    const payload = {
        mode: "live",
        query: input.query,
        chat_history: input.chatHistory || "",
        session_id: input.sessionId || "",
        model_hint: input.modelHint || "",
        llm_config: input.llmConfig || {},
        execution_config: {
            ...(input.executionConfig || {}),
        },
    }

    const pipelineStart = Date.now()
    try {
        const queryPreview = input.query.slice(0, 80).replace(/\n/g, " ")
        console.log(`\n${"─".repeat(60)}`)
        console.log(`[Nexus-Bridge] Pipeline start`)
        console.log(`  └─ query: "${queryPreview}${input.query.length > 80 ? "..." : ""}"`)
        console.log(`  └─ model: ${input.llmConfig?.modelId || "default"} (${input.llmConfig?.provider || "unknown"})`)
        console.log(`  └─ mode: ${input.executionConfig?.executionMode || "dry-run"}`)
        console.log(`  └─ session: ${input.sessionId || "none"}`)
        console.log(`  └─ payload: ${payloadPath}`)
        console.log(`${"─".repeat(60)}\n`)
        await fs.writeFile(payloadPath, JSON.stringify(payload), "utf-8")
        
        const result = await spawnBridgeProcess(
            pythonCommand,
            [bridgeScript, "--payload-json", payloadPath],
            projectRoot,
            {
                ...process.env,
                PROJECT_ROOT: projectRoot,
                OPENBIMFORGE_ROOT: projectRoot,
                OPENBIMFORGE_RUNTIME_ROOT: path.join(projectRoot, "forge_runtime"),
                HF_HOME: path.join(projectRoot, ".cache"),
                PYTHONIOENCODING: "utf-8",
                ...(input.executionConfig?.mepMode
                    ? { OPENBIMFORGE_MEP_MODE: input.executionConfig.mepMode }
                    : {}),
            },
            timeoutMs,
            input,
            options.onProgress,
        )

        // Log final result to Node.js console
        console.log(`[Nexus-Bridge] Stdout preview:\n${result.stdout.slice(0, 500)}`)

        let parsed: Record<string, unknown>
        try {
            parsed = parseBridgeJson(result.stdout)
        } catch (error) {
            const errMsg = error instanceof Error ? error.message : "Parse Error"
            console.error(`[Nexus-Bridge] JSON parse FAILED: ${errMsg}`)
            console.error(`[Nexus-Bridge] Stdout (raw, first 1000 chars):\n${result.stdout.slice(0, 1000)}`)
            console.error(`[Nexus-Bridge] Stderr (last 500 chars):\n${result.stderr.slice(-500)}`)
            return buildCommandFailureOutput(errMsg, result.stderr, input, {
                stages: result.stages,
                logs: result.logs,
                statePath: result.statePath,
                exitCode: result.exitCode,
            })
        }

        const diagnostics = (parsed.diagnostics as Record<string, unknown>) || {}
        diagnostics.bridge_logs = result.logs
        diagnostics.progress_stages = result.stages
        diagnostics.bridge_exit_code = result.exitCode

        const live = (parsed.live as Record<string, unknown>) || {}
        if (live.quality && diagnostics.quality === undefined) {
            diagnostics.quality = live.quality
        }
        if (live.requirement_slots && diagnostics.requirement_slots === undefined) {
            diagnostics.requirement_slots = live.requirement_slots
        }
        if (live.typology_key && diagnostics.typology_key === undefined) {
            diagnostics.typology_key = live.typology_key
        }
        if (live.mep && diagnostics.mep === undefined) {
            diagnostics.mep = live.mep
        }

        // Map backend Python error message to UI format
        if (diagnostics.error && !diagnostics.live_error) {
            diagnostics.live_error = diagnostics.error
        }

        const finalOk = parsed.ok === true
        const pipelineDuration = ((Date.now() - pipelineStart) / 1000).toFixed(1)
        const completedStages = result.stages.filter((s) => s.status === "completed").length
        console.log(`\n${"═".repeat(60)}`)
        console.log(`[Nexus-Bridge] Pipeline ${finalOk ? "SUCCESS" : "FAILED"} in ${pipelineDuration}s`)
        console.log(`  └─ stages: ${completedStages}/${result.stages.length} completed`)
        if (result.statePath) console.log(`  └─ state: ${result.statePath}`)
        if (diagnostics.live_error) console.log(`  └─ error: ${diagnostics.live_error}`)
        console.log(`${"═".repeat(60)}\n`)

        return {
            ok: finalOk,
            mode: parsed.mode === "live" ? "live" : "mock",
            source: "nexus-architect-bridge",
            unifiedBimJson: (parsed.unified_bim_json as Record<string, unknown>) || {},
            diagnostics,
            raw: parsed,
        }
    } finally {
        await fs.unlink(payloadPath).catch(() => {})
    }
}
