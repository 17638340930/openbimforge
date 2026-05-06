import { type DBSchema, type IDBPDatabase, openDB } from "idb"
import { nanoid } from "nanoid"

const DB_NAME = "openbimforge"
const DB_VERSION = 1
const STORE_NAME = "sessions"
const MIGRATION_FLAG = "openbimforge-migrated-to-idb"
const MAX_SESSIONS = 50

export interface ChatSession {
    id: string
    title: string
    createdAt: number
    updatedAt: number
    messages: StoredMessage[]
    bimResults?: Array<{ path: string; timestamp: number }>
}

export interface StoredMessage {
    id: string
    role: "user" | "assistant" | "system"
    parts: Array<{ type: string; [key: string]: unknown }>
}

export interface SessionMetadata {
    id: string
    title: string
    createdAt: number
    updatedAt: number
    messageCount: number
    hasBimResults: boolean
}

interface ChatSessionDB extends DBSchema {
    sessions: {
        key: string
        value: ChatSession
        indexes: { "by-updated": number }
    }
}

let dbPromise: Promise<IDBPDatabase<ChatSessionDB>> | null = null

async function getDB(): Promise<IDBPDatabase<ChatSessionDB>> {
    if (!dbPromise) {
        dbPromise = openDB<ChatSessionDB>(DB_NAME, DB_VERSION, {
            upgrade(db, oldVersion) {
                if (oldVersion < 1) {
                    const store = db.createObjectStore(STORE_NAME, {
                        keyPath: "id",
                    })
                    store.createIndex("by-updated", "updatedAt")
                }
            },
        })
    }
    return dbPromise
}

export function isIndexedDBAvailable(): boolean {
    if (typeof window === "undefined") return false
    try {
        return "indexedDB" in window && window.indexedDB !== null
    } catch {
        return false
    }
}

export async function getAllSessionMetadata(): Promise<SessionMetadata[]> {
    if (!isIndexedDBAvailable()) return []
    try {
        const db = await getDB()
        const tx = db.transaction(STORE_NAME, "readonly")
        const index = tx.store.index("by-updated")
        const metadata: SessionMetadata[] = []

        let cursor = await index.openCursor(null, "prev")
        while (cursor) {
            const s = cursor.value
            metadata.push({
                id: s.id,
                title: s.title,
                createdAt: s.createdAt,
                updatedAt: s.updatedAt,
                messageCount: s.messages.length,
                hasBimResults: !!(s.bimResults && s.bimResults.length > 0),
            })
            cursor = await cursor.continue()
        }
        return metadata
    } catch (error) {
        console.error("Failed to get session metadata:", error)
        return []
    }
}

export async function getSession(id: string): Promise<ChatSession | null> {
    if (!isIndexedDBAvailable()) return null
    try {
        const db = await getDB()
        return (await db.get(STORE_NAME, id)) || null
    } catch (error) {
        console.error("Failed to get session:", error)
        return null
    }
}

export async function saveSession(session: ChatSession): Promise<boolean> {
    if (!isIndexedDBAvailable()) return false
    try {
        const db = await getDB()
        await db.put(STORE_NAME, session)
        return true
    } catch (error) {
        if (
            error instanceof DOMException &&
            error.name === "QuotaExceededError"
        ) {
            console.warn("Storage quota exceeded, deleting oldest session...")
            await deleteOldestSession()
            try {
                const db = await getDB()
                await db.put(STORE_NAME, session)
                return true
            } catch (retryError) {
                console.error(
                    "Failed to save session after cleanup:",
                    retryError,
                )
                return false
            }
        } else {
            console.error("Failed to save session:", error)
            return false
        }
    }
}

export async function deleteSession(id: string): Promise<void> {
    if (!isIndexedDBAvailable()) return
    try {
        const db = await getDB()
        await db.delete(STORE_NAME, id)
    } catch (error) {
        console.error("Failed to delete session:", error)
    }
}

