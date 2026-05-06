"use client"

import { DevLogProvider } from "@/contexts/dev-log-store"
import type { ReactNode } from "react"

export function DevLogProviderWrapper({ children }: { children: ReactNode }) {
    return <DevLogProvider>{children}</DevLogProvider>
}
