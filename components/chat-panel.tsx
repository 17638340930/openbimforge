"use client"

import { useChat } from "@ai-sdk/react"
import { DefaultChatTransport } from "ai"
import { History, ImageIcon, MessageSquarePlus, Mic, MicOff, Send, Settings, Square, Wrench, X } from "lucide-react"
import Image from "next/image"
import { useCallback, useEffect, useRef, useState } from "react"
import { toast, Toaster } from "sonner"
import { ButtonWithTooltip } from "@/components/button-with-tooltip"
import { ChatHistoryPanel } from "@/components/chat-history-panel"
import { ChatMessageDisplay } from "@/components/chat-message-display"
import { ModelConfigDialog } from "@/components/model-config-dialog"
import { ModelSelector } from "@/components/model-selector"
import { SettingsDialog } from "@/components/settings-dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useConversationManager } from "@/hooks/use-conversation-manager"
import { useImageUpload } from "@/hooks/use-image-upload"
import { getSelectedAIConfig, useModelConfig } from "@/hooks/use-model-config"
import { useVoiceInput } from "@/hooks/use-voice-input"
import { getApiEndpoint } from "@/lib/base-path"
import { STORAGE_KEYS } from "@/lib/storage"
import type { ForgeVisionFormResult } from "@/lib/bim/visionary-types"

interface ChatPanelProps {
    isVisible: boolean
    onToggleVisibility: () => void
    isMobile?: boolean
}

interface ClarifyProfileConfig {
    id: string
    provider: string
    model: string
    baseUrl: string
    apiKey: string
}

function getActiveClarifyConfig(): {
    profile: ClarifyProfileConfig | null
    language: "zh" | "en"
} {
    if (typeof window === "undefined") {
        return { profile: null, language: "zh" }
    }

    const language =
        (localStorage.getItem(STORAGE_KEYS.clarifyLanguage) as "zh" | "en") ||
        "zh"

    const raw = localStorage.getItem(STORAGE_KEYS.clarifyProfiles)
    const activeId = localStorage.getItem(STORAGE_KEYS.clarifyActiveProfileId)
    if (raw) {
        try {
            const profiles = JSON.parse(raw) as ClarifyProfileConfig[]
            if (Array.isArray(profiles) && profiles.length > 0) {
                const profile = profiles.find((item) => item.id === activeId) || profiles[0]
                return { profile, language: language === "en" ? "en" : "zh" }
            }
        } catch { /* ignored */ }
    }

    const provider = localStorage.getItem(STORAGE_KEYS.clarifyProvider)
    const model = localStorage.getItem(STORAGE_KEYS.clarifyModel)
    const baseUrl = localStorage.getItem(STORAGE_KEYS.clarifyBaseUrl)
    const apiKey = localStorage.getItem(STORAGE_KEYS.clarifyApiKey)

    if (provider && model) {
        return {
            profile: {
                id: "settings-default",
                provider,
                model,
                baseUrl: baseUrl || "",
                apiKey: apiKey || "",
            },
            language: language === "en" ? "en" : "zh",
        }
    }

    return { profile: null, language: language === "en" ? "en" : "zh" }
}