export async function getSessionCount(): Promise<number> {
    if (!isIndexedDBAvailable()) return 0
    try {
        const db = await getDB()
        return await db.count(STORE_NAME)
    } catch (error) {
        console.error("Failed to get session count:", error)
        return 0
    }
}

export async function deleteOldestSession(): Promise<void> {
    if (!isIndexedDBAvailable()) return
    try {
        const db = await getDB()
        const tx = db.transaction(STORE_NAME, "readwrite")
        const index = tx.store.index("by-updated")
        const cursor = await index.openCursor()
        if (cursor) {
            await cursor.delete()
        }
        await tx.done
    } catch (error) {
        console.error("Failed to delete oldest session:", error)
    }
}

export async function enforceSessionLimit(): Promise<void> {
    const count = await getSessionCount()
    if (count > MAX_SESSIONS) {
        const toDelete = count - MAX_SESSIONS
        for (let i = 0; i < toDelete; i++) {
            await deleteOldestSession()
        }
    }
}

export function createEmptySession(): ChatSession {
    return {
        id: nanoid(),
        title: "新对话",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
    }
}

const MAX_TITLE_LENGTH = 100

export function extractTitle(messages: StoredMessage[]): string {
    const firstUserMessage = messages.find((m) => m.role === "user")
    if (!firstUserMessage) return "新对话"

    const textPart = firstUserMessage.parts.find((p) => p.type === "text")
    if (!textPart || typeof textPart.text !== "string") return "新对话"

    const text = textPart.text.trim()
    if (!text) return "新对话"

    if (text.length > MAX_TITLE_LENGTH) {
        return text.slice(0, MAX_TITLE_LENGTH).trim() + "..."
    }
    return text
}

export function sanitizeMessage(message: unknown): StoredMessage | null {
    if (!message || typeof message !== "object") return null

    const msg = message as Record<string, unknown>
    if (!msg.id || !msg.role) return null

    const role = msg.role as string
    if (!["user", "assistant", "system"].includes(role)) return null

    let parts: Array<{ type: string; [key: string]: unknown }> = []
    if (Array.isArray(msg.parts)) {
        parts = msg.parts.map((part: unknown) => {
            if (!part || typeof part !== "object") return { type: "unknown" }
            const p = part as Record<string, unknown>
            const { isStreaming, streamingState, ...cleanPart } = p
            return cleanPart as { type: string; [key: string]: unknown }
        })
    }

    return {
        id: msg.id as string,
        role: role as "user" | "assistant" | "system",
        parts,
    }
}

export function sanitizeMessages(messages: unknown[]): StoredMessage[] {
    return messages
        .map(sanitizeMessage)
        .filter((m): m is StoredMessage => m !== null)
}

export async function migrateFromLocalStorage(): Promise<string | null> {
    if (typeof window === "undefined") return null
    if (!isIndexedDBAvailable()) return null

    if (localStorage.getItem(MIGRATION_FLAG)) return null

    try {
        const savedMessages = localStorage.getItem("openbimforge-messages")

        let newSessionId: string | null = null
        let migrationSucceeded = false

        if (savedMessages) {
            const messages = JSON.parse(savedMessages)
            if (Array.isArray(messages) && messages.length > 0) {
                const sanitized = sanitizeMessages(messages)
                const session: ChatSession = {
                    ...createEmptySession(),
                    messages: sanitized,
                    title: extractTitle(sanitized),
                }
                const saved = await saveSession(session)
                if (saved) {
                    const verified = await getSession(session.id)
                    if (verified) {
                        newSessionId = session.id
                        migrationSucceeded = true
                    }
                }
            } else {
                migrationSucceeded = true
            }
        } else {
            migrationSucceeded = true
        }

        if (migrationSucceeded) {
            localStorage.setItem(MIGRATION_FLAG, "true")
            localStorage.removeItem("openbimforge-messages")
        }

        return newSessionId
    } catch (error) {
        console.error("Migration failed:", error)
        return null
    }
}
