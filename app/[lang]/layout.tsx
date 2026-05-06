import { GoogleAnalytics } from "@next/third-parties/google"
import type { Metadata, Viewport } from "next"
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google"
import { notFound } from "next/navigation"
import { DictionaryProvider } from "@/hooks/use-dictionary"
import { DevLogProviderWrapper } from "@/components/dev-log-provider"
import type { Locale } from "@/lib/i18n/config"
import { i18n } from "@/lib/i18n/config"
import { getAssetUrl, getBasePath } from "@/lib/base-path"
import { getDictionary, hasLocale } from "@/lib/i18n/dictionaries"

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

function getSiteUrl(): URL {
    const configuredUrl = process.env.NEXT_PUBLIC_APP_URL
    const vercelUrl = process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : undefined
    return new URL(configuredUrl || vercelUrl || "http://localhost:6002")
}

export const viewport: Viewport = {
    width: "device-width",
    initialScale: 1,
    maximumScale: 1,
    userScalable: false,
}

export async function generateStaticParams() {
    return i18n.locales.map((locale) => ({ lang: locale }))
}

export async function generateMetadata({
    params,
}: {
    params: Promise<{ lang: string }>
}): Promise<Metadata> {
    const { lang: rawLang } = await params
    const lang = (
        rawLang in { en: 1, zh: 1, ja: 1, "zh-Hant": 1 } ? rawLang : "en"
    ) as Locale

    const titles: Record<Locale, string> = {
        en: "openBIMForge - Multi-Agent BIM Generation",
        zh: "openBIMForge - 多智能体 BIM 生成工作台",
        ja: "openBIMForge - マルチエージェント BIM 生成",
        "zh-Hant": "openBIMForge - 多智能體 BIM 生成工作台",
    }

    const descriptions: Record<Locale, string> = {
        en: "Generate BIM design intent, Vectorworks execution packages, VWX files, and IFC artifacts through a multi-agent design and build workflow.",
        zh: "通过多智能体设计与执行链路生成 BIM 方案、Vectorworks 执行包、VWX 文件与 IFC 成果。",
        ja: "マルチエージェントの設計・実行ワークフローで BIM 設計意図、Vectorworks 実行パッケージ、VWX、IFC を生成します。",
        "zh-Hant":
            "透過多智能體設計與執行鏈路生成 BIM 方案、Vectorworks 執行包、VWX 檔案與 IFC 成果。",
    }

    const siteUrl = getSiteUrl()
    const basePath = getBasePath()
    const localePath = `${basePath}/${lang}`
    const architectureImage = getAssetUrl("/architecture.png")
    const favicon = getAssetUrl("/favicon.ico")

    return {
        title: titles[lang],
        description: descriptions[lang],
        keywords: [
            "openBIMForge",
            "BIM generation",
            "Vectorworks",
            "IFC export",
            "multi-agent BIM",
            "Design Agent",
            "Build Agent",
        ],
        authors: [{ name: "JY" }],
        creator: "openBIMForge",
        publisher: "openBIMForge",
        metadataBase: siteUrl,
        openGraph: {
            title: titles[lang],
            description: descriptions[lang],
            type: "website",
            url: localePath,
            siteName: "openBIMForge",
            locale:
                lang === "zh"
                    ? "zh_CN"
                    : lang === "zh-Hant"
                      ? "zh_HK"
                      : lang === "ja"
                        ? "ja_JP"
                        : "en_US",
            images: [
                {
                    url: architectureImage,
                    width: 1200,
                    height: 630,
                    alt: "openBIMForge - multi-agent BIM generation workbench",
                },
            ],
        },
        twitter: {
            card: "summary_large_image",
            title: titles[lang],
            description: descriptions[lang],
            images: [architectureImage],
        },
        robots: {
            index: true,
            follow: true,
            googleBot: {
                index: true,
                follow: true,
                "max-video-preview": -1,
                "max-image-preview": "large",
                "max-snippet": -1,
            },
        },
        icons: {
            icon: favicon,
        },
        alternates: {
            languages: {
                en: `${basePath}/en`,
                zh: `${basePath}/zh`,
                ja: `${basePath}/ja`,
                "zh-Hant": `${basePath}/zh-Hant`,
            },
        },
    }
}

export default async function RootLayout({
    children,
    params,
}: Readonly<{
    children: React.ReactNode
    params: Promise<{ lang: string }>
}>) {
    const { lang } = await params
    if (!hasLocale(lang)) notFound()
    const validLang = lang as Locale
    const dictionary = await getDictionary(validLang)
    const appUrl = new URL(`${getBasePath()}/${validLang}`, getSiteUrl()).toString()

    const jsonLd = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        name: "openBIMForge",
        applicationCategory: "DesignApplication",
        operatingSystem: "Web Browser",
        description:
            "Multi-agent BIM generation workbench that connects Design Agent planning, Vectorworks execution, VWX output, and IFC export.",
        url: appUrl,
        inLanguage: validLang,
        offers: {
            "@type": "Offer",
            price: "0",
            priceCurrency: "USD",
        },
    }

    return (
        <html lang={validLang} suppressHydrationWarning>
            <head>
                <script
                    type="application/ld+json"
                    dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
                />
            </head>
            <body
                className={`${plusJakarta.variable} ${jetbrainsMono.variable} antialiased`}
            >
                <DevLogProviderWrapper>
                    <DictionaryProvider dictionary={dictionary}>
                        {children}
                    </DictionaryProvider>
                </DevLogProviderWrapper>
            </body>
            {process.env.NEXT_PUBLIC_GA_ID && (
                <GoogleAnalytics gaId={process.env.NEXT_PUBLIC_GA_ID} />
            )}
        </html>
    )
}
