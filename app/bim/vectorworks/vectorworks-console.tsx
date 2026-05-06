"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Toaster } from "sonner"
import {
    CheckCircle2,
    PlayCircle,
    Activity,
} from "lucide-react"
import { DevConsolePanel } from "@/components/dev-console-panel"
import { getApiEndpoint, getBasePath } from "@/lib/base-path"

type CapabilityResponse = {
    ok: boolean
    ready: boolean
    manifestPath?: string
    updatedAt?: string
    capabilityScanScript?: string
    manifest?: {
        wall_styles?: string[]
        slab_styles?: string[]
        door_symbols?: string[]
        window_symbols?: string[]
    }
}

type ResultResponse = {
    ok: boolean
    path: string
    data?: {
        ok: boolean
        executed_in: string
        handoff_path: string
        result: {
            execution_summary?: {
                build_status?: string
                quality_score?: number
                native_bim_score?: number
                fallback_score?: number
            }
            attempts?: Array<{ attempt: number; status: string }>
        }
        artifacts: {
            vwx_path?: string
            ifc_path?: string
            ifc_ready?: boolean
            ifc_status?: string
            ifc_message?: string
        }
        error?: { category?: string; summary?: string }
    }
    pending?: boolean
    error?: string
}

type RuntimeFile = {
    name: string
    path: string
    updatedAt: string
    size: number
}

type RunnerResponse = {
    ok: boolean
    payloadRoot: string
    nexusLegacySync?: {
        ok?: boolean
        stage?: string
        bridge?: string
        command?: string
        handoffRoot?: string
        updatedAt?: string
        executedCount?: number
        error?: string
        legacyStatusPath?: string
    } | null
    watchSynthesisScript: string
    runOnceSynthesisScript: string
    counts: {
        payloads: number
        pending: number
        deferred: number
        running: number
        done: number
        failed: number
        results: number
    }
    latest: {
        payload: RuntimeFile | null
        pending: RuntimeFile | null
        deferred: RuntimeFile | null
        running: RuntimeFile | null
        done: RuntimeFile | null
        failed: RuntimeFile | null
        result: RuntimeFile | null
    }
}

type HostReply = {
    id?: string
    ok?: boolean
    type?: string
    error?: string
    data?: {
        methods?: string[]
        hasTumIntegrator?: boolean
        method?: string
        missingMethod?: string
        requestedAction?: string
        result?: unknown
    }
}

type HostStatus = "unknown" | "browser" | "connected" | "missing-native" | "error"

type VectorworksNativeBridge = {
    getAllPlantDataV2?: (input: string, history: string) => Promise<unknown>
    openBIMForgeStartRunner?: (payload: string) => Promise<unknown>
    openBIMForgeRunPending?: (payload: string) => Promise<unknown>
    openBIMForgeScanCapabilities?: (payload: string) => Promise<unknown>
    [key: string]: unknown
}

declare global {
    interface Window {
        tumIntegrator?: VectorworksNativeBridge
    }
}

async function fetchJson<T>(url: string): Promise<T> {
    const response = await fetch(url, { cache: "no-store" })
    if (!response.ok) throw new Error(`${url} returned ${response.status}`)
    return response.json() as Promise<T>
}

function getPreferredChatLocale(): string {
    if (typeof window === "undefined") return "zh"

    const requestedLocale = new URLSearchParams(window.location.search).get("lang")
    if (requestedLocale && ["en", "zh", "ja", "zh-Hant"].includes(requestedLocale)) {
        return requestedLocale
    }

    const browserLocale = navigator.language.toLowerCase()
    if (browserLocale.startsWith("ja")) return "ja"
    if (browserLocale.includes("hant") || browserLocale.includes("tw") || browserLocale.includes("hk")) {
        return "zh-Hant"
    }
    if (browserLocale.startsWith("zh")) return "zh"
    return "en"
}

function buildBimChatUrl(): string {
    const params = new URLSearchParams({
        openBIMForge: "1",
        mode: "nexus",
        host: "vectorworks",
    })
    return `${getBasePath()}/${getPreferredChatLocale()}?${params.toString()}`
}

function StateBadge({ ok, children }: { ok: boolean; children: React.ReactNode }) {
    return <span className={ok ? "forge-badge ok" : "forge-badge todo"}>{children}</span>
}

function FallbackScript({
    title,
    description,
    script,
    disabled,
}: {
    title: string
    description: string
    script?: string
    disabled?: boolean
}) {
    const [copied, setCopied] = useState(false)

    async function copyScript() {
        if (!script || disabled) return
        await navigator.clipboard.writeText(script)
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1600)
    }

    return (
        <article className="forge-step-card">
            <div>
                <h3>{title}</h3>
                <p>{description}</p>
            </div>
            <button type="button" onClick={copyScript} disabled={!script || disabled}>
                {copied ? "已复制" : "复制 Synthesis 脚本"}
            </button>
            <details>
                <summary>查看脚本内容</summary>
                <pre>{script || "等待 Nexus 引擎生成..."}</pre>
            </details>
        </article>
    )
}

