import { NextResponse } from "next/server"

export const runtime = "nodejs"

/**
 * Legacy API Endpoint: /api/layout/run
 * Redirects and forwards requests to the Nexus-Visionary (Layout-Agent) within the Nexus Framework.
 */
export async function POST(req: Request) {
    try {
        const url = new URL(req.url)
        const targetUrl = new URL("/api/bim/forge-architect-visionary", url.origin)
        
        const response = await fetch(targetUrl.toString(), {
            method: "POST",
            headers: req.headers,
            body: req.body,
            // @ts-ignore
            duplex: "half"
        })

        const data = await response.json()
        return NextResponse.json({
            ...data,
            source: "nexus-visionary-legacy-bridge"
        })
    } catch (error) {
        return NextResponse.json({
            ok: false,
            error: error instanceof Error ? error.message : "Nexus Visionary legacy bridge disruption."
        }, { status: 500 })
    }
}
