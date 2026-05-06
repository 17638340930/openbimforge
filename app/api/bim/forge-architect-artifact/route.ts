import { promises as fs } from "fs"
import path from "path"
import { getNexusRuntimeRoots, isPathInsideRoots } from "@/lib/bim/openbimforge-paths"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

function getAllowedRoots(): string[] {
    return getNexusRuntimeRoots([
        "runtime_handoffs",
        "runtime_artifacts",
        "runtime_state",
    ])
}

function isAllowedPath(targetPath: string): boolean {
    return isPathInsideRoots(targetPath, getAllowedRoots())
}

function getContentType(filePath: string): string {
    const ext = path.extname(filePath).toLowerCase()
    switch (ext) {
        case ".json":
            return "application/json; charset=utf-8"
        case ".ifc":
            return "text/plain; charset=utf-8"
        case ".py":
            return "text/x-python; charset=utf-8"
        case ".txt":
            return "text/plain; charset=utf-8"
        case ".vwx":
            return "application/octet-stream"
        default:
            return "application/octet-stream"
    }
}

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url)
    const targetPath = searchParams.get("path")
    const mode = searchParams.get("mode") || "download"

    if (!targetPath) {
        return NextResponse.json(
            { ok: false, error: "Missing path query parameter." },
            { status: 400 },
        )
    }

    if (!isAllowedPath(targetPath)) {
        return NextResponse.json(
            { ok: false, error: "Requested Digital BIM Asset path is outside the allowed Nexus runtime directories." },
            { status: 403 },
        )
    }

    try {
        const fileBuffer = await fs.readFile(targetPath)
        const headers = new Headers({
            "content-type": getContentType(targetPath),
            "x-nexus-asset-type": "digital-bim-asset"
        })

        if (mode !== "inline") {
            headers.set(
                "content-disposition",
                `attachment; filename="${path.basename(targetPath)}"`,
            )
        }

        return new NextResponse(fileBuffer, {
            status: 200,
            headers,
        })
    } catch (error) {
        return NextResponse.json(
            {
                ok: false,
                error:
                    error instanceof Error
                        ? error.message
                        : "Failed to retrieve Digital BIM Asset.",
            },
            { status: 404 },
        )
    }
}