function PathRow({ label, file }: { label: string; file: RuntimeFile | null }) {
    return (
        <div className="forge-path-row">
            <strong>{label}</strong>
            <code>{file?.path ?? "暂无"}</code>
        </div>
    )
}

function hostStatusText(status: HostStatus) {
    switch (status) {
        case "connected":
            return "已连接 BIM Synthesis Workbench 原生桥"
        case "missing-native":
            return "已连接旧版原生桥，但缺少 Nexus-Constructor 自动合成方法"
        case "browser":
            return "检测到普通浏览器环境，未发现 BIM Synthesis Workbench 宿主"
        case "error":
            return "BIM Synthesis Workbench 宿主桥接中断"
        default:
            return "正在检索 BIM Synthesis 宿主桥"
    }
}

export default function VectorworksConsole() {
    const [hostStatus, setHostStatus] = useState<HostStatus>("unknown")
    const [hostMessage, setHostMessage] = useState("正在检索 BIM Synthesis 宿主桥")
    const [hostMethods, setHostMethods] = useState<string[]>([])
    const [capability, setCapability] = useState<CapabilityResponse | null>(null)
    const [runner, setRunner] = useState<RunnerResponse | null>(null)
    const [resultData, setResultData] = useState<ResultResponse | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [hostMode, setHostMode] = useState(false)

    const lastAutoStartedPendingPath = useRef<string | null>(null)

    useEffect(() => {
        const params = new URLSearchParams(window.location.search)
        setHostMode(params.get("host") === "vectorworks")
    }, [])

    async function requestHost(type: string, payload?: Record<string, unknown>): Promise<HostReply> {
        const nativeBridge = window.tumIntegrator
        if (!nativeBridge) return { ok: false, error: "Native bridge not found" }
        
        if (type === "OPENBIMFORGE_HOST_STATUS") {
            const methods = Object.keys(nativeBridge).filter(k => typeof (nativeBridge as any)[k] === 'function')
            return { ok: true, data: { methods } }
        }

        if (type === "OPENBIMFORGE_HOST_ACTION") {
                const action = payload?.action as string
                try {
                    if (action === "startRunner" && nativeBridge.openBIMForgeStartRunner) {
                    await nativeBridge.openBIMForgeStartRunner(JSON.stringify(payload?.payload))
                    return { ok: true }
                }
                if (action === "scanCapabilities" && nativeBridge.openBIMForgeScanCapabilities) {
                    await nativeBridge.openBIMForgeScanCapabilities(JSON.stringify(payload?.payload))
                    return { ok: true }
                }
                return { ok: false, error: `Action ${action} not supported or method missing` }
            } catch (e) {
                return { ok: false, error: String(e) }
            }
        }
        return { ok: false, error: "Unknown request type" }
    }

    async function refreshRuntime() {
        try {
            const [capData, runnerData] = await Promise.all([
                fetchJson<CapabilityResponse>(getApiEndpoint("/api/bim/forge-architect-capabilities")),
                fetchJson<RunnerResponse>(getApiEndpoint("/api/bim/forge-architect-runner")),
            ])
            setCapability(capData)
            setRunner(runnerData)

            if (runnerData.latest.result) {
                const resData = await fetchJson<ResultResponse>(
                    getApiEndpoint(
                        `/api/bim/forge-architect-result?path=${encodeURIComponent(runnerData.latest.result.path)}`,
                    ),
                )
                setResultData(resData)
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Runtime 状态刷新失败")
        }
    }

    useEffect(() => {
        let active = true
        async function refresh() {
            if (!active) return
            await refreshRuntime()
        }
        refresh()
        const timer = window.setInterval(refresh, 20000)
        return () => {
            active = false
            window.clearInterval(timer)
        }
    }, [])

    useEffect(() => {
        if (!hostMode) return
        requestHost("OPENBIMFORGE_HOST_STATUS")
            .then((reply) => {
                const methods = reply.data?.methods ?? []
                setHostMethods(methods)
                if (reply.ok) {
                    setHostStatus("connected")
                    setHostMessage(`Workbench 原生协议已对接，检测到 ${methods.length} 个合成接口。`)
                } else {
                    setHostStatus("browser")
                    setHostMessage(reply.error || "未能识别 BIM Synthesis 原生桥接。")
                }
            })
            .catch((hostError) => {
                setHostStatus("browser")
                setHostMessage(hostError instanceof Error ? hostError.message : "Workbench 检索失败")
            })
    }, [hostMode])

    async function startRunnerAutomatically() {
        setHostMessage("正在唤起 Nexus-Constructor 协同合成引擎...")
        try {
            const reply = await requestHost("OPENBIMFORGE_HOST_ACTION", {
                action: "startRunner",
                payload: {
                    payloadRoot: runner?.payloadRoot,
                    runOnceSynthesisScript: runner?.runOnceSynthesisScript,
                    watchSynthesisScript: runner?.watchSynthesisScript,
                },
            })
            if (reply.ok) {
                setHostStatus("connected")
                setHostMessage("Constructor 指令已下发至工作台。正在监控 Transit-Payload 同步状态。")
            } else {
                setHostStatus("missing-native")
                setHostMessage(reply.error || "当前节点缺少原生合成扩展。")
            }
            await refreshRuntime()
        } catch (hostError) {
            setHostStatus("error")
            setHostMessage(hostError instanceof Error ? hostError.message : "合成引擎唤起失败")
        }
    }

    useEffect(() => {
        const pendingPath = runner?.latest.pending?.path
        if (!hostMode || !runner?.payloadRoot || !pendingPath) return
        if (lastAutoStartedPendingPath.current === pendingPath) return
        lastAutoStartedPendingPath.current = pendingPath
        startRunnerAutomatically()
    }, [hostMode, runner?.payloadRoot, runner?.latest.pending?.path])

    const capabilityReady = !!capability?.ready
    const runnerActive = useMemo(() => {
        if (!runner) return false
        return runner.counts.payloads > 0 || runner.counts.done > 0
    }, [runner])
    const bimChatUrl = buildBimChatUrl()

    return (
        <main className="forge-page forge-cn">
            <Toaster />
            <section className="forge-compact-bar">
                <div className="forge-readiness">
                    <StateBadge ok={capabilityReady}>{capabilityReady ? "Capability Contract 已就绪" : "等待能力合约扫描"}</StateBadge>
                    <StateBadge ok={runnerActive}>{runnerActive ? "Synthesis Node 活跃" : "Constructor 待命中"}</StateBadge>
                    <StateBadge ok={hostStatus === "connected"}>{hostStatusText(hostStatus)}</StateBadge>
                    <span className="forge-mini-note">{hostMessage}</span>
                </div>
                <div className="forge-main-actions">
                    <a className={capabilityReady ? "forge-primary" : "forge-primary disabled"} href={bimChatUrl}>
                        Nexus Orchestration
                    </a>
                    <button className="forge-secondary-button" type="button" onClick={startRunnerAutomatically}>
                        唤起合成引擎
                    </button>
                </div>
            </section>

            {error ? <div className="forge-error">{error}</div> : null}

            <section className="forge-host-panel">
                <div>
                    <p className="forge-kicker">多代理协同架构：Nexus-Orchestration</p>
                    <h2>BIM Synthesis Workbench (BIM 执行工作台)</h2>
                    <p>
                        此工作台基于 openBIMForge 协同协议，实现 Architect-Agent 与 Constructor-Agent 的跨模态通讯。
                        通过自动化的 Transit-Payload 传递，实现从“语义逻辑”到“物理构筑”的无缝转化。
                    </p>
                </div>
                <div className="forge-host-methods">
                    <strong>协同协议接口 (APIs)</strong>
                    <code>{hostMethods.length ? hostMethods.join(", ") : "暂无连接"}</code>
                </div>
            </section>

            <section className="forge-flow">
                <article className="forge-flow-card">
                    <div className="flex items-center gap-3 mb-2">
                        <CheckCircle2 className={capabilityReady ? "text-green-500" : "text-zinc-300"} />
                        <h2 className="text-lg font-semibold">1. 同步 Capability Contract</h2>
                    </div>
                    <p className="text-sm text-zinc-500">检索工作台原生能力清单，为 Architect-Agent 提供语义生成边界约束。</p>
                </article>
                <article className="forge-flow-card">
                    <div className="flex items-center gap-3 mb-2">
                        <PlayCircle className={runnerActive ? "text-blue-500" : "text-zinc-300"} />
                        <h2 className="text-lg font-semibold">2. 部署 Constructor-Agent</h2>
                    </div>
                    <p className="text-sm text-zinc-500">激活 Synthesis Node，持续监听 Transit-Payload 并执行构造合成。</p>
                </article>
                <article className="forge-flow-card highlight">
                    <div className="flex items-center gap-3 mb-2">
                        <Activity className="text-indigo-500" />
                        <h2 className="text-lg font-semibold text-indigo-900">3. BIM Synthesis Interaction</h2>
                    </div>
                    <p className="text-sm text-indigo-700/70">输入建筑逻辑。生成的 Transit-Payload 将自动交付至 Constructor-Agent 进行构筑。</p>
                    <a href={bimChatUrl} className="mt-4 inline-block font-medium text-indigo-600 underline">开始协同生成</a>
                </article>
            </section>

            <section className="forge-status-panel">
                <div className="forge-status-card">
                    <h2>Nexus 任务调度状态</h2>
                    <div className="forge-counters">
                        <div><b>{runner?.counts.pending ?? 0}</b><span>待合成</span></div>
                        <div><b>{runner?.counts.deferred ?? 0}</b><span>等待 VM</span></div>
                        <div><b>{runner?.counts.running ?? 0}</b><span>合成中</span></div>
                        <div><b>{runner?.counts.done ?? 0}</b><span>已完成</span></div>
                        <div><b>{runner?.counts.failed ?? 0}</b><span>异常</span></div>
                    </div>
                    <PathRow label="当前 Transit-Payload" file={runner?.latest.payload ?? null} />
                    <PathRow label="待处理 Payload" file={runner?.latest.pending ?? null} />
                    <PathRow label="最新 Digital Asset" file={runner?.latest.result ?? null} />
                    {runner?.nexusLegacySync ? (
                        <div className="forge-path-row">
                            <strong>Nexus Legacy Sync (兼容模式心跳)</strong>
                            <code>
                                {runner.nexusLegacySync.stage ?? "unknown"}
                                {runner.nexusLegacySync.updatedAt ? ` / ${runner.nexusLegacySync.updatedAt}` : ""}
                            </code>
                        </div>
                    ) : null}
                </div>
                <div className="forge-status-card compact">
                    <h2>Capability Contract (能力契约)</h2>
                    <div className="forge-cap-list">
                        <div>Wall Logic <b>{capability?.manifest?.wall_styles?.length ?? 0}</b></div>
                        <div>Slab Logic <b>{capability?.manifest?.slab_styles?.length ?? 0}</b></div>
                        <div>Door Symbols <b>{capability?.manifest?.door_symbols?.length ?? 0}</b></div>
                        <div>Window Symbols <b>{capability?.manifest?.window_symbols?.length ?? 0}</b></div>
                    </div>
                    <p className="forge-muted text-xs mt-2">契约文件：{capability?.manifestPath ?? "暂无"}</p>
                </div>
            </section>

            {resultData?.data ? (
                <section className="forge-result-panel">
                    <div className="forge-result-card">
                        <h2>Constructive Synthesis Results (构造合成结果)</h2>
                        <div className="forge-result-badges">
                            <StateBadge ok={resultData.data.ok}>
                                {resultData.data.ok ? "合成成功" : "合成中断"}
                            </StateBadge>
                        </div>
                        <div className="forge-result-meta mt-4 space-y-2">
                            {resultData.data.result?.execution_summary?.quality_score != null && (
                                <div className="text-sm">Synthesis Quality: <b className="text-indigo-600">{resultData.data.result.execution_summary.quality_score}</b>/100</div>
                            )}
                            {resultData.data.artifacts?.ifc_ready != null && (
                                <div className="text-sm">IFC Asset Status: <b className="text-green-600">{resultData.data.artifacts.ifc_ready ? "Verified" : "Pending"}</b></div>
                            )}
                        </div>
                        <div className="mt-6 flex gap-3">
                            {resultData.data.artifacts?.vwx_path && (
                                <a className="text-sm text-zinc-600 underline" href={getApiEndpoint(`/api/bim/forge-architect-artifact?path=${encodeURIComponent(resultData.data.artifacts.vwx_path)}`)}>下载 VWX</a>
                            )}
                            {resultData.data.artifacts?.ifc_path && (
                                <a className="text-sm text-indigo-600 font-semibold" href={`/bim/ifc-viewer?path=${encodeURIComponent(resultData.data.artifacts.ifc_path)}`}>预览 IFC Asset</a>
                            )}
                        </div>
                    </div>
                </section>
            ) : null}

            <section className="forge-script-grid">
                <FallbackScript
                    title="Capability Scan Script"
                    description="手动同步契约：复制至工作台脚本编辑器执行。"
                    script={capability?.capabilityScanScript}
                    disabled={capabilityReady}
                />
                <FallbackScript
                    title="Constructor Synthesis Script"
                    description="手动触发合成：直接激活 Constructor-Agent 处理当前 Payloads。"
                    script={runner?.runOnceSynthesisScript ?? runner?.watchSynthesisScript}
                />
            </section>

            <section className="forge-dev-console">
                <DevConsolePanel />
            </section>
        </main>
    )
}
