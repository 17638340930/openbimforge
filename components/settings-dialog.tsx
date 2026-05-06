"use client"

import {
    Bot,
    ChevronRight,
    Eye,
    EyeOff,
    MessageCircle,
    X,
} from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { STORAGE_KEYS } from "@/lib/storage"

interface SettingsDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onOpenModelConfig: () => void
    bimModeEnabled: boolean
    onBimModeEnabledChange: (enabled: boolean) => void
    clarifyUseSeparateModel: boolean
    onClarifyUseSeparateModelChange: (enabled: boolean) => void
    showUnvalidatedModels: boolean
    onShowUnvalidatedModelsChange: (show: boolean) => void
}

const CLARIFY_PROVIDERS = [
    { value: "ollama", label: "Ollama (本地)" },
    { value: "openai", label: "OpenAI" },
    { value: "deepseek", label: "DeepSeek" },
    { value: "anthropic", label: "Anthropic" },
]

const CLARIFY_MODELS: Record<string, string[]> = {
    ollama: ["qwen2.5-coder:7b-instruct-q4_K_M", "qwen2.5:7b", "llama3.1:8b", "deepseek-r1:7b"],
    openai: ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
    deepseek: ["deepseek-chat", "deepseek-coder"],
    anthropic: ["claude-sonnet-4-20250514", "claude-haiku-4-20250414"],
}

const DEFAULT_CLARIFY_BASE_URL: Record<string, string> = {
    ollama: "http://127.0.0.1:11434",
    openai: "https://api.openai.com/v1",
    deepseek: "https://api.deepseek.com/v1",
    anthropic: "https://api.anthropic.com",
}

