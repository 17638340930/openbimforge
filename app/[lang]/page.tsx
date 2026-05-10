"use client"

import { use, Suspense, useEffect, useState } from "react"
import ChatPanel from "@/components/chat-panel"

const LOADING_FALLBACK: Record<string, string> = {
    en: "Loading the openBIMForge workbench...",
    zh: "正在加载 openBIMForge BIM 工作台...",
    ja: "openBIMForge ワークベンチを読み込み中...",
    "zh-Hant": "正在載入 openBIMForge BIM 工作台...",
}

function normalizeLocale(value: string): string {
    if (value in LOADING_FALLBACK) return value
    return "en"
}

export default function Home({
    params,
}: {
    params: Promise<{ lang: string }>
}) {
    const { lang } = use(params)
    const locale = normalizeLocale(lang)
    const [isMobile, setIsMobile] = useState(false)

    useEffect(() => {
        // Persist the locale resolved from the URL so downstream components
        // (chat-panel, vectorworks-console) can keep rendering in the same
        // language as the active route.
        localStorage.setItem("openbimforge-locale", locale)
        localStorage.setItem("openbimforge-bim-mode-enabled", "true")

        const checkMobile = () => setIsMobile(window.innerWidth < 768)
        checkMobile()
        window.addEventListener("resize", checkMobile)
        return () => window.removeEventListener("resize", checkMobile)
    }, [locale])

    return (
        <div className="h-screen bg-background relative overflow-hidden">
            <div className="h-full p-2">
                <Suspense
                    fallback={
                        <div className="h-full bg-card rounded-xl border border-border/30 flex items-center justify-center text-muted-foreground">
                            {LOADING_FALLBACK[locale]}
                        </div>
                    }
                >
                    <ChatPanel
                        isVisible={true}
                        onToggleVisibility={() => undefined}
                        isMobile={isMobile}
                    />
                </Suspense>
            </div>
        </div>
    )
}
