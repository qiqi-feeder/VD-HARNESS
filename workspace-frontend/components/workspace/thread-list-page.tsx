"use client";

import Link from "next/link";
import { Pencil, Search, Share2, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { useDeleteThread, useRenameThread, useThreads } from "@/core/threads/hooks";
import { formatRelativeTime } from "@/lib/utils";

export function ThreadListPage() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [workingThreadId, setWorkingThreadId] = useState<string | null>(null);
  const { data: threads = [], isLoading } = useThreads(search);
  const renameThread = useRenameThread();
  const deleteThread = useDeleteThread();

  async function handleRename(threadId: string, currentTitle: string) {
    const nextTitle = window.prompt("输入新的会话标题", currentTitle)?.trim();
    if (!nextTitle || nextTitle === currentTitle) return;
    setWorkingThreadId(threadId);
    try {
      await renameThread.mutateAsync({ threadId, title: nextTitle });
    } finally {
      setWorkingThreadId(null);
    }
  }

  async function handleDelete(threadId: string) {
    setWorkingThreadId(threadId);
    try {
      await deleteThread.mutateAsync(threadId);
      toast.success("会话已删除");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    } finally {
      setWorkingThreadId(null);
    }
  }

  async function handleShare(threadId: string) {
    const url = `${window.location.origin}/workspace/chats/${threadId}`;
    await navigator.clipboard.writeText(url);
    toast.success("链接已复制到剪贴板");
  }

  return (
    <section className="mx-auto flex h-full w-full max-w-6xl flex-col px-4 pb-8 pt-3 md:px-6">
      <header className="mb-6">
        <div className="panel-strong p-6">
          <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
            <div className="max-w-2xl">
              <div className="font-heading text-5xl leading-[0.95]">Chats</div>
              <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
                像浏览一个共享工作区里的项目桌面一样，快速回到过去的上下文、结论和产出。
              </p>
            </div>
            <div className="glass-badge inline-flex items-center gap-2 self-start rounded-full px-4 py-2 text-xs uppercase tracking-[0.24em] text-[var(--muted)]">
              Workspace history
            </div>
          </div>
          <div className="surface-subtle mt-6 flex items-center gap-3 rounded-[28px] px-4">
            <Search className="h-4 w-4 text-[var(--muted)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索标题或摘要..."
              className="h-14 w-full bg-transparent text-sm outline-none placeholder:text-[var(--muted)]"
            />
          </div>
        </div>
      </header>

      <div className="grid gap-3">
        {isLoading && (
          <div className="panel px-5 py-6 text-sm text-[var(--muted)]">
            正在加载会话...
          </div>
        )}
        {!isLoading &&
          threads.map((thread) => (
            <div key={thread.id} className="panel group p-5 transition hover:-translate-y-0.5 hover:border-[var(--line-strong)] hover:bg-white/70">
              <Link href={`/workspace/chats/${thread.id}`} className="block">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-lg font-semibold">{thread.title}</div>
                    <div className="mt-2 line-clamp-2 text-sm leading-7 text-[var(--muted)]">{thread.preview || "暂无摘要"}</div>
                  </div>
                  <div className="glass-badge rounded-full px-3 py-1 text-xs text-[var(--muted)]">
                    {formatRelativeTime(thread.updated_at)}
                  </div>
                </div>
              </Link>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleRename(thread.id, thread.title)}
                  disabled={workingThreadId === thread.id}
                  className="glass-button inline-flex h-9 items-center gap-1 rounded-full px-3 text-xs text-[var(--muted)] hover:text-[var(--foreground)]"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  重命名
                </button>
                <button
                  type="button"
                  onClick={() => void handleShare(thread.id)}
                  className="glass-button inline-flex h-9 items-center gap-1 rounded-full px-3 text-xs text-[var(--muted)] hover:text-[var(--foreground)]"
                >
                  <Share2 className="h-3.5 w-3.5" />
                  分享
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(thread.id)}
                  disabled={workingThreadId === thread.id}
                  className="inline-flex h-9 items-center gap-1 rounded-full border border-[rgba(221,93,86,0.18)] bg-[rgba(221,93,86,0.08)] px-3 text-xs text-[var(--danger)] transition hover:bg-[rgba(221,93,86,0.12)]"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  删除
                </button>
              </div>
            </div>
          ))}
        {!isLoading && threads.length === 0 && (
          <div className="panel border-dashed px-5 py-10 text-sm text-[var(--muted)]">
            没有匹配的会话。
          </div>
        )}
      </div>
    </section>
  );
}
