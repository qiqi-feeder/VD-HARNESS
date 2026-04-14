"use client";

import { Keyboard, MessageSquarePlus, Settings2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useThreads } from "@/core/threads/hooks";

export function WorkspaceCommandPalette({
  open,
  onOpenChange,
  onOpenSettings,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenSettings: () => void;
}) {
  const router = useRouter();
  const { data: threads = [] } = useThreads();
  const [query, setQuery] = useState("");

  const filteredThreads = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return threads.slice(0, 8);
    return threads
      .filter((thread) => thread.title.toLowerCase().includes(needle) || thread.preview.toLowerCase().includes(needle))
      .slice(0, 8);
  }, [query, threads]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 py-[12vh] backdrop-blur-sm">
      <div className="panel w-full max-w-2xl overflow-hidden p-0">
        <div className="border-b border-white/8 px-4 py-4">
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索命令或最近对话..."
            className="h-12 w-full rounded-2xl border border-white/8 bg-black/20 px-4 text-sm outline-none transition focus:border-[var(--line-strong)]"
          />
        </div>

        <div className="space-y-4 p-4">
          <section className="space-y-2">
            <div className="text-xs uppercase tracking-[0.24em] text-[var(--muted)]">快捷动作</div>
            <div className="grid gap-2 md:grid-cols-3">
              <button
                type="button"
                className="rounded-2xl border border-white/8 bg-white/4 p-4 text-left transition hover:border-[var(--line-strong)] hover:bg-white/6"
                onClick={() => {
                  onOpenChange(false);
                  router.push("/workspace/chats/new");
                }}
              >
                <MessageSquarePlus className="mb-3 h-5 w-5 text-[var(--accent)]" />
                <div className="text-sm font-semibold">新对话</div>
                <div className="mt-1 text-xs text-[var(--muted)]">Cmd/Ctrl + Shift + N</div>
              </button>
              <button
                type="button"
                className="rounded-2xl border border-white/8 bg-white/4 p-4 text-left transition hover:border-[var(--line-strong)] hover:bg-white/6"
                onClick={() => {
                  onOpenChange(false);
                  onOpenSettings();
                }}
              >
                <Settings2 className="mb-3 h-5 w-5 text-[var(--accent)]" />
                <div className="text-sm font-semibold">打开设置</div>
                <div className="mt-1 text-xs text-[var(--muted)]">Cmd/Ctrl + ,</div>
              </button>
              <div className="rounded-2xl border border-white/8 bg-white/4 p-4">
                <Keyboard className="mb-3 h-5 w-5 text-[var(--accent)]" />
                <div className="text-sm font-semibold">快捷键帮助</div>
                <div className="mt-1 space-y-1 text-xs text-[var(--muted)]">
                  <div>Cmd/Ctrl + K：命令面板</div>
                  <div>Cmd/Ctrl + B：折叠侧边栏</div>
                  <div>Enter：发送，Shift + Enter：换行</div>
                </div>
              </div>
            </div>
          </section>

          <section className="space-y-2">
            <div className="text-xs uppercase tracking-[0.24em] text-[var(--muted)]">最近对话</div>
            <div className="space-y-2">
              {filteredThreads.map((thread) => (
                <Link
                  key={thread.id}
                  href={`/workspace/chats/${thread.id}`}
                  className="block rounded-2xl border border-white/8 bg-white/4 px-4 py-3 transition hover:border-[var(--line-strong)] hover:bg-white/6"
                  onClick={() => onOpenChange(false)}
                >
                  <div className="truncate text-sm font-medium">{thread.title}</div>
                  <div className="mt-1 truncate text-xs text-[var(--muted)]">{thread.preview || "暂无摘要"}</div>
                </Link>
              ))}
              {filteredThreads.length === 0 && (
                <div className="rounded-2xl border border-dashed border-white/8 px-4 py-6 text-sm text-[var(--muted)]">
                  没有匹配的命令或会话。
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="border-t border-white/8 px-4 py-3 text-xs text-[var(--muted)]">
          Esc 关闭命令面板
        </div>
      </div>
      <button type="button" className="absolute inset-0 -z-10" aria-label="关闭命令面板" onClick={() => onOpenChange(false)} />
    </div>
  );
}
