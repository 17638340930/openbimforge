import { runNexusArchitectAdapter } from "@/lib/bim/forge-architect-adapter"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

/**
 * @deprecated Legacy API Endpoint: /api/bim/text2bim
 * Redirects and forwards requests to the Nexus Multi-Agent Orchestration Framework.
 * Maintaining this for backward compatibility with older Vectorworks plugins.
 * New clients should call /api/chat or the forge-architect routes directly.
 */
export async function POST(req: Request) {
    try {
        const body = await req.json()
        
        // Map legacy fields to Nexus schema
        const input = {
            query: body.query || "",
            chatHistory: body.chat_history || "",
            sessionId: body.session_id || "",
            mode: body.mode || "live",
            llmConfig: body.llm_config || {},
            executionConfig: {
                executionMode: body.execution_mode || "vectorworks",
                ...body.execution_config
            }
        }

        const result = await runNexusArchitectAdapter(input)

        return NextResponse.json({
            ...result,
            ok: result.ok,
            source: "nexus-legacy-bridge-adapter",
            note: "Successfully forwarded legacy Text2BIM request to Nexus-Orchestrator."
        })
    } catch (error) {
        return NextResponse.json({
            ok: false,
            error: error instanceof Error ? error.message : "Nexus legacy bridge disruption."
        }, { status: 500 })
    }
}
