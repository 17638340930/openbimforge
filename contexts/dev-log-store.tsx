"use client"

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useState,
    type ReactNode,
} from "react"

/* ---------- Types ---------- */

export interface DevLogEntry {
    id: string
    timestamp: number
    type: "stage-event" | "progress" | "error" | "result" | "raw"
    stageId?: string
    stageLabel?: string
    status?: string
    duration_ms?: number
    detail?: string
    payload?: Record<string, unknown>
    logs?: string[]
}

export interface DevLogSnapshot {
    sessionId: string
    title: string
    status: "running" | "success" | "failed"
    mode?: string
    agent?: string
    entries: DevLogEntry[]
    rawPayloads: Array<{ timestamp: number; data: Record<string, unknown> }>
    startedAt: number
    finishedAt?: number
}

/* ---------- Context ---------- */

interface DevLogStore {
    snapshots: DevLogSnapshot[]
    currentSnapshot: DevLogSnapshot | null
    pushExecutionLog: (payload: Record<string, unknown>) => void
    clearLogs: () => void
    getSnapshotById: (id: string) => DevLogSnapshot | undefined
}

const DevLogContext = createContext<DevLogStore | null>(null)

const STORAGE_KEY = "openbimforge-dev-logs"
const MAX_SNAPSHOTS = 20

/* ---------- Provider ---------- */

export function DevLogProvider({ children }: { children: ReactNode }) {
    const [snapshots, setSnapshots] = useState<DevLogSnapshot[]>(() => {
        if (typeof window === "undefined") return []
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY)
            return raw ? JSON.parse(raw) : []
        } catch {
            return []
        }
    })

    const currentSnapshot = snapshots[snapshots.length - 1] || null

    // Persist to sessionStorage
    useEffect(() => {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshots))
        } catch {}
    }, [snapshots])

    const pushExecutionLog = useCallback(
        (payload: Record<string, unknown>) => {
            const now = Date.now()
            const stages = (payload.stages as any[]) || []
            const logs = (payload.logs as string[]) || []
            const status = (payload.status as string) || "running"
            const title = (payload.title as string) || "Nexus Execution"
            const mode = payload.mode as string | undefined
            const agent = payload.agent as string | undefined

            // Convert stages to dev log entries
            const entries: DevLogEntry[] = stages.map((stage, i) => ({
                id: `${stage.id || i}-${now}`,
                timestamp: now,
                type: "stage-event" as const,
                stageId: stage.id,
                stageLabel: stage.label || stage.id,
                status: stage.status,
                duration_ms: stage.duration_ms,
                detail: stage.detail,
            }))

            // Add log lines as entries
            if (logs.length > 0) {
                entries.push({
                    id: `logs-${now}`,
                    timestamp: now,
                    type: "raw",
                    logs: logs,
                    detail: `${logs.length} log lines`,
                })
            }

            const snapshotId = `snap-${now}`

            setSnapshots((prev) => {
                // Check if we should update the last snapshot (same session, still running)
                const last = prev[prev.length - 1]
                if (
                    last &&
                    last.status === "running" &&
                    last.title === title
                ) {
                    const updated: DevLogSnapshot = {
                        ...last,
                        status: status as "running" | "success" | "failed",
                        entries,
                        rawPayloads: [
                            ...last.rawPayloads,
                            { timestamp: now, data: payload },
                        ],
                        ...(status !== "running"
                            ? { finishedAt: now }
                            : {}),
                    }
                    return [...prev.slice(0, -1), updated]
                }

                // New snapshot
                const newSnapshot: DevLogSnapshot = {
                    sessionId: snapshotId,
                    title,
                    status: status as "running" | "success" | "failed",
                    mode,
                    agent,
                    entries,
                    rawPayloads: [{ timestamp: now, data: payload }],
                    startedAt: now,
                    ...(status !== "running" ? { finishedAt: now } : {}),
                }
                const next = [...prev, newSnapshot]
                return next.length > MAX_SNAPSHOTS
                    ? next.slice(-MAX_SNAPSHOTS)
                    : next
            })
        },
        [],
    )

    const clearLogs = useCallback(() => {
        setSnapshots([])
        try {
            sessionStorage.removeItem(STORAGE_KEY)
        } catch {}
    }, [])

    const getSnapshotById = useCallback(
        (id: string) => snapshots.find((s) => s.sessionId === id),
        [snapshots],
    )

    return (
        <DevLogContext.Provider
            value={{
                snapshots,
                currentSnapshot,
                pushExecutionLog,
                clearLogs,
                getSnapshotById,
            }}
        >
            {children}
        </DevLogContext.Provider>
    )
}

export function useDevLogStore(): DevLogStore {
    const ctx = useContext(DevLogContext)
    if (!ctx) throw new Error("useDevLogStore must be inside DevLogProvider")
    return ctx
}
