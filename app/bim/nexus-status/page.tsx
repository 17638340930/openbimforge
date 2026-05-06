import { promises as fs } from "fs"
import Link from "next/link"
import {
    getNexusRuntimeRoots,
    isPathInsideRoots,
} from "@/lib/bim/openbimforge-paths"

export const runtime = "nodejs"

function getAllowedRoots(): string[] {
    return getNexusRuntimeRoots(["runtime_handoffs", "runtime_artifacts"])
}

function isAllowedPath(targetPath: string): boolean {
    return isPathInsideRoots(targetPath, getAllowedRoots())
}

function artifactLink(filePath: string, inline = false): string {
    return `/api/bim/forge-architect-artifact?path=${encodeURIComponent(filePath)}${
        inline ? "&mode=inline" : ""
    }`
}

function statusLabel(value: unknown): string {
    return value ? "Synthesized / Complete" : "Pending / Incomplete"
}

export default async function NexusStatusPage({
    searchParams,
}: {
    searchParams: Promise<{ path?: string }>
}) {
    const params = await searchParams
    const resultPath = params.path || ""
    let data: Record<string, any> | null = null
    let error = ""

    try {
        if (!resultPath) throw new Error("Synthesis result path is missing.")
        if (!isAllowedPath(resultPath)) {
            throw new Error("Result path is outside allowed Nexus runtime directories.")
        }
        data = JSON.parse(await fs.readFile(resultPath, "utf-8"))
    } catch (err) {
        error = err instanceof Error ? err.message : "Unable to retrieve synthesis results."
    }

    const artifacts = data?.artifacts || {}
    const result = data?.result || {}
    const attempts = Array.isArray(result.attempts) ? result.attempts : []
    const ifcPath = String(artifacts.ifc_path || "")
    const vwxPath = String(artifacts.vwx_path || "")
    const quality = result.execution_summary?.validation?.quality || {}
    const degradations = result.execution_summary?.validation?.degradations || []
    const fixer = data?.fixer || {}

    return (
        <main className="min-h-screen bg-slate-950 p-5 text-slate-50 md:p-10 font-sans">
            <div className="mx-auto max-w-6xl space-y-5">
                <section className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-8 shadow-2xl">
                    <p className="text-sm uppercase tracking-[0.3em] text-cyan-300 font-bold">
                        Nexus Multi-Agent Framework
                    </p>
                    <h1 className="mt-2 text-4xl font-bold tracking-tight">
                        Orchestration Synthesis Status
                    </h1>
                    <p className="mt-4 break-all text-xs font-mono text-slate-500 bg-black/30 p-2 rounded-lg">
                        {resultPath}
                    </p>
                </section>

                {error ? (
                    <section className="rounded-2xl border border-red-500/40 bg-red-950/40 p-4 text-red-200">
                        <b>Diagnostic Error:</b> {error}
                    </section>
                ) : null}

                {data ? (
                    <>
                        <section className="grid gap-4 md:grid-cols-5">
                            {[
                                ["Transit-Payload", statusLabel(data.handoff_path)],
                                ["Digital VWX", statusLabel(vwxPath)],
                                ["Digital IFC", statusLabel(artifacts.ifc_ready)],
                                ["Synthesis Attempts", String(attempts.length)],
                                [
                                    "Quality Index",
                                    quality.quality_score
                                        ? `${quality.quality_score}/100`
                                        : "-",
                                ],
                            ].map(([label, value]) => (
                                <div
                                    key={label}
                                    className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-sm"
                                >
                                    <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">
                                        {label}
                                    </div>
                                    <div className="mt-2 text-lg font-semibold text-cyan-50">
                                        {value}
                                    </div>
                                </div>
                            ))}
                        </section>

                        <div className="grid gap-5 md:grid-cols-2">
                            <section className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
                                <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                                    <span className="w-2 h-2 bg-cyan-400 rounded-full"></span>
                                    Digital BIM Assets
                                </h2>
                                <div className="space-y-4 text-sm">
                                    {vwxPath ? (
                                        <div className="p-3 bg-black/40 rounded-xl border border-slate-800">
                                            <p className="text-xs text-slate-500 mb-1 font-mono">VWX (Native Synthesis)</p>
                                            <Link
                                                className="text-cyan-300 font-bold hover:underline break-all"
                                                href={artifactLink(vwxPath)}
                                            >
                                                Export VWX Asset
                                            </Link>
                                        </div>
                                    ) : null}
                                    {ifcPath ? (
                                        <div className="p-3 bg-black/40 rounded-xl border border-slate-800">
                                            <p className="text-xs text-slate-500 mb-1 font-mono">IFC (Interoperable Synthesis)</p>
                                            <div className="flex flex-col gap-2">
                                                <Link
                                                    className="text-cyan-300 font-bold hover:underline break-all"
                                                    href={artifactLink(ifcPath)}
                                                >
                                                    Export IFC Asset
                                                </Link>
                                                <Link
                                                    className="inline-flex items-center justify-center rounded-lg bg-cyan-500/10 px-4 py-2 text-xs font-bold text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-colors"
                                                    href={`/bim/ifc-viewer?path=${encodeURIComponent(ifcPath)}`}
                                                >
                                                    Launch Web IFC-Viewer
                                                </Link>
                                            </div>
                                        </div>
                                    ) : null}
                                    {artifacts.ifc_message ? (
                                        <p className="text-slate-400 italic text-xs p-2">
                                            {artifacts.ifc_message}
                                        </p>
                                    ) : null}
                                </div>
                            </section>

                            <section className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
                                <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                                    <span className="w-2 h-2 bg-amber-400 rounded-full"></span>
                                    Diagnostic Agent Log
                                </h2>
                                {fixer.fix_request_path ? (
                                    <div className="p-3 bg-amber-950/20 rounded-xl border border-amber-500/20">
                                        <p className="text-[10px] text-amber-500 font-bold uppercase mb-1">Diagnostic Request Active</p>
                                        <p className="text-xs font-mono text-amber-100 break-all">{fixer.fix_request_path}</p>
                                    </div>
                                ) : (
                                    <p className="text-sm text-slate-500 italic">
                                        No synthesis disruptions detected. Diagnostic Agent idle.
                                    </p>
                                )}
                                {Array.isArray(degradations) && degradations.length > 0 ? (
                                    <div className="mt-4">
                                        <p className="text-[10px] text-slate-500 font-bold uppercase mb-1">Functional Degradations</p>
                                        <pre className="max-h-48 overflow-auto rounded-xl bg-black/50 p-3 text-[10px] font-mono text-slate-300">
                                            {JSON.stringify(degradations, null, 2)}
                                        </pre>
                                    </div>
                                ) : null}
                            </section>
                        </div>

                        <section className="rounded-[2rem] border border-slate-800 bg-slate-900/80 p-6 shadow-xl">
                            <h2 className="text-xl font-bold mb-4">Orchestration Payload (JSON)</h2>
                            <pre className="max-h-[50vh] overflow-auto rounded-xl bg-black/50 p-4 text-[10px] font-mono text-slate-400 leading-relaxed">
                                {JSON.stringify(data, null, 2)}
                            </pre>
                        </section>
                    </>
                ) : null}
            </div>
        </main>
    )
}
