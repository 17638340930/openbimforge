"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
    type ChatSession,
    createEmptySession,
    deleteSession as deleteSessionFromDB,
    enforceSessionLimit,
    extractTitle,
    getAllSessionMetadata,
    getSession,
    isIndexedDBAvailable,
    migrateFromLocalStorage,
    type SessionMetadata,
    type StoredMessage,
    saveSession,
} from "@/lib/session-storage"

export interface SessionData {
    messages: StoredMessage[]
    bimResults?: Array<{ path: string; timestamp: number }>
}

export interface UseConversationManagerReturn {
    sessions: SessionMetadata[]
    currentSessionId: string | null
    currentSession: ChatSession | null
    isLoading: boolean
    isAvailable: boolean
    switchSession: (id: string) => Promise<SessionData | null>
    deleteSession: (id: string) => Promise<{ wasCurrentSession: boolean }>
    saveCurrentSession: (
        data: SessionData,
        forSessionId?: string | null,
    ) => Promise<void>
    refreshSessions: () => Promise<void>
    clearCurrentSession: () => void
}

export function useConversationManager(): UseConversationManagerReturn {
    const [sessions, setSessions] = useState<SessionMetadata[]>([])
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(
        null,
    )
    const [currentSession, setCurrentSession] = useState<ChatSession | null>(
        null,
    )
    const [isLoading, setIsLoading] = useState(true)
    const [isAvailable, setIsAvailable] = useState(false)

    const isInitializedRef = useRef(false)

    const refreshSessions = useCallback(async () => {
        if (!isIndexedDBAvailable()) return
        try {
            const metadata = await getAllSessionMetadata()
            setSessions(metadata)
        } catch (error) {
            console.error("Failed to refresh sessions:", error)
        }
    }, [])

    useEffect(() => {
        if (isInitializedRef.current) return
        isInitializedRef.current = true

        async function init() {
            setIsLoading(true)

            if (!isIndexedDBAvailable()) {
                setIsAvailable(false)
                setIsLoading(false)
                return
            }

            setIsAvailable(true)

            try {
                await migrateFromLocalStorage()
                const metadata = await getAllSessionMetadata()
                setSessions(metadata)
            } catch (error) {
                console.error("Failed to initialize conversation manager:", error)
            } finally {
                setIsLoading(false)
            }
        }

        init()
    }, [])

    useEffect(() => {
        const handleFocus = () => {
            refreshSessions()
        }
        window.addEventListener("focus", handleFocus)
        return () => window.removeEventListener("focus", handleFocus)
    }, [refreshSessions])

    const switchSession = useCallback(
        async (id: string): Promise<SessionData | null> => {
            if (id === currentSessionId && currentSession) {
                return {
                    messages: currentSession.messages,
                    bimResults: currentSession.bimResults,
                }
            }

            if (currentSession && currentSession.messages.length > 0) {
                await saveSession(currentSession)
            }

            const session = await getSession(id)
            if (!session) {
                console.error("Session not found:", id)
                return null
            }

            setCurrentSession(session)
            setCurrentSessionId(session.id)

            return {
                messages: session.messages,
                bimResults: session.bimResults,
            }
        },
        [currentSessionId, currentSession],
    )

    const deleteSession = useCallback(
        async (id: string): Promise<{ wasCurrentSession: boolean }> => {
            const wasCurrentSession = id === currentSessionId
            await deleteSessionFromDB(id)

            if (wasCurrentSession) {
                setCurrentSession(null)
                setCurrentSessionId(null)
            }

            await refreshSessions()

            return { wasCurrentSession }
        },
        [currentSessionId, refreshSessions],
    )

    const saveCurrentSession = useCallback(
        async (
            data: SessionData,
            forSessionId?: string | null,
        ): Promise<void> => {
            if (
                forSessionId !== undefined &&
                forSessionId !== currentSessionId
            ) {
                return
            }

            if (!currentSession) {
                const newSession: ChatSession = {
                    ...createEmptySession(),
                    messages: data.messages,
                    bimResults: data.bimResults,
                    title: extractTitle(data.messages),
                }
                await saveSession(newSession)
                await enforceSessionLimit()
                setCurrentSession(newSession)
                setCurrentSessionId(newSession.id)
                await refreshSessions()
                return
            }

            const updatedSession: ChatSession = {
                ...currentSession,
                messages: data.messages,
                bimResults: data.bimResults ?? currentSession.bimResults,
                updatedAt: Date.now(),
                title:
                    currentSession.title === "新对话" &&
                    data.messages.length > 0
                        ? extractTitle(data.messages)
                        : currentSession.title,
            }

            await saveSession(updatedSession)
            setCurrentSession(updatedSession)

            setSessions((prev) =>
                prev.map((s) =>
                    s.id === updatedSession.id
                        ? {
                              ...s,
                              title: updatedSession.title,
                              updatedAt: updatedSession.updatedAt,
                              messageCount: updatedSession.messages.length,
                              hasBimResults:
                                  !!updatedSession.bimResults &&
                                  updatedSession.bimResults.length > 0,
                          }
                        : s,
                ),
            )
        },
        [currentSession, currentSessionId, refreshSessions],
    )

    const clearCurrentSession = useCallback(() => {
        setCurrentSession(null)
        setCurrentSessionId(null)
    }, [])

    return {
        sessions,
        currentSessionId,
        currentSession,
        isLoading,
        isAvailable,
        switchSession,
        deleteSession,
        saveCurrentSession,
        refreshSessions,
        clearCurrentSession,
    }
}
