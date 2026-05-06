import { promises as fs } from "fs"
import path from "path"
import { NextResponse } from "next/server"
import {
    getNexusArchitectRoot,
    getNexusRuntimeRoot,
} from "@/lib/bim/openbimforge-paths"

export const runtime = "nodejs"

type RuntimeFile = {
    name: string
    path: string
    updatedAt: string
    size: number
}

const STALE_LOCK_MS = 10 * 60 * 1000

/**
 * Returns the root directory for Nexus Transit-Payloads.
 */
function getNexusPayloadRoot(): string {
    return getNexusRuntimeRoot("runtime_handoffs")
}

/**
 * Builds the synthesis engine execution script for the BIM Synthesis Workbench.
 */
function buildSynthesisScript(once = false): string {
    const projectRoot = getNexusArchitectRoot()
    const payloadRoot = getNexusPayloadRoot()
    return [
        "import sys",
        "",
        `project_root = r"${projectRoot}"`,
        "if project_root not in sys.path:",
        "    sys.path.insert(0, project_root)",
        "",
        "from forge_core.build_agent.vectorworks_watch_runner import start_vectorworks_runner",
        "",
        once
            ? `start_vectorworks_runner(r"${payloadRoot}", 3.0, once=True)`
            : `start_vectorworks_runner(r"${payloadRoot}", 3.0)`,
    ].join("\n")
}

async function listFiles(root: string): Promise<RuntimeFile[]> {
    try {
        const entries = await fs.readdir(root, { withFileTypes: true })
        const files = await Promise.all(
            entries
                .filter((entry) => entry.isFile())
                .map(async (entry) => {
                    const filePath = path.join(root, entry.name)
                    const stat = await fs.stat(filePath)
                    return {
                        name: entry.name,
                        path: filePath,
                        updatedAt: stat.mtime.toISOString(),
                        size: stat.size,
                    }
                }),
        )
        return files.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    } catch {
        return []
    }
}

async function readJsonFile(filePath: string): Promise<Record<string, unknown> | null> {
    try {
        const raw = await fs.readFile(filePath, "utf8")
        return JSON.parse(raw) as Record<string, unknown>
    } catch {
        return null
    }
}

export async function GET() {
    try {
        const payloadRoot = getNexusPayloadRoot()
        const files = await listFiles(payloadRoot)
        
        // Filter for academic Transit-Payloads
        const payloads = files.filter(
            (file) =>
                file.name.startsWith("nexus_payload_") &&
                file.name.endsWith(".json") &&
                !file.name.endsWith(".result.json") &&
                !file.name.endsWith(".fix-request.json"),
        )
        
        const running = files.filter((file) => file.name.endsWith(".running"))
        const done = files.filter((file) => file.name.endsWith(".done"))
        const failed = files.filter((file) => file.name.endsWith(".failed"))
        const results = files.filter((file) => file.name.endsWith(".result.json"))

        const pending = payloads.filter((payload) => {
            const resultName = payload.name.replace(/\.json$/, ".result.json")
            const doneName = `${payload.name}.done`
            const failedName = `${payload.name}.failed`
            const runningName = `${payload.name}.running`
            return !files.some((file) => {
                if ([resultName, doneName, failedName].includes(file.name)) {
                    return true
                }
                if (file.name !== runningName) {
                    return false
                }
                return Date.now() - Date.parse(file.updatedAt) <= STALE_LOCK_MS
            })
        })

        return NextResponse.json({
            ok: true,
            payloadRoot,
            nexusLegacySync: await readJsonFile(path.join(payloadRoot, "openbimforge_legacy_bridge_status.json")),
            watchSynthesisScript: buildSynthesisScript(false),
            runOnceSynthesisScript: buildSynthesisScript(true),
            counts: {
                payloads: payloads.length,
                pending: pending.length,
                running: running.length,
                done: done.length,
                failed: failed.length,
                results: results.length,
            },
            latest: {
                payload: payloads[0] ?? null,
                pending: pending[0] ?? null,
                running: running[0] ?? null,
                done: done[0] ?? null,
                failed: failed[0] ?? null,
                result: results[0] ?? null,
            },
        })
    } catch (err) {
        // Suppress 500 spam from polling by returning 200 with ok: false
        return NextResponse.json({ ok: false, error: String(err) })
    }
}
