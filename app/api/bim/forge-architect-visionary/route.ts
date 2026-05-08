import { execFile } from "node:child_process"
import { randomUUID } from "node:crypto"
import { promises as fs } from "node:fs"
import path from "node:path"
import { promisify } from "node:util"
import type { ForgeVisionFormResult } from "@/lib/bim/visionary-types"
import { getOpenBimForgeRoot } from "@/lib/bim/openbimforge-paths"
import { NextResponse } from "next/server"

export const runtime = "nodejs"

const execFileAsync = promisify(execFile)
const MAX_IMAGE_BYTES = 12 * 1024 * 1024
const SUPPORTED_IMAGE_TYPES = new Set([
    "image/png",
    "image/jpeg",
    "image/webp",
])

type VisionaryRunBody = {
    imageDataUrl?: string
    fileName?: string
    sessionId?: string
}

type VisionaryDebugEvent = {
    at: string
    detail?: Record<string, unknown>
    message: string
}

function createDebugLog() {
    const events: VisionaryDebugEvent[] = []
    const startedAt = Date.now()
    return {
        events,
        push(message: string, detail?: Record<string, unknown>) {
            events.push({
                at: new Date().toISOString(),
                detail,
                message,
            })
        },
        snapshot() {
            return {
                durationMs: Date.now() - startedAt,
                events,
            }
        },
    }
}

function getRuntimeRoot(): string {
    return path.resolve(
        process.env.OPENBIMFORGE_RUNTIME_ROOT ||
            path.join(getOpenBimForgeRoot(), "forge_runtime"),
    )
}

function getBridgePythonCommand(): string {
    return (
        process.env.OPENBIMFORGE_LAYOUT_BRIDGE_PYTHON ||
        process.env.PYTHON_COMMAND ||
        "python"
    )
}

function sanitizeFileName(fileName: string): string {
    const ext = path.extname(fileName).toLowerCase()
    const safeExt = [".png", ".jpg", ".jpeg", ".webp"].includes(ext) ? ext : ".png"
    return `input${safeExt}`
}

function parseDataUrl(dataUrl: string): { mimeType: string; buffer: Buffer } {
    const match = dataUrl.match(/^data:([^;]+);base64,(.+)$/)
    if (!match) {
        throw new Error("Invalid image data URL.")
    }
    const mimeType = match[1]
    if (!SUPPORTED_IMAGE_TYPES.has(mimeType)) {
        throw new Error("Unsupported image type. Please upload PNG, JPEG, or WebP.")
    }
    const buffer = Buffer.from(match[2], "base64")
    if (buffer.byteLength > MAX_IMAGE_BYTES) {
        throw new Error("Image is too large. Please upload an image smaller than 12MB.")
    }
    return { mimeType, buffer }
}

async function readImageFromRequest(req: Request): Promise<{
    buffer: Buffer
    fileName: string
    sessionId?: string
    source: "multipart" | "json-data-url"
}> {
    const contentType = req.headers.get("content-type") || ""

    if (contentType.includes("multipart/form-data")) {
        const formData = await req.formData()
        const file = formData.get("image")
        const sessionId = formData.get("sessionId")
        if (!(file instanceof File)) {
            throw new Error("Missing image file field.")
        }
        if (!SUPPORTED_IMAGE_TYPES.has(file.type)) {
            throw new Error("Unsupported image type. Please upload PNG, JPEG, or WebP.")
        }
        if (file.size > MAX_IMAGE_BYTES) {
            throw new Error("Image is too large. Please upload an image smaller than 12MB.")
        }
        return {
            buffer: Buffer.from(await file.arrayBuffer()),
            fileName: file.name,
            sessionId: typeof sessionId === "string" ? sessionId : undefined,
            source: "multipart",
        }
    }

    const body = (await req.json()) as VisionaryRunBody
    if (!body.imageDataUrl) {
        throw new Error("Missing imageDataUrl.")
    }
    const { buffer, mimeType } = parseDataUrl(body.imageDataUrl)
    const ext = mimeType === "image/jpeg" ? ".jpg" : mimeType === "image/webp" ? ".webp" : ".png"
    return {
        buffer,
        fileName: body.fileName || `input${ext}`,
        sessionId: body.sessionId,
        source: "json-data-url",
    }
}

async function writeInputImage(params: {
    buffer: Buffer
    fileName: string
    sessionId: string
}): Promise<string> {
    const inputDir = path.join(getRuntimeRoot(), "nexus_visionary_inputs", params.sessionId, "upload")
    await fs.mkdir(inputDir, { recursive: true })
    const inputPath = path.join(inputDir, sanitizeFileName(params.fileName))
    await fs.writeFile(inputPath, params.buffer)
    return inputPath
}

