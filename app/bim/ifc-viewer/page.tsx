import { promises as fs } from "fs"
import Link from "next/link"
import {
    getNexusRuntimeRoots,
    isPathInsideRoots,
} from "@/lib/bim/openbimforge-paths"

export const runtime = "nodejs"

function buildArtifactUrl(filePath: string, inline = true): string {
    return `/api/bim/forge-architect-artifact?path=${encodeURIComponent(filePath)}${
        inline ? "&mode=inline" : ""
    }`
}

function getAllowedRoots(): string[] {
    return getNexusRuntimeRoots(["runtime_handoffs", "runtime_outputs", "runtime_artifacts"])
}

function isAllowedPath(targetPath: string): boolean {
    return isPathInsideRoots(targetPath, getAllowedRoots())
}

function getIfcPreviewStats(text: string) {
    const count = (token: string) =>
        (text.match(new RegExp(token, "gi")) || []).length
    return {
        building: count("IFCBUILDING\\("),
        storey: count("IFCBUILDINGSTOREY\\("),
        wall: count("IFCWALL"),
        slab: count("IFCSLAB"),
        roof: count("IFCROOF"),
        space: count("IFCSPACE"),
    }
}

function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function readResultJson(resultPath?: string): Promise<{ ok: boolean; ifc_ready?: boolean; vwx_path?: string; quality_score?: number } | null> {
    if (!resultPath) return null
    try {
        if (!isAllowedPath(resultPath)) return null
        const raw = await fs.readFile(resultPath, "utf-8")
        const parsed = JSON.parse(raw)
        return {
            ok: parsed.ok === true,
            ifc_ready: parsed.artifacts?.ifc_ready,
            vwx_path: parsed.artifacts?.vwx_path,
            quality_score: parsed.result?.execution_summary?.quality_score,
        }
    } catch {
        return null
    }
}

