"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { getApiEndpoint } from "@/lib/base-path"

const DEFAULT_MAX_BYTES = 8 * 1024 * 1024
const SUPPORTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp"])

export interface ImageAttachment {
    file: File
    previewUrl: string
}

export interface LayoutUploadResult {
    ok: boolean
    result?: unknown
    error?: string
}

export function useImageUpload() {
    const [attachment, setAttachment] = useState<ImageAttachment | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [isUploading, setIsUploading] = useState(false)
    const previewRef = useRef<string | null>(null)

    const revokePreview = useCallback(() => {
        if (previewRef.current) {
            URL.revokeObjectURL(previewRef.current)
            previewRef.current = null
        }
    }, [])

    const clearAttachment = useCallback(() => {
        revokePreview()
        setAttachment(null)
        setError(null)
    }, [revokePreview])

    useEffect(() => clearAttachment, [clearAttachment])

    const selectFile = useCallback(
        (file: File | null) => {
            setError(null)
            if (!file) return
            if (!SUPPORTED_TYPES.has(file.type)) {
                setError("仅支持 PNG、JPEG 或 WebP 图片。")
                return
            }
            if (file.size > DEFAULT_MAX_BYTES) {
                setError("图片不能超过 8MB，请压缩后重试。")
                return
            }
            revokePreview()
            const previewUrl = URL.createObjectURL(file)
            previewRef.current = previewUrl
            setAttachment({ file, previewUrl })
        },
        [revokePreview],
    )

    const runLayout = useCallback(async (sessionId?: string): Promise<LayoutUploadResult> => {
        if (!attachment) {
            return { ok: false, error: "请先选择一张图片。" }
        }

        setIsUploading(true)
        setError(null)
        try {
            const formData = new FormData()
            formData.set("image", attachment.file)
            if (sessionId) {
                formData.set("sessionId", sessionId)
            }
            const response = await fetch(getApiEndpoint("/api/bim/forge-architect-visionary"), {
                method: "POST",
                body: formData,
            })
            const data = await response.json()
            if (!response.ok || !data?.ok) {
                const message = data?.error || data?.result?.error || "Layout Agent 处理失败。"
                setError(message)
                return { ok: false, error: message, result: data?.result }
            }
            return { ok: true, result: data.result }
        } catch (err) {
            const message = err instanceof Error ? err.message : "Layout Agent 请求失败。"
            setError(message)
            return { ok: false, error: message }
        } finally {
            setIsUploading(false)
        }
    }, [attachment])

    return {
        attachment,
        clearAttachment,
        error,
        isUploading,
        runLayout,
        selectFile,
        setError,
    }
}