async function runVisionaryAgent(
    imagePath: string,
    sessionId: string,
    debug: ReturnType<typeof createDebugLog>,
) {
    const projectRoot = getOpenBimForgeRoot()
    const code = [
        "import json, sys",
        `sys.path.insert(0, ${JSON.stringify(projectRoot)})`,
        "from forge_core.layout_agent import run_layout",
        `print(json.dumps(run_layout(${JSON.stringify(imagePath)}, ${JSON.stringify(sessionId)}), ensure_ascii=False))`,
    ].join("\n")

    const timeout = Number(process.env.OPENBIMFORGE_LAYOUT_API_TIMEOUT_MS || 900_000)
    debug.push("Initializing ForgeVision-Form orchestration bridge.", {
        bridgePython: getBridgePythonCommand(),
        projectRoot,
        timeout,
    })
    const { stdout, stderr } = await execFileAsync(
        getBridgePythonCommand(),
        ["-c", code],
        {
            cwd: projectRoot,
            env: {
                ...process.env,
                OPENBIMFORGE_ROOT: projectRoot,
                OPENBIMFORGE_RUNTIME_ROOT: getRuntimeRoot(),
            },
            maxBuffer: 16 * 1024 * 1024,
            timeout,
        },
    )

    const trimmed = stdout.trim()
    debug.push("ForgeVision-Form synthesis finished.", {
        stderrLength: stderr.length,
        stdoutLength: stdout.length,
    })
    if (!trimmed) {
        throw new Error(stderr.trim() || "ForgeVision-Form returned empty output.")
    }
    try {
        return JSON.parse(trimmed.split(/\r?\n/).at(-1) || trimmed)
    } catch (error) {
        throw new Error(
            `ForgeVision-Form returned invalid JSON. ${error instanceof Error ? error.message : ""}`,
        )
    }
}

export async function POST(req: Request) {
    const debug = createDebugLog()
    try {
        debug.push("Received ForgeVision-Form orchestration request.", {
            contentType: req.headers.get("content-type") || "",
        })
        const upload = await readImageFromRequest(req)
        debug.push("Parsed input topology asset.", {
            fileName: upload.fileName,
            imageBytes: upload.buffer.byteLength,
            source: upload.source,
        })
        const sessionId = upload.sessionId || `visionary-${randomUUID().slice(0, 12)}`
        const imagePath = await writeInputImage({
            buffer: upload.buffer,
            fileName: upload.fileName,
            sessionId,
        })
        console.log(
            `[ForgeVision-Form] start | session=${sessionId} | file=${upload.fileName} | bytes=${upload.buffer.byteLength} | path=${imagePath}`,
        )
        debug.push("Staged visual topology reference.", {
            imagePath,
            sessionId,
        })
        const result = await runVisionaryAgent(imagePath, sessionId, debug)
        debug.push("ForgeVision-Form returned result.", {
            ok: Boolean(result?.ok),
            status: result?.status,
            logPath: result?.log_path,
        })

        const stlPaths = Array.isArray(result?.stl_paths) ? result.stl_paths : []
        const previewPaths = Array.isArray(result?.preview_paths) ? result.preview_paths : []
        const cadVectorPaths = Array.isArray(result?.cad_vector_paths) ? result.cad_vector_paths : []
        const hasStls = stlPaths.length > 0
        const hasPreviews = previewPaths.length > 0
        const referenceOnly = result?.status === "completed_reference_only" || !hasStls
        console.log(
            `[ForgeVision-Form] result | session=${sessionId} | ok=${Boolean(result?.ok)} | status=${result?.status || "unknown"} | stl=${stlPaths.length} | preview=${previewPaths.length} | cadVector=${cadVectorPaths.length} | log=${result?.log_path || "missing"}`,
        )

        let inputKind: ForgeVisionFormResult["forgeVisionConstraints"]["inputKind"] = "unknown"
        if (hasStls) {
            inputKind = "massing_reference"
        } else if (hasPreviews) {
            inputKind = "concept_sketch"
        }

        const forgeVisionConstraints: ForgeVisionFormResult["forgeVisionConstraints"] = {
            inputKind,
            isReferenceOnly: true,
            massingReferencePath: stlPaths[0],
            visualPreviewPath: previewPaths[0],
            cadVectorPath: cadVectorPaths[0],
            notes: [
                "[REFERENCE_ONLY] ForgeVision-Form result is only a massing/form reference, not a final BIM deliverable.",
                referenceOnly
                    ? "[CRITICAL] No valid STL massing was extracted. Use the uploaded image only as a loose visual reference and rely on the user text for BIM semantics."
                    : "Use the STL only as a geometric envelope reference; rebuild semantic BIM elements with Vectorworks-native walls, slabs, openings, and storeys.",
                "Do not invent engineering facts that are not provided by the user, including exact area, absolute height, storey count, structure, or fire-code metrics.",
            ],
        }

        const forgeVisionForm: ForgeVisionFormResult = {
            source: "forgevision-form",
            sessionId,
            status: result?.status || (result?.ok ? "completed" : "failed"),
            previewPaths,
            stlPaths,
            cadVectorPaths,
            logPath: result?.log_path,
            forgeVisionConstraints,
            constraints: forgeVisionConstraints,
        }

        return NextResponse.json({
            ok: Boolean(result?.ok),
            debug: debug.snapshot(),
            source: "forgevision-form",
            result,
            forgeVisionForm,
            normalizedVisionary: forgeVisionForm,
        })
    } catch (error) {
        console.error(
            `[ForgeVision-Form] failed | error=${error instanceof Error ? error.message : String(error)}`,
        )
        debug.push("ForgeVision-Form orchestration failed.", {
            error: error instanceof Error ? error.message : String(error),
        })
        return NextResponse.json(
            {
                ok: false,
                debug: debug.snapshot(),
                source: "forgevision-form",
                error:
                    error instanceof Error
                        ? error.message
                        : "ForgeVision-Form orchestration failure.",
            },
            { status: 400 },
        )
    }
}