export default async function IfcViewerPage({
    searchParams,
}: {
    searchParams: Promise<{ path?: string; result?: string }>
}) {
    const params = await searchParams
    const filePath = params.path || ""
    const resultPath = params.result || ""

    if (!filePath) {
        return (
            <main className="min-h-screen bg-zinc-950 p-8 text-zinc-50">
                <div className="mx-auto max-w-4xl rounded-3xl border border-zinc-800 bg-zinc-900/70 p-8">
                    <h1 className="text-2xl font-semibold">Nexus Asset Viewer</h1>
                    <p className="mt-3 text-zinc-300">IFC path parameter is missing in orchestration context.</p>
                </div>
            </main>
        )
    }

    const artifactUrl = buildArtifactUrl(filePath, true)
    let content = ""
    let error = ""
    try {
        if (!isAllowedPath(filePath)) {
            throw new Error("IFC path is outside allowed Nexus runtime directories.")
        }
        content = await fs.readFile(filePath, "utf-8")
    } catch (err) {
        error = err instanceof Error ? err.message : "Unable to read Digital BIM Asset (IFC)."
    }

    const resultSummary = await readResultJson(resultPath)
    const stats = getIfcPreviewStats(content)
    const preview = content.slice(0, 18000)
    let fileSize = ""
    try {
        const stat = await fs.stat(filePath)
        fileSize = formatFileSize(stat.size)
    } catch { /* ignore */ }

    return (
        <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#164e63,transparent_35%),linear-gradient(135deg,#09090b,#18181b_60%,#111827)] p-5 text-zinc-50 md:p-10">
            <div className="mx-auto max-w-6xl space-y-5">
                <section className="rounded-[2rem] border border-cyan-300/20 bg-zinc-950/70 p-6 shadow-2xl shadow-cyan-950/30 backdrop-blur">
                    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                        <div>
                            <p className="text-sm uppercase tracking-[0.3em] text-cyan-200/80 font-bold">
                                Nexus Multi-Agent Framework
                            </p>
                            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
                                Digital BIM Asset Viewer (IFC)
                            </h1>
                            <p className="mt-2 break-all text-xs font-mono text-zinc-400 bg-black/30 p-2 rounded-lg">
                                {filePath}
                            </p>
                            {fileSize ? <p className="mt-2 text-xs text-zinc-500 font-medium uppercase tracking-widest">Asset Size: {fileSize}</p> : null}
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {resultSummary ? (
                                <Link
                                    href={resultPath ? `/bim/nexus-status?path=${encodeURIComponent(resultPath)}` : "#"}
                                    className="rounded-full border border-cyan-600 px-4 py-2 text-xs font-bold text-cyan-200 hover:bg-cyan-950 transition-colors"
                                >
                                    Orchestration Details
                                </Link>
                            ) : null}
                            {resultSummary?.vwx_path ? (
                                <Link
                                    href={buildArtifactUrl(resultSummary.vwx_path, false)}
                                    className="rounded-full border border-zinc-600 px-4 py-2 text-xs font-bold text-zinc-100 hover:bg-zinc-800 transition-colors"
                                >
                                    Export VWX
                                </Link>
                            ) : null}
                            <Link
                                href={buildArtifactUrl(filePath, false)}
                                className="rounded-full bg-cyan-300 px-4 py-2 text-xs font-bold text-zinc-950 hover:bg-cyan-200 transition-transform active:scale-95"
                            >
                                Export IFC Asset
                            </Link>
                            <Link
                                href={artifactUrl}
                                className="rounded-full border border-zinc-600 px-4 py-2 text-xs font-bold text-zinc-100 hover:bg-zinc-800 transition-colors"
                            >
                                RAW Semantic View
                            </Link>
                        </div>
                    </div>
                    {resultSummary ? (
                        <div className="mt-4 flex flex-wrap gap-3 border-t border-cyan-300/10 pt-4">
                            <div className="text-xs font-bold uppercase tracking-widest text-zinc-400">
                                Synthesis: <span className={resultSummary.ok ? "text-green-400" : "text-red-400"}>{resultSummary.ok ? "SUCCESS" : "FAILURE"}</span>
                            </div>
                            {resultSummary.quality_score != null ? (
                                <div className="text-xs font-bold uppercase tracking-widest text-zinc-400">
                                    Quality: <span className="text-cyan-200">{resultSummary.quality_score}</span>/100
                                </div>
                            ) : null}
                            {resultSummary.ifc_ready != null ? (
                                <div className="text-xs font-bold uppercase tracking-widest text-zinc-400">
                                    Asset: <span className={resultSummary.ifc_ready ? "text-green-400" : "text-yellow-400"}>{resultSummary.ifc_ready ? "READY" : "MISSING"}</span>
                                </div>
                            ) : null}
                        </div>
                    ) : null}
                </section>

                <section className="grid gap-3 md:grid-cols-6">
                    {Object.entries(stats).map(([key, value]) => (
                        <div
                            key={key}
                            className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4 backdrop-blur-sm"
                        >
                            <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">
                                {key}
                            </div>
                            <div className="mt-2 text-2xl font-semibold text-cyan-50">
                                {value}
                            </div>
                        </div>
                    ))}
                </section>

                <section className="rounded-[2rem] border border-zinc-800 bg-zinc-950/80 p-6 shadow-xl">
                    <h2 className="text-lg font-semibold flex items-center gap-2">
                        <span className="w-2 h-2 bg-cyan-400 rounded-full"></span>
                        Semantic Asset Preview
                    </h2>
                    <p className="mt-1 text-xs text-zinc-500 italic">
                        Visualizing synthesized IFC metadata. 3D Constructive View (Three.js/web-ifc) integration pending.
                    </p>
                    {error ? (
                        <pre className="mt-4 overflow-auto rounded-2xl bg-red-950/40 p-4 text-xs text-red-200 border border-red-500/20">
                            {error}
                        </pre>
                    ) : (
                        <pre className="mt-4 max-h-[60vh] overflow-auto rounded-2xl bg-black/60 p-5 text-[10px] font-mono leading-relaxed text-zinc-400">
                            {preview}
                        </pre>
                    )}
                </section>
            </div>
        </main>
    )
}
