"use client"

import type { UIMessage } from "ai"
import {
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    LoaderCircle,
    XCircle,
} from "lucide-react"
import ReactMarkdown from "react-markdown"
import { useEffect, useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import { useDevLogStore } from "@/contexts/dev-log-store"
import { getApiEndpoint } from "@/lib/base-path"

/* ---------- Types ---------- */

interface ExecutionStage {
    id?: string
    label?: string
    status?: string
    duration_ms?: number
    detail?: string
}

interface ExecutionLogPayload {
    title?: string
    status?: "success" | "failed" | "running" | string
    mode?: string
    agent?: string
    exit_code?: number | null
    state_path?: string
    result_path?: string
    handoff_path?: string
    stages?: ExecutionStage[]
    logs?: string[]
    summary?: string
}

interface NexusResultData {
    ok?: boolean
    result?: {
        execution_summary?: {
            code_lines?: number
            quality_score?: number
            validation?: {
                quality?: {
                    build_status?: string
                    quality_score?: number
                    native_bim_score?: number
                    degradation_count?: number
                }
            }
        }
    }
    artifacts?: {
        vwx_path?: string
        ifc_path?: string
        ifc_ready?: boolean
        ifc_status?: string
    }
}

/* ---------- Helpers ---------- */

const STAGE_META: Record<string, { icon: string; zh: string }> = {
    // Backend Python stage IDs
    "architect_agent": { icon: "📐", zh: "需求规划" },
    "constructor_agent": { icon: "⚙️", zh: "代码合成" },
    "nexus_transit": { icon: "📦", zh: "载荷交付" },
    "nexus_execute": { icon: "🏗️", zh: "物理构筑" },
    // Legacy / frontend stage IDs
    "stage-0": { icon: "🔍", zh: "需求追问" },
    "stage-1": { icon: "📐", zh: "需求规划" },
    "stage-2": { icon: "⚙️", zh: "代码合成" },
    "stage-3": { icon: "📦", zh: "载荷交付" },
    "stage-4": { icon: "🏗️", zh: "物理构筑" },
}

const RESULT_POLL_INTERVALS_MS = [15000, 30000, 60000, 120000, 300000]

function getStageDisplay(stage: ExecutionStage) {
    const key = stage.id || ""
    const meta = STAGE_META[key]
    return {
        label: meta?.zh || stage.label || stage.id || "未知步骤",
        icon: meta?.icon || "▸",
    }
}

function getMessageText(message: UIMessage): string {
    return message.parts
        ?.map((part: any) => {
            if (part.type === "text") return part.text || ""
            return ""
        })
        .filter(Boolean)
        .join("\n")
}

function splitExecution(text: string) {
    const sections: Array<{
        type: "text" | "execution"
        content: string
        payload?: ExecutionLogPayload
    }> = []
    const pattern = /<execution-log>([\s\S]*?)<\/execution-log>/g
    let lastIndex = 0
    let match: RegExpExecArray | null

    while ((match = pattern.exec(text)) !== null) {
        const before = text.slice(lastIndex, match.index).trim()
        if (before) sections.push({ type: "text", content: before })
        try {
            sections.push({
                type: "execution",
                content: match[1].trim(),
                payload: JSON.parse(match[1].trim()),
            })
        } catch {
            sections.push({ type: "text", content: match[0] })
        }
        lastIndex = pattern.lastIndex
    }

    const tail = text.slice(lastIndex).trim()
    if (tail) sections.push({ type: "text", content: tail })

    // Keep only the LAST execution block (latest snapshot has all stages)
    let lastExecutionIndex = -1
    for (let i = sections.length - 1; i >= 0; i--) {
        if (sections[i].type === "execution") {
            lastExecutionIndex = i
            break
        }
    }

    const filtered = sections.filter((section, index) => {
        if (section.type === "execution") return index === lastExecutionIndex
        if (
            lastExecutionIndex >= 0 &&
            index > lastExecutionIndex &&
            /Nexus\s+(载荷已交付|payload is ready)/i.test(section.content)
        ) {
            return false
        }
        return true
    })
    return filtered.length
        ? filtered
        : [{ type: "text" as const, content: text }]
}

/* ---------- Status icon ---------- */

function StatusDot({ status }: { status?: string }) {
    if (status === "completed")
        return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
    if (status === "failed")
        return <XCircle className="h-3.5 w-3.5 text-red-500" />
    if (status === "running")
        return (
            <LoaderCircle className="h-3.5 w-3.5 animate-spin text-sky-500" />
        )
    return <div className="h-3.5 w-3.5 rounded-full border-2 border-zinc-300" />
}

/* ---------- User-facing ExecutionCard ---------- */

function StageDetailItem({ stage }: { stage: ExecutionStage }) {
    const { label, icon } = getStageDisplay(stage)
    const isCompleted = stage.status === "completed"
    const isRunning = stage.status === "running"

    return (
        <div className="flex items-center gap-2.5 py-1.5 px-2 rounded-lg transition-colors hover:bg-zinc-50/80 group">
            <StatusDot status={stage.status} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                    <span className={cn(
                        "text-[12px] font-medium transition-colors",
                        isCompleted ? "text-zinc-900" : "text-zinc-500",
                        isRunning && "text-blue-600"
                    )}>
                        {icon} {label}
                    </span>
                    {stage.duration_ms && (
                        <span className="text-[10px] text-zinc-400 tabular-nums">
                            {(stage.duration_ms / 1000).toFixed(1)}s
                        </span>
                    )}
                </div>
                {stage.detail && (
                    <p className="text-[11px] text-zinc-400 truncate group-hover:whitespace-normal group-hover:break-words transition-all mt-0.5">
                        {stage.detail}
                    </p>
                )}
            </div>
        </div>
    )
}

export function ExecutionCard({ payload }: { payload: ExecutionLogPayload }) {
    const [expanded, setExpanded] = useState(false)
    const [resultData, setResultData] = useState<NexusResultData | null>(null)
    const stages = payload.stages || []

    const resultStatus = resultData ? (resultData.ok ? "success" : "failed") : null
    const quality = resultData?.result?.execution_summary?.validation?.quality
    const artifacts = resultData?.artifacts || {}
    const displayStages = useMemo(() => {
        if (resultStatus !== "success") return stages

        let hasExecuteStage = false
        const executeDetail = artifacts.ifc_ready
            ? "Vectorworks VM completed physical construction and IFC export."
            : "Vectorworks VM completed physical construction."

        const updatedStages = stages.map((stage) => {
            if (stage.id !== "nexus_execute") return stage
            hasExecuteStage = true
            return {
                ...stage,
                status: "completed",
                detail: executeDetail,
            }
        })

        if (hasExecuteStage) return updatedStages
        return [
            ...updatedStages,
            {
                id: "nexus_execute",
                label: "Nexus-Execute (物理构筑)",
                status: "completed",
                detail: executeDetail,
            },
        ]
    }, [artifacts.ifc_ready, resultStatus, stages])
    const hasRunning = displayStages.length === 0 || displayStages.some((s) => ["running", "pending", "waiting"].includes(String(s.status)))
    const hasFailed = displayStages.some((s) => s.status === "failed")
    const allDone = displayStages.length > 0 && displayStages.every((s) => s.status === "completed")
    const overallStatus = resultStatus || (hasFailed ? "failed" : (hasRunning ? "running" : (allDone ? "success" : "running")))
    const qualityScore = quality?.quality_score ?? resultData?.result?.execution_summary?.quality_score
    const totalDurationMs = displayStages.reduce((acc, stage) => acc + (stage.duration_ms || 0), 0)
    const completedStages = displayStages.filter((stage) => stage.status === "completed").length
    const totalStages = Math.max(displayStages.length, 4)

    useEffect(() => {
        if (!payload.handoff_path || typeof window === "undefined") return
        const stage4 = stages.find((stage) => stage.id === "nexus_execute")
        if (!stage4 || !["waiting", "running"].includes(String(stage4.status))) return

        try {
            const dispatchKey = `openbimforge-vm-dispatched:${payload.handoff_path}`
            if (window.sessionStorage.getItem(dispatchKey)) return
            window.sessionStorage.setItem(dispatchKey, "true")
            window.parent.postMessage(
                {
                    source: "openBIMForgeNext",
                    type: "OPENBIMFORGE_HOST_ACTION",
                    id: `run-pending-${Date.now()}`,
                    action: "runPending",
                    payload: {
                        payloadPath: payload.handoff_path,
                        source: "execution-card",
                    },
                },
                "*",
            )
        } catch (error) {
            console.warn("[openBIMForge] VM dispatch message failed", error)
        }
    }, [payload.handoff_path, stages])

    useEffect(() => {
        if (!payload.result_path || resultData) return

        let cancelled = false
        let attempts = 0
        const maxAttempts = overallStatus === "running" ? RESULT_POLL_INTERVALS_MS.length : 1

        const fetchResult = async () => {
            attempts += 1
            try {
                const response = await fetch(
                    getApiEndpoint(`/api/bim/forge-architect-result?path=${encodeURIComponent(payload.result_path || "")}`),
                    { cache: "no-store" },
                )
                const body = await response.json()
                if (!cancelled && body?.ok && body.data) {
                    setResultData(body.data as NexusResultData)
                    return
                }
            } catch {
                // Result JSON is written by Vectorworks asynchronously.
            }

            if (!cancelled && attempts < maxAttempts) {
                window.setTimeout(
                    fetchResult,
                    RESULT_POLL_INTERVALS_MS[Math.min(attempts - 1, RESULT_POLL_INTERVALS_MS.length - 1)],
                )
            }
        }

        fetchResult()
        return () => {
            cancelled = true
        }
    }, [overallStatus, payload.result_path, resultData])

    return (
        <div className="my-4 rounded-xl border border-zinc-200 bg-white overflow-hidden shadow-sm transition-all hover:shadow-md max-w-[420px]">
            {/* Header */}
            <div 
                className="flex items-center justify-between px-4 py-3 cursor-pointer bg-zinc-50/50"
                onClick={() => setExpanded(!expanded)}
            >
                <div className="flex items-center gap-3">
                    <div className={cn(
                        "w-2 h-2 rounded-full",
                        overallStatus === "success" ? "bg-emerald-500" : overallStatus === "failed" ? "bg-rose-500" : "bg-blue-500 animate-pulse"
                    )} />
                    <span className="text-[13px] font-bold text-zinc-800 tracking-tight">
                        NEXUS BIM 协同编排流
                    </span>
                    <span className={cn(
                        "text-[10px] font-bold px-2 py-0.5 rounded-full tabular-nums",
                        overallStatus === "success" ? "bg-emerald-100 text-emerald-700" : 
                        overallStatus === "failed" ? "bg-rose-100 text-rose-700" : 
                        "bg-blue-100 text-blue-700"
                    )}>
                        {overallStatus === "success" ? `${completedStages}/${totalStages} 阶段已完成` : 
                         overallStatus === "failed" ? "构筑失败" : 
                         `${completedStages}/${totalStages} 正在构筑...`}
                    </span>
                </div>
                {expanded ? <ChevronDown className="w-3.5 h-3.5 text-zinc-400" /> : <ChevronRight className="w-3.5 h-3.5 text-zinc-400" />}
            </div>

            {/* Stages Detail (Foldable) */}
            {expanded && (
                <div className="px-3 py-2 border-t border-zinc-100 bg-white space-y-0.5">
                    {displayStages.map((stage, i) => (
                        <StageDetailItem key={stage.id || i} stage={stage} />
                    ))}
                </div>
            )}

            {/* Final Business Summary (Only on success/finish) */}
            {overallStatus === "success" && (
                <div className="px-4 py-3 border-t border-zinc-100 bg-emerald-50/40">
                    <div className="flex items-start gap-3">
                        <div className="mt-0.5 p-1 rounded-full bg-emerald-100 text-emerald-600">
                            <CheckCircle2 className="w-4 h-4" />
                        </div>
                        <div className="flex-1">
                            <h4 className="text-[13px] font-bold text-emerald-900 leading-tight">
                                BIM 模型已成功注入 Vectorworks
                            </h4>
                            <div className="mt-2 space-y-1 text-[12px] text-emerald-800/90 leading-relaxed">
                                <p><span className="font-semibold">执行状态：</span>{payload.summary || "Vectorworks 已写回构筑结果。"}</p>
                                <p><span className="font-semibold">质量评分：</span>{qualityScore != null ? `${qualityScore}/100` : "等待结果同步"}</p>
                                <p><span className="font-semibold">VWX 文件：</span>{artifacts.vwx_path ? "已生成" : "等待生成"}</p>
                                <p><span className="font-semibold">IFC 文件：</span>{artifacts.ifc_ready ? "已就绪" : artifacts.ifc_status || "等待导出确认"}</p>
                                <p><span className="font-semibold">执行耗时：</span>{totalDurationMs > 0 ? (totalDurationMs / 1000).toFixed(1) + "s" : "等待 VM 回写"}</p>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

/* ---------- Exported component ---------- */

export function ChatMessageDisplay({ message }: { message: UIMessage }) {
    const text = getMessageText(message)
    const sections = useMemo(() => splitExecution(text), [text])
    const isUser = message.role === "user"
    const { pushExecutionLog } = useDevLogStore()

    // Push execution log payloads to dev log store
    useEffect(() => {
        for (const section of sections) {
            if (section.type === "execution" && section.payload) {
                pushExecutionLog(section.payload as Record<string, unknown>)
            }
        }
    }, [sections, pushExecutionLog])

    return (
        <div
            className={cn(
                "flex w-full mb-6",
                isUser ? "justify-end" : "justify-start",
            )}
        >
            <div
                className={cn(
                    "max-w-[85%] rounded-[1.75rem] px-6 py-4 text-sm shadow-sm transition-all",
                    isUser
                        ? "bg-zinc-950 text-zinc-50 shadow-zinc-200"
                        : "border border-zinc-200 bg-white/80 text-zinc-800 backdrop-blur-sm",
                )}
            >
                {sections.map((section, index) =>
                    section.type === "execution" && section.payload ? (
                        <ExecutionCard
                            key={`execution-${index}`}
                            payload={section.payload}
                        />
                    ) : (
                        <div
                            key={`text-${index}`}
                            className={cn(
                                "prose prose-sm max-w-none prose-zinc",
                                isUser ? "prose-invert" : "",
                            )}
                        >
                            <ReactMarkdown>{section.content}</ReactMarkdown>
                        </div>
                    ),
                )}
            </div>
        </div>
    )
}
