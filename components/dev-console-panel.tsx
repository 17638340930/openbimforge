"use client"

import {
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Clock3,
    LoaderCircle,
    Terminal,
    Trash2,
    XCircle,
} from "lucide-react"
import { useState } from "react"
import { cn } from "@/lib/utils"
import { useDevLogStore, type DevLogSnapshot, type DevLogEntry } from "@/contexts/dev-log-store"

/* ---------- Helpers ---------- */

function formatTime(ts: number) {
    return new Date(ts).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    })
}

function formatDuration(ms?: number) {
    if (ms == null) return ""
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(2)}s`
}

function StatusIcon({ status }: { status?: string }) {
    if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
    if (status === "failed") return <XCircle className="h-3.5 w-3.5 text-red-400" />
    if (status === "running") return <LoaderCircle className="h-3.5 w-3.5 animate-spin text-sky-400" />
    return <Clock3 className="h-3.5 w-3.5 text-zinc-500" />
}

function statusColor(status?: string) {
    if (status === "completed") return "text-emerald-400"
    if (status === "failed") return "text-red-400"
    if (status === "running") return "text-sky-400"
    return "text-zinc-500"
}

/* ---------- Stage Detail Row ---------- */

function StageRow({ entry }: { entry: DevLogEntry }) {
    return (
        <div className="flex items-start gap-3 py-1.5 px-3 rounded hover:bg-white/5 transition-colors">
            <StatusIcon status={entry.status} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className={cn("text-xs font-mono font-medium", statusColor(entry.status))}>
                        {entry.stageLabel || entry.stageId || "unknown"}
                    </span>
                    {entry.duration_ms != null && (
                        <span className="text-[10px] text-zinc-500 font-mono tabular-nums">
                            {formatDuration(entry.duration_ms)}
                        </span>
                    )}
                    <span className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded font-mono",
                        entry.status === "completed" ? "bg-emerald-900/40 text-emerald-400" :
                            entry.status === "failed" ? "bg-red-900/40 text-red-400" :
                                entry.status === "running" ? "bg-sky-900/40 text-sky-400" :
                                    "bg-zinc-800 text-zinc-500",
                    )}>
                        {entry.status || "pending"}
                    </span>
                </div>
                {entry.detail && (
                    <p className="text-[11px] text-zinc-400 mt-0.5 leading-relaxed break-all">
                        {entry.detail}
                    </p>
                )}
            </div>
            <span className="text-[10px] text-zinc-600 font-mono shrink-0">
                {formatTime(entry.timestamp)}
            </span>
        </div>
    )
}

/* ---------- Raw Log Entry ---------- */

function RawLogRow({ entry }: { entry: DevLogEntry }) {
    const [expanded, setExpanded] = useState(false)
    const logs = entry.logs || []

    return (
        <div className="py-1.5 px-3">
            <button
                type="button"
                className="flex items-center gap-2 w-full text-left hover:bg-white/5 rounded px-1 py-0.5 transition-colors"
                onClick={() => setExpanded(!expanded)}
            >
                <Terminal className="h-3 w-3 text-zinc-500" />
                <span className="text-[11px] text-zinc-400 font-mono">
                    {logs.length} log lines
                </span>
                <span className="text-[10px] text-zinc-600 font-mono ml-auto">
                    {formatTime(entry.timestamp)}
                </span>
                {expanded ? (
                    <ChevronDown className="h-3 w-3 text-zinc-500" />
                ) : (
                    <ChevronRight className="h-3 w-3 text-zinc-500" />
                )}
            </button>
            {expanded && (
                <pre className="mt-1 ml-5 p-2 bg-black/40 rounded text-[10px] text-zinc-300 font-mono leading-relaxed max-h-60 overflow-auto whitespace-pre-wrap break-all">
                    {logs.join("\n")}
                </pre>
            )}
        </div>
    )
}

/* ---------- Snapshot Card ---------- */

function SnapshotCard({ snapshot }: { snapshot: DevLogSnapshot }) {
    const [expanded, setExpanded] = useState(true)

    const overallStatus = snapshot.status
    const stageEntries = snapshot.entries.filter((e) => e.type === "stage-event")
    const rawEntries = snapshot.entries.filter((e) => e.type === "raw")

    return (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/80 overflow-hidden">
            {/* Header */}
            <button
                type="button"
                className="flex items-center gap-3 w-full px-4 py-3 hover:bg-zinc-800/50 transition-colors text-left"
                onClick={() => setExpanded(!expanded)}
            >
                {overallStatus === "running" ? (
                    <LoaderCircle className="h-4 w-4 animate-spin text-sky-400" />
                ) : overallStatus === "failed" ? (
                    <XCircle className="h-4 w-4 text-red-400" />
                ) : (
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                )}
                <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-zinc-200 truncate">
                        {snapshot.title}
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-zinc-500 font-mono mt-0.5">
                        <span>{formatTime(snapshot.startedAt)}</span>
                        {snapshot.mode && <span>mode: {snapshot.mode}</span>}
                        {snapshot.agent && <span>agent: {snapshot.agent}</span>}
                        <span>{stageEntries.length} stages</span>
                        {snapshot.finishedAt && (
                            <span>
                                duration:{" "}
                                {formatDuration(
                                    snapshot.finishedAt - snapshot.startedAt,
                                )}
                            </span>
                        )}
                    </div>
                </div>
                {expanded ? (
                    <ChevronDown className="h-4 w-4 text-zinc-500" />
                ) : (
                    <ChevronRight className="h-4 w-4 text-zinc-500" />
                )}
            </button>

            {/* Body */}
            {expanded && (
                <div className="border-t border-zinc-800">
                    {/* Stage entries */}
                    {stageEntries.length > 0 && (
                        <div className="py-2">
                            <div className="px-4 py-1 text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                                Stage Events
                            </div>
                            {stageEntries.map((entry) => (
                                <StageRow key={entry.id} entry={entry} />
                            ))}
                        </div>
                    )}

                    {/* Raw log entries */}
                    {rawEntries.length > 0 && (
                        <div className="py-2 border-t border-zinc-800/50">
                            <div className="px-4 py-1 text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                                Raw Logs
                            </div>
                            {rawEntries.map((entry) => (
                                <RawLogRow key={entry.id} entry={entry} />
                            ))}
                        </div>
                    )}

                    {/* Raw payloads toggle */}
                    <details className="border-t border-zinc-800/50">
                        <summary className="px-4 py-2 text-[10px] text-zinc-500 uppercase tracking-wider font-semibold cursor-pointer hover:bg-white/5">
                            Raw Payloads ({snapshot.rawPayloads.length})
                        </summary>
                        <div className="px-4 pb-3 max-h-80 overflow-auto">
                            {snapshot.rawPayloads.map((p, i) => (
                                <pre
                                    key={`${p.timestamp}-${i}`}
                                    className="mb-2 p-2 bg-black/40 rounded text-[10px] text-zinc-400 font-mono leading-relaxed whitespace-pre-wrap break-all overflow-auto max-h-40"
                                >
                                    {JSON.stringify(p.data, null, 2)}
                                </pre>
                            ))}
                        </div>
                    </details>
                </div>
            )}
        </div>
    )
}

/* ---------- Exported Panel ---------- */

export function DevConsolePanel() {
    const { snapshots, clearLogs } = useDevLogStore()
    const reversed = [...snapshots].reverse()

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-zinc-400" />
                    <h3 className="text-sm font-semibold text-zinc-200">
                        Developer Console
                    </h3>
                    <span className="text-[10px] text-zinc-500 font-mono">
                        {snapshots.length} session{snapshots.length !== 1 ? "s" : ""}
                    </span>
                </div>
                {snapshots.length > 0 && (
                    <button
                        type="button"
                        onClick={clearLogs}
                        className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
                    >
                        <Trash2 className="h-3 w-3" />
                        Clear
                    </button>
                )}
            </div>

            {/* Snapshot list */}
            {reversed.length === 0 ? (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-8 text-center">
                    <Terminal className="h-8 w-8 text-zinc-700 mx-auto mb-3" />
                    <p className="text-sm text-zinc-500">
                        No execution logs yet.
                    </p>
                    <p className="text-xs text-zinc-600 mt-1">
                        Run a BIM synthesis from the chat panel to see detailed
                        stage events here.
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {reversed.map((snapshot) => (
                        <SnapshotCard
                            key={snapshot.sessionId}
                            snapshot={snapshot}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}