export function SettingsDialog({
    open,
    onOpenChange,
    onOpenModelConfig,
    bimModeEnabled,
    onBimModeEnabledChange,
    clarifyUseSeparateModel,
    onClarifyUseSeparateModelChange,
    showUnvalidatedModels,
    onShowUnvalidatedModelsChange,
}: SettingsDialogProps) {
    const [clarifyProvider, setClarifyProvider] = useState(() => {
        if (typeof window === "undefined") return "ollama"
        return localStorage.getItem(STORAGE_KEYS.clarifyProvider) || "ollama"
    })
    const [clarifyModel, setClarifyModel] = useState(() => {
        if (typeof window === "undefined") return "qwen2.5-coder:7b-instruct-q4_K_M"
        return localStorage.getItem(STORAGE_KEYS.clarifyModel) || "qwen2.5-coder:7b-instruct-q4_K_M"
    })
    const [clarifyBaseUrl, setClarifyBaseUrl] = useState(() => {
        if (typeof window === "undefined") return "http://127.0.0.1:11434"
        return localStorage.getItem(STORAGE_KEYS.clarifyBaseUrl) || "http://127.0.0.1:11434"
    })
    const [clarifyApiKey, setClarifyApiKey] = useState(() => {
        if (typeof window === "undefined") return "ollama"
        return localStorage.getItem(STORAGE_KEYS.clarifyApiKey) || "ollama"
    })
    const [showClarifyApiKey, setShowClarifyApiKey] = useState(false)
    const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "error">("idle")
    const [testMessage, setTestMessage] = useState("")

    const handleProviderChange = (provider: string) => {
        setClarifyProvider(provider)
        setClarifyModel(CLARIFY_MODELS[provider]?.[0] || "")
        setClarifyBaseUrl(DEFAULT_CLARIFY_BASE_URL[provider] || "")
        setClarifyApiKey(provider === "ollama" ? "ollama" : "")
        localStorage.setItem(STORAGE_KEYS.clarifyProvider, provider)
        localStorage.setItem(STORAGE_KEYS.clarifyModel, CLARIFY_MODELS[provider]?.[0] || "")
        localStorage.setItem(STORAGE_KEYS.clarifyBaseUrl, DEFAULT_CLARIFY_BASE_URL[provider] || "")
        localStorage.setItem(STORAGE_KEYS.clarifyApiKey, provider === "ollama" ? "ollama" : "")
    }

    const handleModelChange = (model: string) => {
        setClarifyModel(model)
        localStorage.setItem(STORAGE_KEYS.clarifyModel, model)
    }

    const handleBaseUrlChange = (url: string) => {
        setClarifyBaseUrl(url)
        localStorage.setItem(STORAGE_KEYS.clarifyBaseUrl, url)
    }

    const handleApiKeyChange = (key: string) => {
        setClarifyApiKey(key)
        localStorage.setItem(STORAGE_KEYS.clarifyApiKey, key)
    }

    const testConnection = async () => {
        setTestStatus("testing")
        setTestMessage("")
        try {
            const baseUrl = clarifyBaseUrl.replace(/\/+$/, "")
            const endpoint = clarifyProvider === "ollama"
                ? `${baseUrl}/v1/chat/completions`
                : `${baseUrl}/chat/completions`

            const res = await fetch(endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(clarifyApiKey && { Authorization: `Bearer ${clarifyApiKey}` }),
                },
                body: JSON.stringify({
                    model: clarifyModel,
                    messages: [{ role: "user", content: "hi" }],
                    max_tokens: 5,
                }),
            })

            if (res.ok) {
                setTestStatus("ok")
                setTestMessage("连接成功")
            } else {
                const text = await res.text().catch(() => "")
                setTestStatus("error")
                setTestMessage(`HTTP ${res.status}: ${text.slice(0, 100)}`)
            }
        } catch (err: any) {
            setTestStatus("error")
            setTestMessage(err?.message || "连接失败")
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>设置</DialogTitle>
                    <DialogDescription className="sr-only">
                        应用设置和 BIM 追问环配置
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-2">
                    {/* AI Model Config Navigation */}
                    <div className="space-y-3">
                        <div className="flex items-center gap-2">
                            <Bot className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium">AI 模型配置</span>
                        </div>
                        <button
                            type="button"
                            className="w-full flex items-center justify-between p-3 rounded-lg border border-border/60 bg-card hover:bg-accent/50 hover:border-primary/30 transition-all text-left"
                            onClick={() => {
                                onOpenChange(false)
                                onOpenModelConfig()
                            }}
                        >
                            <div>
                                <div className="text-sm font-medium">管理 API Key、模型和提供商</div>
                                <div className="text-xs text-muted-foreground mt-0.5">
                                    配置主生成模型的提供商、API Key 和模型列表
                                </div>
                            </div>
                            <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                        </button>
                    </div>

                    <div className="h-px bg-border/60" />

                    {/* BIM Clarification Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2">
                            <MessageCircle className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium">BIM 追问环</span>
                        </div>

                        <div className="space-y-4 pl-6">
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label
                                        htmlFor="bim-mode-enabled"
                                        className="text-sm cursor-pointer"
                                    >
                                        启用追问环
                                    </Label>
                                    <p className="text-xs text-muted-foreground">
                                        先做参数完整性检查，不完整时先追问再进入主流程
                                    </p>
                                </div>
                                <Switch
                                    id="bim-mode-enabled"
                                    checked={bimModeEnabled}
                                    onCheckedChange={onBimModeEnabledChange}
                                />
                            </div>

                            {bimModeEnabled && (
                                <div className="space-y-4 p-4 rounded-lg border border-border/60 bg-surface-2/30">
                                    <div className="flex items-center justify-between">
                                        <div className="space-y-0.5">
                                            <Label
                                                htmlFor="clarify-separate-model"
                                                className="text-sm cursor-pointer"
                                            >
                                                使用独立模型
                                            </Label>
                                            <p className="text-xs text-muted-foreground">
                                                追问阶段使用独立模型
                                            </p>
                                        </div>
                                        <Switch
                                            id="clarify-separate-model"
                                            checked={clarifyUseSeparateModel}
                                            onCheckedChange={onClarifyUseSeparateModelChange}
                                        />
                                    </div>

                                    {clarifyUseSeparateModel && (
                                        <div className="space-y-3 pt-2">
                                            <div className="space-y-1.5">
                                                <Label className="text-xs">提供商</Label>
                                                <Select
                                                    value={clarifyProvider}
                                                    onValueChange={handleProviderChange}
                                                >
                                                    <SelectTrigger className="h-9">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {CLARIFY_PROVIDERS.map((p) => (
                                                            <SelectItem key={p.value} value={p.value}>
                                                                {p.label}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-1.5">
                                                <Label className="text-xs">模型</Label>
                                                <Select
                                                    value={clarifyModel}
                                                    onValueChange={handleModelChange}
                                                >
                                                    <SelectTrigger className="h-9">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {(CLARIFY_MODELS[clarifyProvider] || []).map((m) => (
                                                            <SelectItem key={m} value={m}>
                                                                {m}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-1.5">
                                                <Label className="text-xs">Base URL</Label>
                                                <Input
                                                    value={clarifyBaseUrl}
                                                    onChange={(e) => handleBaseUrlChange(e.target.value)}
                                                    className="h-9 text-sm"
                                                    placeholder="http://127.0.0.1:11434"
                                                />
                                            </div>

                                            <div className="space-y-1.5">
                                                <Label className="text-xs">API Key</Label>
                                                <div className="relative">
                                                    <Input
                                                        type={showClarifyApiKey ? "text" : "password"}
                                                        value={clarifyApiKey}
                                                        onChange={(e) => handleApiKeyChange(e.target.value)}
                                                        className="h-9 text-sm pr-9"
                                                        placeholder="ollama"
                                                    />
                                                    <button
                                                        type="button"
                                                        onClick={() => setShowClarifyApiKey(!showClarifyApiKey)}
                                                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                                                    >
                                                        {showClarifyApiKey ? (
                                                            <EyeOff className="h-3.5 w-3.5" />
                                                        ) : (
                                                            <Eye className="h-3.5 w-3.5" />
                                                        )}
                                                    </button>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2 pt-1">
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    size="sm"
                                                    className="h-8 text-xs"
                                                    onClick={testConnection}
                                                    disabled={testStatus === "testing"}
                                                >
                                                    {testStatus === "testing" ? "测试中..." : "测试连接"}
                                                </Button>
                                                {testStatus === "ok" && (
                                                    <span className="text-xs text-green-600">{testMessage}</span>
                                                )}
                                                {testStatus === "error" && (
                                                    <span className="text-xs text-destructive">{testMessage}</span>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="h-px bg-border/60" />

                    {/* Other Settings */}
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label
                                    htmlFor="show-unvalidated"
                                    className="text-sm cursor-pointer"
                                >
                                    显示未验证模型
                                </Label>
                                <p className="text-xs text-muted-foreground">
                                    API Key 存储在浏览器本地
                                </p>
                            </div>
                            <Switch
                                id="show-unvalidated"
                                checked={showUnvalidatedModels}
                                onCheckedChange={onShowUnvalidatedModelsChange}
                            />
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
