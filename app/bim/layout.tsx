import type { Metadata, Viewport } from "next"
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google"
import { DevLogProviderWrapper } from "@/components/dev-log-provider"

import "../globals.css"

const plusJakarta = Plus_Jakarta_Sans({
    variable: "--font-sans",
    subsets: ["latin"],
    weight: ["400", "500", "600", "700"],
})

const jetbrainsMono = JetBrains_Mono({
    variable: "--font-mono",
    subsets: ["latin"],
    weight: ["400", "500"],
})

export const metadata: Metadata = {
    title: "openBIMForge Vectorworks Console",
    description:
        "Vectorworks embedded console for openBIMForge Design Agent, Runner, and IFC workflows.",
}

export const viewport: Viewport = {
    width: "device-width",
    initialScale: 1,
    maximumScale: 1,
    userScalable: false,
}

export default function BimLayout({ children }: Readonly<{ children: React.ReactNode }>) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body className={`${plusJakarta.variable} ${jetbrainsMono.variable} antialiased`}>
                <DevLogProviderWrapper>
                    {children}
                </DevLogProviderWrapper>
            </body>
        </html>
    )
}
