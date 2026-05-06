"use client"

import { Suspense, useEffect, useState } from "react"
import ChatPanel from "@/components/chat-panel"

export default function Home() {
    const [isMobile, setIsMobile] = useState(false)

    useEffect(() => {
        localStorage.setItem("openbimforge-locale", "zh")
        localStorage.setItem("openbimforge-bim-mode-enabled", "true")

        const checkMobile = () => setIsMobile(window.innerWidth < 768)
        checkMobile()
        window.addEventListener("resize", checkMobile)
        return () => window.removeEventListener("resize", checkMobile)
    }, [])

    return (
        <div className="h-screen bg-background relative overflow-hidden">
            <div className="h-full p-2">
                <Suspense
                    fallback={
                        <div className="h-full bg-card rounded-xl border border-border/30 flex items-center justify-center text-muted-foreground">
                            正在加载 openBIMForge BIM 工作台...
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
