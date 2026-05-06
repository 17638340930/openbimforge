"use client"

import { MessageSquare, Search, Trash2, X } from "lucide-react"
import { useState } from "react"
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import type { SessionMetadata } from "@/lib/session-storage"

interface ChatHistoryPanelProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    sessions: SessionMetadata[]
    onSelectSession: (id: string) => void
    onDeleteSession: (id: string) => void
}

function formatSessionDate(timestamp: number): string {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / (1000 * 60))
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

    if (diffMins < 1) return "刚刚"
    if (diffMins < 60) return `${diffMins} 分钟前`
    if (diffHours < 24) return `${diffHours} 小时前`
    if (diffDays < 7) return `${diffDays} 天前`

    return date.toLocaleDateString("zh-CN", {
        month: "short",
        day: "numeric",
    })
}

export function ChatHistoryPanel({
    open,
    onOpenChange,
    sessions,
    onSelectSession,
    onDeleteSession,
}: ChatHistoryPanelProps) {
    const [searchQuery, setSearchQuery] = useState("")
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
    const [sessionToDelete, setSessionToDelete] = useState<string | null>(null)

    const filteredSessions = sessions.filter((session) =>
        session.title.toLowerCase().includes(searchQuery.toLowerCase()),
    )

    return (
        <>
            <Dialog open={open} onOpenChange={onOpenChange}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>对话历史</DialogTitle>
                        <DialogDescription>选择一个对话继续，或搜索历史记录。</DialogDescription>
                    </DialogHeader>

                    <div className="relative mb-3">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="搜索对话..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-border/60 bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all"
                        />
                        {searchQuery && (
                            <button
                                type="button"
                                onClick={() => setSearchQuery("")}
                                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-muted transition-colors"
                            >
                                <X className="w-3 h-3 text-muted-foreground" />
                            </button>
                        )}
                    </div>

                    <div className="max-h-[400px] overflow-y-auto space-y-2 pr-1">
                        {filteredSessions.length === 0 ? (
                            <p className="text-sm text-muted-foreground text-center py-8">
                                {searchQuery ? "未找到匹配的对话" : "暂无对话历史"}
                            </p>
                        ) : (
                            filteredSessions.map((session) => (
                                <div
                                    key={session.id}
                                    role="button"
                                    tabIndex={0}
                                    className="group w-full flex items-center gap-3 p-3 rounded-xl border border-border/60 bg-card hover:bg-accent/50 hover:border-primary/30 transition-all duration-200 cursor-pointer text-left"
                                    onClick={() => {
                                        onSelectSession(session.id)
                                        onOpenChange(false)
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" || e.key === " ") {
                                            e.preventDefault()
                                            onSelectSession(session.id)
                                            onOpenChange(false)
                                        }
                                    }}
                                >
                                    <div className="w-10 h-10 shrink-0 rounded-lg bg-primary/10 flex items-center justify-center">
                                        <MessageSquare className="w-4 h-4 text-primary" />
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <div className="text-sm font-medium truncate">
                                            {session.title}
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            {formatSessionDate(session.updatedAt)}
                                            {session.messageCount > 0 && (
                                                <span className="ml-2">
                                                    {session.messageCount} 条消息
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            setSessionToDelete(session.id)
                                            setDeleteDialogOpen(true)
                                        }}
                                        className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                                        title="删除"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            ))
                        )}
                    </div>
                </DialogContent>
            </Dialog>

            <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                <AlertDialogContent className="max-w-sm">
                    <AlertDialogHeader>
                        <AlertDialogTitle>删除此对话？</AlertDialogTitle>
                        <AlertDialogDescription>
                            此操作将永久删除该对话记录，无法撤销。
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>取消</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={() => {
                                if (sessionToDelete) {
                                    onDeleteSession(sessionToDelete)
                                }
                                setDeleteDialogOpen(false)
                                setSessionToDelete(null)
                            }}
                            className="border border-red-300 bg-red-50 text-red-700 hover:bg-red-100 hover:border-red-400"
                        >
                            删除
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}
