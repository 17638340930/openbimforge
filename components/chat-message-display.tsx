"use client"

import type { UIMessage } from "ai"
import {
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    LoaderCircle,
    Sparkles,
    XCircle,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import ReactMarkdown from "react-markdown"
import { useDevLogStore } from "@/contexts/dev-log-store"
import { getApiEndpoint } from "@/lib/base-path"
import { cn } from "@/lib/utils"

interface ExecutionStage {
    id?: string
    label?: string
    status?: string
    duration_ms?: number
    detail?: string
}

interface QualityDimensionDetail {
    score?: number
    [key: string]: unknown
}

interface QualityReport {
    build_status?: string
    quality_score?: number
    native_bim_score?: number
    degradation_count?: number
    missing_resources?: string[]
    metrics?: {
        storey_count?: number
        wall_count?: number
        slab_count?: number
        space_count?: number
        polygon_count?: number
        roof_count?: number
        door_count?: number
        window_count?: number
        inferred_area_m2?: number | null
        inferred_floor_height_m?: number | null
    }
    dimensions?: {
        requirement_conformance?: QualityDimensionDetail
        geometry_validity?: QualityDimensionDetail
        bim_richness?: QualityDimensionDetail
    }
    next_actions?: string[]
}

interface RequirementSlots {
    building_type?: string | null
    storey_count?: number | string | null
    target_area_m2?: number | string | null
    floor_height_m?: number | string | null
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
    quality?: QualityReport
    requirement_slots?: RequirementSlots
    typology_key?: string
    mep?: MepOutcome
}

interface MepOutcome {
    enabled?: boolean
    error?: string
    fixture_count?: number
    stack_count?: number
    pipe_count?: number
    ifc_path?: string
    plan_path?: string
    script_path?: string
    warnings?: string[]
    quality?: {
        build_status?: string
        quality_score?: number
        dimensions?: Record<string, { score?: number; [key: string]: unknown }>
        next_actions?: string[]
    }
    metrics?: Record<string, unknown>
}

interface NexusResultData {
    ok?: boolean
    result?: {
        execution_summary?: {
            code_lines?: number
            quality_score?: number
            validation?: {
                quality?: QualityReport
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

const STAGE_META: Record<string, { icon: string; zh: string }> = {
    architect_agent: { icon: "A", zh: "需求规划" },
    constructor_agent: { icon: "C", zh: "代码合成" },
    nexus_checker: { icon: "Q", zh: "质量审查" },
    nexus_checker_rewrite: { icon: "R", zh: "重生成" },
    transit_payload: { icon: "T", zh: "载荷交付" },
    nexus_transit: { icon: "T", zh: "载荷交付" },
    nexus_execute: { icon: "V", zh: "物理构筑" },
    mep_agent: { icon: "M", zh: "MEP 排污" },
    mep_fixtures: { icon: "F", zh: "器具布置" },
    mep_stacks: { icon: "S", zh: "立管规划" },
    mep_routing: { icon: "P", zh: "管路规划" },
    mep_sizing: { icon: "D", zh: "管径/通气" },
    "stage-0": { icon: "?", zh: "需求追问" },
    "stage-1": { icon: "A", zh: "需求规划" },
    "stage-2": { icon: "C", zh: "代码合成" },
    "stage-3": { icon: "T", zh: "载荷交付" },
    "stage-4": { icon: "V", zh: "物理构筑" },
    layout_upload: { icon: "I", zh: "拓扑输入" },
    layout_agent: { icon: "F", zh: "ForgeVision-Form" },
}

const RESULT_POLL_INTERVALS_MS = [15000, 30000, 60000, 120000, 300000]

function getStageDisplay(stage: ExecutionStage) {
    const key = stage.id || ""
    const meta = STAGE_META[key]
    return {
        label: meta?.zh || stage.label || stage.id || "未知步骤",
        icon: meta?.icon || ">",
    }
}

function getMessageText(message: UIMessage): string {
    return message.parts
        ?.map((part: any) => (part.type === "text" ? part.text || "" : ""))
        .filter(Boolean)
        .join("\n")
}

function sanitizeDisplayText(text: string): string {
    const technicalLinePatterns = [
        /^\s*\[Nexus-Log\]/i,
        /^\s*\[Nexus-Bridge\]/i,
        /^\s*\[Nexus-Web-(?:Status|Progress|Final|Clarify|LLM)\]/i,
        /^\s*\[Nexus-Orchestrator\]\s+(?:Creating|.*client|.*Diagnostics|Warming)/i,
        /^\s*\[Diagnostics\]/i,
        /^\s*Creating .* client/i,
        /^\s*Architect-Agent client ready/i,
        /^\s*Constructor-Agent client ready/i,
    ]

    const withForgeVisionPlaceholder = text
        .replace(
            /(?:\u3010ForgeVision(?:Layout)?Constraints\u3011|ã€ForgeVision(?:Layout)?Constraintsã€‘|Ã£â‚¬ÂForgeVision(?:Layout)?ConstraintsÃ£â‚¬â€˜)[\s\S]*?(?=\u3010用户补充需求\u3011|ã€ç”¨æˆ·è¡¥å……éœ€æ±‚ã€‘|Constraint policy:|$)/g,
            "📦 [已载入 ForgeVision 几何/空间约束供主模型参考]\n\n",
        )
        .replace(
            /```json\s*([\s\S]*?(?:"source"\s*:\s*"forgevision-(?:form|layout)"|forgeVision(?:Layout)?Constraints|cadVectorPaths|layoutTopologyPath)[\s\S]*?)```/gi,
            "📦 [已载入 ForgeVision 几何/空间约束供主模型参考]",
        )
        .replace(
            /\{\s*"source"\s*:\s*"forgevision-form"[\s\S]*?\n\}/g,
            "📦 [已载入 ForgeVision 几何约束供主模型参考]",
        )
        .replace(/\n?Constraint policy:[\s\S]*$/i, "")

    const withClarificationCards = withForgeVisionPlaceholder.replace(
        /```json\s*([\s\S]*?(?:ready_to_generate|missing_fields|extracted_slots)[\s\S]*?)```/gi,
        (_match, jsonText) => {
            try {
                const data = JSON.parse(jsonText)
                const missing = Array.isArray(data.missing_fields)
                    ? data.missing_fields.join("、")
                    : "无"
                const slots = data.extracted_slots && typeof data.extracted_slots === "object"
                    ? Object.entries(data.extracted_slots)
                          .filter(([, value]) => Boolean(value))
                          .map(([key, value]) => `- ${key}: ${value}`)
                          .join("\n")
                    : "暂无"
                return [
                    "### Nexus 需求确认",
                    `- 完整度评分：${data.completion_score ?? "待评估"}/100`,
                    `- 是否可生成：${data.ready_to_generate ? "是" : "否"}`,
                    `- 缺失字段：${missing}`,
                    "",
                    "**已识别参数**",
                    slots,
                ].join("\n")
            } catch {
                return ""
            }
        },
    )

    return withClarificationCards
        .replace(/\r/g, "\n")
        .split("\n")
        .filter((line) => !technicalLinePatterns.some((pattern) => pattern.test(line)))
        .join("\n")
        .replace(/\n{3,}/g, "\n\n")
        .trim()
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
        const before = sanitizeDisplayText(text.slice(lastIndex, match.index))
        if (before) sections.push({ type: "text", content: before })
        try {
            sections.push({
                type: "execution",
                content: match[1].trim(),
                payload: JSON.parse(match[1].trim()),
            })
        } catch {
            const fallback = sanitizeDisplayText(match[0])
            if (fallback) sections.push({ type: "text", content: fallback })
        }
        lastIndex = pattern.lastIndex
    }

    const tail = sanitizeDisplayText(text.slice(lastIndex))
    if (tail) sections.push({ type: "text", content: tail })

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

    return filtered.length ? filtered : [{ type: "text" as const, content: sanitizeDisplayText(text) || text }]
}

function isForgeVisionConstraintText(text: string): boolean {
    return (
        text.includes("\u3010ForgeVisionConstraints\u3011") ||
        text.includes("\u3010ForgeVisionLayoutConstraints\u3011") ||
        text.includes("ã€ForgeVisionConstraintsã€‘") ||
        text.includes("ã€ForgeVisionLayoutConstraintsã€‘") ||
        text.includes("Ã£â‚¬ÂForgeVisionConstraintsÃ£â‚¬â€˜") ||
        text.includes("Ã£â‚¬ÂForgeVisionLayoutConstraintsÃ£â‚¬â€˜") ||
        (/ForgeVision/i.test(text) && /(cadVectorPath|layoutTopologyPath|forgeVisionLayoutConstraints)/i.test(text))
    )
}

function ForgeVisionConstraintCard() {
    return (
        <div className="rounded-2xl border border-violet-200 bg-violet-50/90 p-4 text-violet-950 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-violet-100 text-xs text-violet-700">
                    FV
                </span>
                <span>已载入 ForgeVision 几何/空间约束</span>
            </div>
            <div className="mt-2 space-y-1 text-xs leading-relaxed text-violet-800">
                <p>图片形体、CAD 向量或空间拓扑已交给 Nexus 主模型。</p>
                <p>前端隐藏原始 JSON，后端仍保留完整约束用于 BIM 生成。</p>
            </div>
        </div>
    )
}

function StatusDot({ status }: { status?: string }) {
    if (status === "completed") {
        return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
    }
    if (status === "failed") {
        return <XCircle className="h-3.5 w-3.5 text-red-500" />
    }
    if (status === "running") {
        return <LoaderCircle className="h-3.5 w-3.5 animate-spin text-sky-500" />
    }
    if (status === "waiting" || status === "pending") {
        return <LoaderCircle className="h-3.5 w-3.5 animate-spin text-amber-500" />
    }
    return <div className="h-3.5 w-3.5 rounded-full border-2 border-zinc-300" />
}

function CollapsibleStageRow({
    stage,
    defaultOpen,
}: {
    stage: ExecutionStage
    defaultOpen?: boolean
}) {
    const { label, icon } = getStageDisplay(stage)
    const [open, setOpen] = useState(
        defaultOpen ?? (stage.status === "running" || stage.status === "failed"),
    )
    const isRunning = stage.status === "running"
    const isCompleted = stage.status === "completed"
    const hasDetail = !!stage.detail

    return (
        <div className="rounded-lg border border-transparent transition-colors hover:border-zinc-200/80 hover:bg-zinc-50/70">
            <button
                type="button"
                className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left"
                onClick={() => hasDetail && setOpen((value) => !value)}
                disabled={!hasDetail}
            >
                <StatusDot status={stage.status} />
                <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                        <span
                            className={cn(
                                "text-[12px] font-medium",
                                isCompleted ? "text-zinc-900" : "text-zinc-500",
                                isRunning && "text-blue-600",
                                stage.status === "failed" && "text-red-600",
                            )}
                        >
                            <span className="mr-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-zinc-100 text-[9px] font-bold text-zinc-600">
                                {icon}
                            </span>
                            {label}
                        </span>
                        <div className="flex items-center gap-2">
                            {stage.duration_ms ? (
                                <span className="text-[10px] tabular-nums text-zinc-400">
                                    {(stage.duration_ms / 1000).toFixed(1)}s
                                </span>
                            ) : null}
                            {hasDetail ? (
                                open ? (
                                    <ChevronDown className="h-3 w-3 text-zinc-400" />
                                ) : (
                                    <ChevronRight className="h-3 w-3 text-zinc-400" />
                                )
                            ) : null}
                        </div>
                    </div>
                </div>
            </button>
            {hasDetail && open ? (
                <div className="border-l-2 border-zinc-200 bg-zinc-50/50 px-3 py-2 ml-3 mb-1 text-[11px] leading-relaxed text-zinc-600">
                    {stage.detail}
                </div>
            ) : null}
        </div>
    )
}

function QualityBadge({ score }: { score?: number }) {
    if (typeof score !== "number") return null
    const tone =
        score >= 85
            ? "bg-emerald-100 text-emerald-700"
            : score >= 60
              ? "bg-amber-100 text-amber-700"
              : "bg-rose-100 text-rose-700"
    return (
        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-bold tabular-nums", tone)}>
            Quality {score}
        </span>
    )
}

function QualityPanel({ quality }: { quality: QualityReport | undefined }) {
    const [open, setOpen] = useState(false)
    if (!quality || typeof quality.quality_score !== "number") return null

    const dimensions = quality.dimensions || {}
    const conformance = dimensions.requirement_conformance
    const geometry = dimensions.geometry_validity
    const richness = dimensions.bim_richness
    const metrics = quality.metrics || {}
    const nextActions = quality.next_actions || []

    return (
        <div className="border-t border-zinc-100 bg-white">
            <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-4 py-2 text-left"
                onClick={() => setOpen((value) => !value)}
            >
                <div className="flex items-center gap-2 text-[11px] font-semibold text-zinc-700">
                    <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                    <span>质量评估</span>
                    <QualityBadge score={quality.quality_score} />
                    <span className="text-[10px] font-normal text-zinc-400">
                        status={quality.build_status || "n/a"}
                    </span>
                </div>
                {open ? (
                    <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
                ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-zinc-400" />
                )}
            </button>
            {open ? (
                <div className="space-y-3 px-4 pb-3 text-[11px] leading-relaxed text-zinc-700">
                    <div className="grid grid-cols-3 gap-2">
                        <DimensionTile
                            label="需求符合度"
                            score={conformance?.score as number | undefined}
                            hint={
                                conformance
                                    ? `area ${conformance.area_inferred_m2 ?? "?"}/${conformance.area_expected_m2 ?? "?"} m2`
                                    : undefined
                            }
                        />
                        <DimensionTile
                            label="几何合理性"
                            score={geometry?.score as number | undefined}
                            hint={
                                geometry
                                    ? `walls=${geometry.wall_count ?? 0} slabs=${geometry.slab_count ?? 0}`
                                    : undefined
                            }
                        />
                        <DimensionTile
                            label="BIM 语义丰富度"
                            score={richness?.score as number | undefined}
                            hint={
                                richness
                                    ? `core=${richness.has_core_zone ? "y" : "n"} corr=${richness.has_circulation_zone ? "y" : "n"}`
                                    : undefined
                            }
                        />
                    </div>
                    <div>
                        <p className="mb-1 text-[10px] uppercase tracking-wide text-zinc-400">Metrics</p>
                        <div className="grid grid-cols-4 gap-x-3 gap-y-1 text-[10px] text-zinc-600">
                            <span>storey {metrics.storey_count ?? 0}</span>
                            <span>wall {metrics.wall_count ?? 0}</span>
                            <span>slab {metrics.slab_count ?? 0}</span>
                            <span>space {metrics.space_count ?? 0}</span>
                            <span>door {metrics.door_count ?? 0}</span>
                            <span>window {metrics.window_count ?? 0}</span>
                            <span>roof {metrics.roof_count ?? 0}</span>
                            <span>
                                area {metrics.inferred_area_m2 != null ? `${metrics.inferred_area_m2} m2` : "?"}
                            </span>
                        </div>
                    </div>
                    {nextActions.length > 0 ? (
                        <div>
                            <p className="mb-1 text-[10px] uppercase tracking-wide text-zinc-400">Next actions</p>
                            <ul className="list-inside list-disc space-y-0.5 text-[11px]">
                                {nextActions.map((action, index) => (
                                    <li key={index}>{action}</li>
                                ))}
                            </ul>
                        </div>
                    ) : null}
                </div>
            ) : null}
        </div>
    )
}

function DimensionTile({
    label,
    score,
    hint,
}: {
    label: string
    score?: number
    hint?: string
}) {
    const tone =
        typeof score !== "number"
            ? "bg-zinc-50 text-zinc-500"
            : score >= 85
              ? "bg-emerald-50 text-emerald-900"
              : score >= 60
                ? "bg-amber-50 text-amber-900"
                : "bg-rose-50 text-rose-900"
    return (
        <div className={cn("rounded-lg border border-zinc-100 px-2 py-1.5", tone)}>
            <div className="text-[10px] font-semibold tracking-wide">{label}</div>
            <div className="text-lg font-bold tabular-nums leading-tight">
                {typeof score === "number" ? score : "—"}
            </div>
            {hint ? <div className="text-[9px] opacity-70">{hint}</div> : null}
        </div>
    )
}

function LogsPanel({ logs }: { logs?: string[] }) {
    const [open, setOpen] = useState(false)
    if (!logs || logs.length === 0) return null

    return (
        <div className="border-t border-zinc-100 bg-white">
            <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-4 py-2 text-left text-[11px] font-semibold text-zinc-700"
                onClick={() => setOpen((value) => !value)}
            >
                <span>执行日志 ({logs.length})</span>
                {open ? (
                    <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
                ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-zinc-400" />
                )}
            </button>
            {open ? (
                <pre className="mx-4 mb-3 max-h-48 overflow-auto rounded-lg bg-zinc-950 p-3 text-[10px] leading-relaxed text-zinc-100">
                    {logs.join("\n")}
                </pre>
            ) : null}
        </div>
    )
}

function MepPanel({ mep }: { mep?: MepOutcome }) {
    const [open, setOpen] = useState(false)
    if (!mep || !mep.enabled) return null

    const score = mep.quality?.quality_score
    const hasError = Boolean(mep.error)
    const tone = hasError
        ? "bg-rose-100 text-rose-700"
        : score === undefined
          ? "bg-zinc-100 text-zinc-600"
          : score >= 85
            ? "bg-emerald-100 text-emerald-700"
            : score >= 60
              ? "bg-amber-100 text-amber-700"
              : "bg-rose-100 text-rose-700"

    return (
        <div className="border-t border-zinc-100 bg-white">
            <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-4 py-2 text-left"
                onClick={() => setOpen((value) => !value)}
            >
                <div className="flex items-center gap-2 text-[11px] font-semibold text-zinc-700">
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-cyan-100 text-[9px] font-bold text-cyan-700">
                        M
                    </span>
                    <span>MEP 排污系统</span>
                    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-bold tabular-nums", tone)}>
                        {hasError
                            ? "failed"
                            : score !== undefined
                              ? `Quality ${score}`
                              : "ready"}
                    </span>
                </div>
                {open ? (
                    <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
                ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-zinc-400" />
                )}
            </button>
            {open ? (
                <div className="space-y-2 px-4 pb-3 text-[11px] leading-relaxed text-zinc-700">
                    {hasError ? (
                        <p className="text-rose-600">{mep.error}</p>
                    ) : (
                        <>
                            <div className="grid grid-cols-3 gap-2 text-[10px] text-zinc-600">
                                <span>fixtures {mep.fixture_count ?? 0}</span>
                                <span>stacks {mep.stack_count ?? 0}</span>
                                <span>pipes {mep.pipe_count ?? 0}</span>
                            </div>
                            {mep.quality?.dimensions ? (
                                <div className="grid grid-cols-4 gap-2">
                                    {Object.entries(mep.quality.dimensions).map(([key, value]) => (
                                        <div
                                            key={key}
                                            className="rounded-lg border border-zinc-100 bg-cyan-50/40 px-2 py-1.5 text-cyan-900"
                                        >
                                            <div className="text-[9px] uppercase tracking-wide">
                                                {key}
                                            </div>
                                            <div className="text-sm font-bold tabular-nums">
                                                {typeof value.score === "number" ? value.score : "—"}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : null}
                            {mep.ifc_path ? (
                                <p className="text-[10px] text-zinc-500 truncate">
                                    IFC: <span className="font-mono text-zinc-700">{mep.ifc_path}</span>
                                </p>
                            ) : null}
                            {mep.quality?.next_actions?.length ? (
                                <div>
                                    <p className="text-[10px] uppercase tracking-wide text-zinc-400">建议</p>
                                    <ul className="list-inside list-disc text-[11px]">
                                        {mep.quality.next_actions.map((action, idx) => (
                                            <li key={idx}>{action}</li>
                                        ))}
                                    </ul>
                                </div>
                            ) : null}
                        </>
                    )}
                </div>
            ) : null}
        </div>
    )
}

function RequirementSlotsRow({
    slots,
    typologyKey,
}: {
    slots?: RequirementSlots
    typologyKey?: string
}) {
    if (!slots && !typologyKey) return null
    const chips: Array<{ label: string; value: string }> = []
    if (typologyKey) chips.push({ label: "typology", value: typologyKey })
    if (slots?.building_type) chips.push({ label: "type", value: String(slots.building_type) })
    if (slots?.storey_count) chips.push({ label: "storeys", value: String(slots.storey_count) })
    if (slots?.target_area_m2) chips.push({ label: "area", value: `${slots.target_area_m2} m²` })
    if (slots?.floor_height_m) chips.push({ label: "floor h", value: `${slots.floor_height_m} m` })
    if (chips.length === 0) return null

    return (
        <div className="flex flex-wrap items-center gap-1 border-t border-zinc-100 bg-zinc-50/40 px-4 py-2">
            {chips.map((chip) => (
                <span
                    key={chip.label}
                    className="rounded-md bg-white px-2 py-0.5 text-[10px] text-zinc-600 shadow-sm ring-1 ring-zinc-200"
                >
                    <span className="text-zinc-400">{chip.label}</span>
                    <span className="mx-1 text-zinc-300">·</span>
                    <span className="font-semibold">{chip.value}</span>
                </span>
            ))}
        </div>
    )
}

export function ExecutionCard({ payload }: { payload: ExecutionLogPayload }) {
    const [expanded, setExpanded] = useState(true)
    const [resultData, setResultData] = useState<NexusResultData | null>(null)
    const stages = payload.stages || []
    const isForgeVision = payload.mode === "ForgeVision-Form" || payload.mode === "ForgeVision-Layout"
    const isForgeVisionLayout = payload.mode === "ForgeVision-Layout"

    const resultStatus = resultData ? (resultData.ok ? "success" : "failed") : null
    const resultQuality = resultData?.result?.execution_summary?.validation?.quality
    const payloadQuality = payload.quality
    const quality: QualityReport | undefined = resultQuality || payloadQuality
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
            return { ...stage, status: "completed", detail: executeDetail }
        })

        if (hasExecuteStage) return updatedStages
        return [
            ...updatedStages,
            {
                id: "nexus_execute",
                label: "Nexus-Execute",
                status: "completed",
                detail: executeDetail,
            },
        ]
    }, [artifacts.ifc_ready, resultStatus, stages])

    const hasVmWaiting = displayStages.some((stage) => stage.id === "nexus_execute" && ["running", "pending", "waiting"].includes(String(stage.status)))
    const hasRunning = displayStages.length === 0 || displayStages.some((stage) => ["running", "pending", "waiting"].includes(String(stage.status)))
    const hasFailed = displayStages.some((stage) => stage.status === "failed")
    const allDone = displayStages.length > 0 && displayStages.every((stage) => stage.status === "completed")
    const payloadStatus = String(payload.status || "")
    const overallStatus =
        resultStatus ||
        (allDone
            ? "success"
            : hasVmWaiting
              ? "running"
              : hasFailed || payloadStatus === "failed"
                ? "failed"
                : hasRunning
                  ? "running"
                  : "running")
    const totalDurationMs = displayStages.reduce((acc, stage) => acc + (stage.duration_ms || 0), 0)
    const completedStages = displayStages.filter((stage) => stage.status === "completed").length
    const totalStages = isForgeVision ? Math.max(displayStages.length, 1) : Math.max(displayStages.length, 4)

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
                    payload: { payloadPath: payload.handoff_path, source: "execution-card" },
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
        <div className="my-4 max-w-[460px] overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm transition-all hover:shadow-md">
            <div
                className="flex cursor-pointer items-center justify-between bg-zinc-50/50 px-4 py-3"
                onClick={() => setExpanded(!expanded)}
            >
                <div className="flex items-center gap-3">
                    <div
                        className={cn(
                            "h-2 w-2 rounded-full",
                            overallStatus === "success"
                                ? "bg-emerald-500"
                                : overallStatus === "failed"
                                  ? "bg-rose-500"
                                  : "animate-pulse bg-blue-500",
                        )}
                    />
                    <span className="text-[13px] font-bold tracking-tight text-zinc-800">
                        {isForgeVision
                            ? isForgeVisionLayout
                                ? "ForgeVision-Layout 空间拓扑"
                                : "ForgeVision-Form 形体转化"
                            : "NEXUS BIM 协同编排流"}
                    </span>
                    <span
                        className={cn(
                            "rounded-full px-2 py-0.5 text-[10px] font-bold tabular-nums",
                            overallStatus === "success"
                                ? "bg-emerald-100 text-emerald-700"
                                : overallStatus === "failed"
                                  ? "bg-rose-100 text-rose-700"
                                  : "bg-blue-100 text-blue-700",
                        )}
                    >
                        {overallStatus === "success"
                            ? `${completedStages}/${totalStages} 阶段已完成`
                            : overallStatus === "failed"
                              ? "构筑失败"
                              : hasVmWaiting
                                ? `${completedStages}/${totalStages} 等待 VM 回写...`
                                : `${completedStages}/${totalStages} 正在构筑...`}
                    </span>
                    {quality?.quality_score != null ? (
                        <QualityBadge score={quality.quality_score} />
                    ) : null}
                </div>
                {expanded ? (
                    <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
                ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-zinc-400" />
                )}
            </div>

            <RequirementSlotsRow slots={payload.requirement_slots} typologyKey={payload.typology_key} />

            {expanded && (
                <div className="space-y-1 border-t border-zinc-100 bg-white px-3 py-2">
                    {displayStages.length === 0 ? (
                        <div className="px-2 py-3 text-[11px] text-zinc-400">正在初始化 Nexus 编排...</div>
                    ) : (
                        displayStages.map((stage, i) => (
                            <CollapsibleStageRow
                                key={stage.id || i}
                                stage={stage}
                                defaultOpen={stage.status === "running" || stage.status === "failed"}
                            />
                        ))
                    )}
                </div>
            )}

            <QualityPanel quality={quality} />
            <MepPanel mep={payload.mep} />
            <LogsPanel logs={payload.logs} />

            {overallStatus === "success" && (
                <div className="border-t border-zinc-100 bg-emerald-50/40 px-4 py-3">
                    <div className="flex items-start gap-3">
                        <div className="mt-0.5 rounded-full bg-emerald-100 p-1 text-emerald-600">
                            <CheckCircle2 className="h-4 w-4" />
                        </div>
                        <div className="flex-1">
                            {isForgeVision ? (
                                <>
                                    <h4 className="text-[13px] font-bold leading-tight text-emerald-900">
                                        {isForgeVisionLayout ? "图片空间拓扑已完成" : "图片形体参考已完成"}
                                    </h4>
                                    <div className="mt-2 space-y-1 text-[12px] leading-relaxed text-emerald-800/90">
                                        <p>
                                            <span className="font-semibold">执行状态：</span>
                                            {payload.summary || "ForgeVision 已返回参考产物。"}
                                        </p>
                                        <p>
                                            <span className="font-semibold">下一步：</span>
                                            系统将自动进入 Nexus 编排；如未触发，可点击对应的继续生成按钮。
                                        </p>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <h4 className="text-[13px] font-bold leading-tight text-emerald-900">
                                        BIM 模型已成功注入 Vectorworks
                                    </h4>
                                    <div className="mt-2 space-y-1 text-[12px] leading-relaxed text-emerald-800/90">
                                        <p>
                                            <span className="font-semibold">执行状态：</span>
                                            {payload.summary || "Vectorworks 已写回构筑结果。"}
                                        </p>
                                        <p>
                                            <span className="font-semibold">质量评分：</span>
                                            {quality?.quality_score != null ? `${quality.quality_score}/100` : "等待结果同步"}
                                        </p>
                                        <p>
                                            <span className="font-semibold">VWX 文件：</span>
                                            {artifacts.vwx_path ? "已生成" : "等待生成"}
                                        </p>
                                        <p>
                                            <span className="font-semibold">IFC 文件：</span>
                                            {artifacts.ifc_ready
                                                ? "已就绪"
                                                : artifacts.ifc_status || "等待导出确认"}
                                        </p>
                                        <p>
                                            <span className="font-semibold">执行耗时：</span>
                                            {totalDurationMs > 0 ? `${(totalDurationMs / 1000).toFixed(1)}s` : "等待 VM 回写"}
                                        </p>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

export function ChatMessageDisplay({ message }: { message: UIMessage }) {
    const text = getMessageText(message)
    const sections = useMemo(() => splitExecution(text), [text])
    const isUser = message.role === "user"
    const isForgeVisionConstraintMessage = isUser && isForgeVisionConstraintText(text)
    const { pushExecutionLog } = useDevLogStore()

    useEffect(() => {
        for (const section of sections) {
            if (section.type === "execution" && section.payload) {
                pushExecutionLog(section.payload as Record<string, unknown>)
            }
        }
    }, [sections, pushExecutionLog])

    return (
        <div className={cn("mb-6 flex w-full", isUser ? "justify-end" : "justify-start")}>
            <div
                className={cn(
                    "max-w-[85%] rounded-[1.75rem] px-6 py-4 text-sm shadow-sm transition-all",
                    isForgeVisionConstraintMessage
                        ? "max-w-[560px] bg-transparent p-0 shadow-none"
                        : isUser
                          ? "bg-zinc-950 text-zinc-50 shadow-zinc-200"
                          : "border border-zinc-200 bg-white/80 text-zinc-800 backdrop-blur-sm",
                )}
            >
                {sections.map((section, index) =>
                    section.type === "execution" && section.payload ? (
                        <ExecutionCard key={`execution-${index}`} payload={section.payload} />
                    ) : isForgeVisionConstraintMessage ? (
                        <ForgeVisionConstraintCard key={`text-${index}`} />
                    ) : (
                        <div
                            key={`text-${index}`}
                            className={cn("prose prose-sm max-w-none prose-zinc", isUser ? "prose-invert" : "")}
                        >
                            <ReactMarkdown>{section.content}</ReactMarkdown>
                        </div>
                    ),
                )}
            </div>
        </div>
    )
}
