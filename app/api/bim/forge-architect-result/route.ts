import { promises as fs } from "fs"
import path from "path"
import { getNexusRuntimeRoots, isPathInsideRoots } from "@/lib/bim/openbimforge-paths"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

const vmWaitLogCache = new Map<string, string>()

function getAllowedRoots(): string[] {
    return getNexusRuntimeRoots([
        "runtime_handoffs",
        "runtime_artifacts",
    ])
}

function isAllowedPath(targetPath: string): boolean {
    return isPathInsideRoots(targetPath, getAllowedRoots())
}

async function fileExists(filePath: string): Promise<boolean> {
    try {
        await fs.access(filePath)
        return true
    } catch {
        return false
    }
}

async function readJsonFile(filePath: string): Promise<Record<string, unknown> | null> {
    try {
        return JSON.parse(await fs.readFile(filePath, "utf-8")) as Record<string, unknown>
    } catch {
        return null
    }
}

async function logVmWaitState(resultPath: string, errorMessage: string) {
    const payloadPath = resultPath.replace(/\.result\.json$/i, ".json")
    const handoffRoot = path.dirname(resultPath)
    const bridgeStatusPath = path.join(handoffRoot, "openbimforge_legacy_bridge_status.json")
    const bridgeStatus = await readJsonFile(bridgeStatusPath)
    const state = {
        payload: await fileExists(payloadPath),
        running: await fileExists(`${payloadPath}.running`),
        done: await fileExists(`${payloadPath}.done`),
        failed: await fileExists(`${payloadPath}.failed`),
        bridgeStage: String(bridgeStatus?.stage || "missing"),
        bridgePayloadPath: String(bridgeStatus?.payloadPath || ""),
        bridgeError: String(bridgeStatus?.error || ""),
    }

    const signature = JSON.stringify(state)
    if (vmWaitLogCache.get(resultPath) === signature) return
    vmWaitLogCache.set(resultPath, signature)

    console.log(
        [
            "[Nexus-VM-Wait]",
            `result=${path.basename(resultPath)}`,
            `payload=${state.payload ? "yes" : "no"}`,
            `running=${state.running ? "yes" : "no"}`,
            `done=${state.done ? "yes" : "no"}`,
            `failed=${state.failed ? "yes" : "no"}`,
            `bridgeStage=${state.bridgeStage}`,
            state.bridgePayloadPath ? `bridgePayload=${path.basename(state.bridgePayloadPath)}` : "bridgePayload=missing",
            state.bridgeError ? `bridgeError=${state.bridgeError}` : "",
            `read=${errorMessage}`,
        ].filter(Boolean).join(" | "),
    )
}

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url)
    const targetPath = searchParams.get("path")

    if (!targetPath) {
        return NextResponse.json(
            { ok: false, error: "Missing path query parameter." },
            { status: 400 },
        )
    }

    if (!isAllowedPath(targetPath)) {
        return NextResponse.json(
            { ok: false, error: "Requested Digital Asset path is outside the allowed Nexus runtime directories." },
            { status: 403 },
        )
    }

    try {
        const content = await fs.readFile(targetPath, "utf-8")
        return NextResponse.json({
            ok: true,
            path: targetPath,
            data: JSON.parse(content),
            note: "Digital BIM Asset successfully retrieved via Nexus-Orchestrator."
        })
    } catch (error) {
        const message =
            error instanceof Error ? error.message : "Digital Asset is not yet synthesized."
        await logVmWaitState(targetPath, message)
        return NextResponse.json(
            {
                ok: false,
                path: targetPath,
                pending: true,
                error: message,
            },
            { status: 202 },
        )
    }
}
