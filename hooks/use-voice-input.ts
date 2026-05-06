"use client"

import { useCallback, useEffect, useRef, useState } from "react"

type VoiceInputStatus = "idle" | "listening" | "unsupported" | "error"

interface SpeechRecognitionLike {
    continuous: boolean
    interimResults: boolean
    lang: string
    onend: (() => void) | null
    onerror: ((event: { error?: string }) => void) | null
    onresult: ((event: SpeechRecognitionEventLike) => void) | null
    start: () => void
    stop: () => void
}

interface SpeechRecognitionEventLike {
    resultIndex: number
    results: ArrayLike<{
        isFinal: boolean
        0: { transcript: string }
    }>
}

interface SpeechWindow extends Window {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
}

interface UseVoiceInputOptions {
    language?: string
    onFinalTranscript: (text: string) => void
}

export function useVoiceInput({
    language = "zh-CN",
    onFinalTranscript,
}: UseVoiceInputOptions) {
    const [status, setStatus] = useState<VoiceInputStatus>("idle")
    const [interimTranscript, setInterimTranscript] = useState("")
    const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
    const finalTranscriptRef = useRef(onFinalTranscript)

    useEffect(() => {
        finalTranscriptRef.current = onFinalTranscript
    }, [onFinalTranscript])

    useEffect(() => {
        if (typeof window === "undefined") return
        const speechWindow = window as SpeechWindow
        const SpeechRecognition =
            speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition
        if (!SpeechRecognition) {
            setStatus("unsupported")
            return
        }

        return () => {
            recognitionRef.current?.stop()
            recognitionRef.current = null
        }
    }, [])

    const startListening = useCallback(() => {
        if (typeof window === "undefined") return false
        const speechWindow = window as SpeechWindow
        const SpeechRecognition =
            speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition
        if (!SpeechRecognition) {
            setStatus("unsupported")
            return false
        }

        const recognition = new SpeechRecognition()
        recognition.continuous = false
        recognition.interimResults = true
        recognition.lang = language
        recognition.onresult = (event) => {
            let finalText = ""
            let interimText = ""
            for (let index = event.resultIndex; index < event.results.length; index += 1) {
                const result = event.results[index]
                const transcript = result[0]?.transcript?.trim()
                if (!transcript) continue
                if (result.isFinal) {
                    finalText += `${transcript} `
                } else {
                    interimText += `${transcript} `
                }
            }
            if (finalText.trim()) {
                finalTranscriptRef.current(finalText.trim())
            }
            setInterimTranscript(interimText.trim())
        }
        recognition.onerror = () => {
            setStatus("error")
            setInterimTranscript("")
        }
        recognition.onend = () => {
            setStatus((current) => (current === "unsupported" ? current : "idle"))
            setInterimTranscript("")
        }

        recognitionRef.current = recognition
        setInterimTranscript("")
        setStatus("listening")
        recognition.start()
        return true
    }, [language])

    const stopListening = useCallback(() => {
        recognitionRef.current?.stop()
        setStatus((current) => (current === "unsupported" ? current : "idle"))
        setInterimTranscript("")
    }, [])

    return {
        interimTranscript,
        isListening: status === "listening",
        isSupported: status !== "unsupported",
        startListening,
        status,
        stopListening,
    }
}
