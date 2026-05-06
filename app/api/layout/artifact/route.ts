import { promises as fs } from "node:fs"
import path from "node:path"
import { getOpenBimForgeRoot, isPathInsideRoots } from "@/lib/bim/openbimforge-paths"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

function getRuntimeRoot(): string {
    return path.resolve(
        process.env.OPENBIMFORGE_RUNTIME_ROOT ||
            path.join(getOpenBimForgeRoot(), "forge_runtime"),
    )
}

function getAllowedRoots(): string[] {
    const runtimeRoot = getRuntimeRoot()
    return [
        path.join(runtimeRoot, "layout_outputs"),
        path.join(runtimeRoot, "logs"),
    ].map((root) => path.resolve(root))
}

function getContentType(filePath: string): string {
    const ext = path.extname(filePath).toLowerCase()
    switch (ext) {
        case ".png":
            return "image/png"
        case ".jpg":
        case ".jpeg":
            return "image/jpeg"
        case ".webp":
            return "image/webp"
        case ".stl":
            return "model/stl"
        case ".log":
        case ".txt":
            return "text/plain; charset=utf-8"
        case ".json":
            return "application/json; charset=utf-8"
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

    if (!isPathInsideRoots(targetPath, getAllowedRoots())) {
        return NextResponse.json(
            { ok: false, error: "Layout artifact path is outside allowed runtime directories." },
            { status: 403 },
        )
    }

    try {
        const fileBuffer = await fs.readFile(targetPath)
        const headers = new Headers({
            "content-type": getContentType(targetPath),
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
                        : "Failed to read layout artifact.",
            },
            { status: 404 },
        )
    }
}