export default function ChatPanel({ isVisible }: ChatPanelProps) {
    const [input, setInput] = useState("")
    const [showModelConfigDialog, setShowModelConfigDialog] = useState(false)
    const [showSettingsDialog, setShowSettingsDialog] = useState(false)
    const [showHistory, setShowHistory] = useState(false)
    const [isVectorworksHost, setIsVectorworksHost] = useState(false)
    const [lastResultPath, setLastResultPath] = useState<string | null>(null)
    const [forgeVisionForm, setForgeVisionForm] = useState<ForgeVisionFormResult | null>(null)
    const [bimModeEnabled, setBimModeEnabled] = useState(() => {
        if (typeof window === "undefined") return true
        return localStorage.getItem("openbimforge-bim-mode-enabled") !== "false"
    })
    const [clarifyUseSeparateModel, setClarifyUseSeparateModel] = useState(() => {
        if (typeof window === "undefined") return false
        const val = localStorage.getItem(STORAGE_KEYS.clarifyUseSeparateModel)
        return val === "true"
    })
    const [showUnvalidatedModels, setShowUnvalidatedModels] = useState(() => {
        if (typeof window === "undefined") return false
        return localStorage.getItem(STORAGE_KEYS.showUnvalidatedModels) === "true"
    })
    const modelConfig = useModelConfig()
    const conversationManager = useConversationManager()
    const messagesRef = useRef<any[]>([])
    const imageInputRef = useRef<HTMLInputElement | null>(null)
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const {
        attachment,
        clearAttachment,
        error: imageError,
        runLayout,
        selectFile,
    } = useImageUpload()

    const appendVoiceTranscript = useCallback((text: string) => {
        setInput((current) => {
            const trimmed = current.trimEnd()
            return trimmed ? `${trimmed} ${text}` : text
        })
    }, [])

    const {
        isListening,
        isSupported: isVoiceSupported,
        startListening,
        stopListening,
    } = useVoiceInput({
        language: "zh-CN",
        onFinalTranscript: appendVoiceTranscript,
    })

    const [sessionId, setSessionId] = useState(() => {
        if (typeof window === "undefined") return `session-${Date.now()}`
        const existing = localStorage.getItem("openbimforge-session-id")
        if (existing) return existing
        const next = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        localStorage.setItem("openbimforge-session-id", next)
        return next
    })

    const { messages, sendMessage, status, stop, setMessages } = useChat({
        transport: new DefaultChatTransport({ api: getApiEndpoint("/api/chat") }),
        onError: (err) => {
            try {
                const data = JSON.parse(err.message)
                toast.error(data.error || err.message)
            } catch {
                toast.error(err.message)
            }
        },
    })

    useEffect(() => {
        if (typeof window === "undefined") return
        const params = new URLSearchParams(window.location.search)
        setIsVectorworksHost(params.get("host") === "vectorworks")
    }, [])

    useEffect(() => {
        messagesRef.current = messages as any[]
    }, [messages])

    useEffect(() => {
        const handleHostMessage = (event: MessageEvent) => {
            const message = event.data || {}
            if (message.source !== "openBIMForgeVectorworksHost") return
            if (message.type !== "OPENBIMFORGE_VM_STATUS") return

            if (message.status === "running") {
                toast.info("Vectorworks VM 正在处理 Transit-Payload")
            } else if (message.status === "dispatched") {
                toast.success("已派发至 Vectorworks VM，等待结果写回")
            } else if (message.status === "failed") {
                toast.error(message.message || "Vectorworks VM 调度失败")
            }
        }

        window.addEventListener("message", handleHostMessage)
        return () => window.removeEventListener("message", handleHostMessage)
    }, [])

    const handleNewChat = useCallback(async () => {
        if (conversationManager.isAvailable && messagesRef.current.length > 0) {
            const { sanitizeMessages } = await import("@/lib/session-storage")
            const sessionData = {
                messages: sanitizeMessages(messagesRef.current),
                bimResults: lastResultPath ? [{ path: lastResultPath, timestamp: Date.now() }] : [],
            }
            await conversationManager.saveCurrentSession(sessionData)
            await conversationManager.refreshSessions()
        }

        conversationManager.clearCurrentSession()
        setMessages([])
        setInput("")
        setLastResultPath(null)
        setForgeVisionForm(null)
        const newSessionId = `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        setSessionId(newSessionId)
        localStorage.setItem("openbimforge-session-id", newSessionId)
        toast.success("Nexus 协同会话已重置")
    }, [conversationManager, lastResultPath, setMessages])

    useEffect(() => {
        localStorage.setItem(STORAGE_KEYS.bimModeEnabled, String(bimModeEnabled))
    }, [bimModeEnabled])

    useEffect(() => {
        localStorage.setItem(
            STORAGE_KEYS.clarifyUseSeparateModel,
            String(clarifyUseSeparateModel),
        )
    }, [clarifyUseSeparateModel])

    const send = () => {
        const text = input.trim()
        if (!text || status === "submitted" || status === "streaming") return

        const config = getSelectedAIConfig()
        const clarify = getActiveClarifyConfig()

        if (!config.aiProvider || !config.aiModel) {
            toast.error("请先在模型设置中选择 Nexus 主生成模型")
            setShowModelConfigDialog(true)
            return
        }

        setInput("")
        const p = localStorage.getItem("openbimforge-clarify-provider")
        const m = localStorage.getItem("openbimforge-clarify-model")
        const b = localStorage.getItem("openbimforge-clarify-base-url")
        const k = localStorage.getItem("openbimforge-clarify-api-key")

        sendMessage(
            { parts: [{ type: "text", text }] },
            {
                body: { sessionId },
                headers: {
                    "x-access-code": config.accessCode,
                    "x-ai-provider": config.aiProvider,
                    ...(config.aiBaseUrl && { "x-ai-base-url": config.aiBaseUrl }),
                    ...(config.aiApiKey && { "x-ai-api-key": config.aiApiKey }),
                    "x-ai-model": config.aiModel,
                    ...(config.selectedModelId && { "x-selected-model-id": config.selectedModelId }),
                    ...(config.awsAccessKeyId && { "x-aws-access-key-id": config.awsAccessKeyId }),
                    ...(config.awsSecretAccessKey && { "x-aws-secret-access-key": config.awsSecretAccessKey }),
                    ...(config.awsRegion && { "x-aws-region": config.awsRegion }),
                    ...(config.awsSessionToken && { "x-aws-session-token": config.awsSessionToken }),
                    ...(config.vertexApiKey && { "x-vertex-api-key": config.vertexApiKey }),
                    "x-bim-mode": String(bimModeEnabled),
                    "x-clarify-language": clarify.language || "zh",
                    ...(p && { "x-clarify-provider": p }),
                    ...(m && { "x-clarify-model": m }),
                    ...(b && { "x-clarify-base-url": b }),
                    ...(k && { "x-clarify-api-key": k }),
                },
            },
        )
    }

    const handleForgeVisionFormContinue = () => {
        if (!forgeVisionForm) return

        const config = getSelectedAIConfig()
        const clarify = getActiveClarifyConfig()

        if (!config.aiProvider || !config.aiModel) {
            toast.error("请先在模型设置中选择 Nexus 主生成模型")
            setShowModelConfigDialog(true)
            return
        }

        const forgeVisionData = JSON.stringify(forgeVisionForm, null, 2)
        const text = `[ForgeVision-Form 几何约束已载入]

【ForgeVisionConstraints】
${forgeVisionData}

【用户补充需求】
${input.trim() || "请根据上述图片形体约束生成初始 BIM 方案。"}

约束声明：
- [REFERENCE_ONLY] STL / preview 不是最终 BIM，只能作为建筑外轮廓、体量和构图参考。
- 请 Nexus 根据上述形体拓扑，使用 Vectorworks 原生组件（墙、板、窗、楼层等）进行语义化 BIM 重构。
- 不要伪造面积、楼层、高度等未从用户需求或图片结果中明确给出的工程数值。`
        
        setInput("")
        setForgeVisionForm(null)
        
        const p = localStorage.getItem("openbimforge-clarify-provider")
        const m = localStorage.getItem("openbimforge-clarify-model")
        const b = localStorage.getItem("openbimforge-clarify-base-url")
        const k = localStorage.getItem("openbimforge-clarify-api-key")

        sendMessage(
            { parts: [{ type: "text", text }] },
            {
                body: { sessionId },
                headers: {
                    "x-access-code": config.accessCode,
                    "x-ai-provider": config.aiProvider,
                    ...(config.aiBaseUrl && { "x-ai-base-url": config.aiBaseUrl }),
                    ...(config.aiApiKey && { "x-ai-api-key": config.aiApiKey }),
                    "x-ai-model": config.aiModel,
                    ...(config.selectedModelId && { "x-selected-model-id": config.selectedModelId }),
                    ...(config.awsAccessKeyId && { "x-aws-access-key-id": config.awsAccessKeyId }),
                    ...(config.awsSecretAccessKey && { "x-aws-secret-access-key": config.awsSecretAccessKey }),
                    ...(config.awsRegion && { "x-aws-region": config.awsRegion }),
                    ...(config.awsSessionToken && { "x-aws-session-token": config.awsSessionToken }),
                    ...(config.vertexApiKey && { "x-vertex-api-key": config.vertexApiKey }),
                    "x-bim-mode": String(bimModeEnabled),
                    "x-clarify-language": clarify.language || "zh",
                    ...(p && { "x-clarify-provider": p }),
                    ...(m && { "x-clarify-model": m }),
                    ...(b && { "x-clarify-base-url": b }),
                    ...(k && { "x-clarify-api-key": k }),
                },
            },
        )
    }

    const sendToLayoutAgent = async () => {
        const result = await runLayout(sessionId)
        const resultRecord = (result.result || {}) as Record<string, any>
        const debugEvents = Array.isArray(resultRecord.debug?.events)
            ? resultRecord.debug.events.map((event: any) =>
                  `${event.at || ""} ${event.message || ""}`.trim(),
              )
            : []
        const layoutResult = (resultRecord.result || resultRecord) as Record<string, any>
        const payload = {
            title: "ForgeVision-Form Result",
            status: result.ok ? "success" : "failed",
            mode: "ForgeVision-Form",
            stages: [
                {
                    id: "layout_upload",
                    label: "Topology Input (图片上传)",
                    status: "completed",
                    detail: attachment?.file.name || "Visual topology uploaded.",
                },
                {
                    id: "layout_agent",
                    label: "ForgeVision-Form (形体转化)",
                    status: result.ok ? "completed" : "failed",
                    detail: result.ok
                        ? "ForgeVision-Form returned massing reference outputs."
                        : result.error || "ForgeVision-Form interpretation failed.",
                },
            ],
            logs: [
                ...debugEvents,
                layoutResult?.log_path ? `Topology log: ${layoutResult.log_path}` : "",
            ].filter(Boolean),
            summary: result.ok
                ? "图片形体参考已交付至 ForgeVision-Form，可继续进入 Nexus BIM 生成。"
                : `ForgeVision-Form 转化中断：${result.error || "请检查后端日志。"}`,
            result,
        }

        setMessages((current: any[]) => [
            ...current,
            {
                id: `layout-result-${Date.now()}`,
                role: "assistant",
                parts: [
                    {
                        type: "text",
                        text: `<execution-log>${JSON.stringify(payload)}</execution-log>`,
                    },
                ],
            },
        ])

        if (result.ok) {
            toast.success("ForgeVision-Form 转化完成")
            clearAttachment()
            const nextForgeVisionForm = resultRecord.forgeVisionForm || resultRecord.normalizedVisionary
            if (nextForgeVisionForm) {
                const form = nextForgeVisionForm as ForgeVisionFormResult
                if (form.stlPaths.length > 0 || form.previewPaths.length > 0) {
                    setForgeVisionForm(form)
                }
            }
        } else if (result.error) {
            toast.error(result.error)
        }
    }

    if (!isVisible) return null

    const isBusy = status === "submitted" || status === "streaming"
    const voiceDisabled = isBusy || !isVoiceSupported || isVectorworksHost
    const voiceButtonTitle = isVectorworksHost
        ? "Vectorworks Web Palette 不开放麦克风权限，请在浏览器版使用语音"
        : !isVoiceSupported
        ? "当前环境不支持语义听写"
        : isListening
            ? "停止听写"
            : "开启语义听写"

    return (
        <div className="flex h-full flex-col overflow-hidden rounded-[2rem] border border-zinc-200/70 bg-gradient-to-br from-white via-zinc-50 to-sky-50 shadow-2xl">
            <Toaster position="top-center" />
            <header className="flex items-center justify-end border-b border-zinc-200/70 bg-white/80 px-5 py-3 backdrop-blur-xl">
                <div className="flex items-center gap-2">
                    <ButtonWithTooltip
                        tooltipContent="开启新协同会话"
                        variant="ghost"
                        size="icon"
                        onClick={handleNewChat}
                        disabled={isBusy}
                        className="hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <MessageSquarePlus className="h-5 w-5 text-muted-foreground" />
                    </ButtonWithTooltip>
                    <ButtonWithTooltip
                        tooltipContent="BIM Synthesis Workbench"
                        variant="outline"
                        size="icon"
                        onClick={() => window.location.assign("/bim/vectorworks?host=vectorworks")}
                    >
                        <Wrench className="h-4 w-4" />
                    </ButtonWithTooltip>
                    <ButtonWithTooltip
                        tooltipContent="Nexus Framework 设置"
                        variant="outline"
                        size="icon"
                        onClick={() => setShowSettingsDialog(true)}
                    >
                        <Settings className="h-4 w-4" />
                    </ButtonWithTooltip>
                </div>
            </header>

            <main className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
                <div className="mx-auto flex max-w-5xl flex-col gap-5">
                    {messages.length === 0 ? (
                        <div className="rounded-[2rem] border border-zinc-200/70 bg-white/80 p-8 shadow-sm">
                            <p className="text-sm uppercase tracking-[0.3em] text-zinc-500">Nexus-Orchestration Center</p>
                            <h2 className="mt-4 text-3xl font-semibold tracking-tight">从语义需求发起 Constructive Synthesis</h2>
                            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                                输入建筑类型、楼层、容积等语义参数。Nexus 框架将调度 Architect-Agent 进行逻辑规划、Constructor-Agent 执行物理合成并导出 Digital BIM Assets。
                            </p>
                            <button
                                type="button"
                                onClick={() => setInput("发起一个办公建筑合成任务，6层，总面积4200平方米，典型层高3.6米。")}
                                className="mt-6 rounded-full bg-zinc-950 px-5 py-2 text-sm text-white hover:bg-zinc-800"
                            >
                                载入示例语义
                            </button>
                        </div>
                    ) : (
                        messages.map((message) => (
                            <ChatMessageDisplay key={message.id} message={message} />
                        ))
                    )}
                </div>
            </main>

            <footer className="p-4">
                <div className="mx-auto max-w-5xl">
                    {attachment && (
                        <div className="mb-2 flex items-center gap-3 rounded-2xl border border-zinc-200 bg-white/80 p-2 text-sm shadow-sm">
                            <Image
                                src={attachment.previewUrl}
                                alt="Visual Topology Reference"
                                width={56}
                                height={56}
                                unoptimized
                                className="h-14 w-14 rounded-xl object-cover"
                            />
                            <div className="min-w-0 flex-1">
                                <p className="truncate font-medium text-zinc-800">{attachment.file.name}</p>
                                <p className="text-xs text-zinc-500">已就绪，可交付至 Layout-Agent 执行空间转化。</p>
                            </div>
                            <Button type="button" variant="ghost" size="icon" onClick={clearAttachment} title="移除拓扑参考">
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    )}
                    {imageError && (
                        <p className="mb-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                            {imageError}
                        </p>
                    )}

                    <div className="input-capsule">
                        <div className="relative">
                            <Textarea
                                ref={textareaRef}
                                value={input}
                                onChange={(event) => setInput(event.target.value)}
                                onKeyDown={(event) => {
                                    if (event.key === "Enter" && !event.shiftKey) {
                                        event.preventDefault()
                                        send()
                                    }
                                }}
                                placeholder="输入语义需求或跨模态意图..."
                                className="min-h-[56px] max-h-[168px] resize-none border-0 bg-transparent px-4 py-3 text-sm focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/60 rounded-none"
                                rows={2}
                            />
                        </div>
                        <div className="input-toolbar">
                            <div className="input-toolbar-left">
                                <ButtonWithTooltip
                                    tooltipContent="上传图片作为 ForgeVision-Form 形体参考"
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                                    onClick={() => imageInputRef.current?.click()}
                                    disabled={isBusy}
                                >
                                    <ImageIcon className="h-4 w-4" />
                                </ButtonWithTooltip>
                                <ButtonWithTooltip
                                    tooltipContent={voiceButtonTitle}
                                    type="button"
                                    variant={isListening ? "secondary" : "ghost"}
                                    size="sm"
                                    className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                                    onClick={() => {
                                        if (isListening) {
                                            stopListening()
                                        } else {
                                            startListening()
                                        }
                                    }}
                                    disabled={voiceDisabled}
                                >
                                    {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                                </ButtonWithTooltip>
                                <ButtonWithTooltip
                                    tooltipContent="协同历史"
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                                    onClick={() => setShowHistory(true)}
                                    disabled={conversationManager.sessions.length === 0}
                                >
                                    <History className="h-4 w-4" />
                                </ButtonWithTooltip>
                                <div className="w-px h-5 bg-border mx-1" />
                                <ModelSelector
                                    models={modelConfig.models}
                                    selectedModelId={modelConfig.selectedModelId}
                                    onSelect={modelConfig.setSelectedModelId}
                                    onConfigure={() => setShowModelConfigDialog(true)}
                                    disabled={isBusy}
                                    showUnvalidatedModels={showUnvalidatedModels}
                                />
                            </div>
                            <div className="input-toolbar-right">
                                {forgeVisionForm && !isBusy && (
                                    <Button
                                        className="h-8 rounded-xl bg-indigo-600 px-3 text-xs text-white hover:bg-indigo-700 mr-2"
                                        onClick={handleForgeVisionFormContinue}
                                        size="sm"
                                    >
                                        采用图片形体继续生成 BIM
                                    </Button>
                                )}
                                {attachment && !isBusy && (
                                    <Button
                                        className="h-8 rounded-xl bg-sky-600 px-3 text-xs text-white hover:bg-sky-700"
                                        onClick={sendToLayoutAgent}
                                        size="sm"
                                    >
                                        交付 ForgeVision-Form
                                    </Button>
                                )}
                                {isBusy ? (
                                    <Button
                                        className="h-8 w-8 rounded-xl p-0"
                                        onClick={() => stop()}
                                        size="sm"
                                        variant="destructive"
                                    >
                                        <Square className="h-4 w-4" />
                                    </Button>
                                ) : (
                                    <Button
                                        className="h-8 w-8 rounded-xl p-0"
                                        onClick={send}
                                        disabled={!input.trim() && !attachment}
                                        size="sm"
                                    >
                                        <Send className="h-4 w-4" />
                                    </Button>
                                )}
                            </div>
                        </div>
                    </div>

                    <input
                        ref={imageInputRef}
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        className="hidden"
                        onChange={(event) => {
                            selectFile(event.target.files?.[0] || null)
                            setForgeVisionForm(null)
                            event.currentTarget.value = ""
                        }}
                    />
                </div>
            </footer>

            <SettingsDialog
                open={showSettingsDialog}
                onOpenChange={setShowSettingsDialog}
                onOpenModelConfig={() => setShowModelConfigDialog(true)}
                bimModeEnabled={bimModeEnabled}
                onBimModeEnabledChange={setBimModeEnabled}
                clarifyUseSeparateModel={clarifyUseSeparateModel}
                onClarifyUseSeparateModelChange={setClarifyUseSeparateModel}
                showUnvalidatedModels={showUnvalidatedModels}
                onShowUnvalidatedModelsChange={(show) => {
                    setShowUnvalidatedModels(show)
                    localStorage.setItem(STORAGE_KEYS.showUnvalidatedModels, String(show))
                    modelConfig.setShowUnvalidatedModels(show)
                }}
            />

            <ModelConfigDialog
                open={showModelConfigDialog}
                onOpenChange={setShowModelConfigDialog}
                modelConfig={modelConfig}
            />

            <ChatHistoryPanel
                open={showHistory}
                onOpenChange={setShowHistory}
                sessions={conversationManager.sessions}
                onSelectSession={async (id) => {
                    const data = await conversationManager.switchSession(id)
                    if (data) {
                        setMessages(data.messages as any)
                        setSessionId(id)
                        localStorage.setItem("openbimforge-session-id", id)
                    }
                }}
                onDeleteSession={async (id) => {
                    await conversationManager.deleteSession(id)
                }}
            />
        </div>
    )
}
