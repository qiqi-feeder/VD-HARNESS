"use client";

import { ChevronRight, MessageSquarePlus, MessagesSquare, Pencil, Settings2, Share2, Trash2, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useDeleteThread, useRenameThread, useThreads } from "@/core/threads/hooks";
import { cn, formatRelativeTime } from "@/lib/utils";

/* Landing page 同款 SVG Logo */
function VdFlowLogo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M16 2L28.124 9V23L16 30L3.876 23V9L16 2Z"
        stroke="url(#sidebar-logo-grad)"
        strokeWidth="2"
        fill="none"
      />
      <path
        d="M11 12L16 8L21 12L16 20L11 12Z"
        fill="url(#sidebar-logo-grad)"
        opacity="0.8"
      />
      <circle cx="16" cy="14" r="2" fill="#050508" />
      <defs>
        <linearGradient id="sidebar-logo-grad" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#00ffff" />
          <stop offset="0.5" stopColor="#a855f7" />
          <stop offset="1" stopColor="#ff00ff" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function WorkspaceSidebar({
  open,
  pathname,
  onOpenSettings,
}: {
  open: boolean;
  pathname: string;
  onOpenSettings: () => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: threads = [] } = useThreads();
  const renameThread = useRenameThread();
  const deleteThread = useDeleteThread();
  const [workingThreadId, setWorkingThreadId] = useState<string | null>(null);

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
      if (pathname === `/workspace/chats/${threadId}`) {
        router.push("/workspace/chats/new");
      }
      await queryClient.invalidateQueries({ queryKey: ["threads"] });
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
    <aside
      className={cn(
        "sidebar-embedded sticky top-0 hidden shrink-0 flex-col overflow-hidden transition-[width] duration-300 md:flex h-screen z-10",
        open ? "w-[280px]" : "w-[72px]",
      )}
    >
      <div className="border-b border-[rgba(0,212,255,0.06)] px-4 py-5">
        <Link href="/" className={cn("flex items-center gap-3 group transition-colors", !open && "justify-center")}>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center transition group-hover:drop-shadow-[0_0_8px_rgba(0,255,255,0.4)]">
            <VdFlowLogo size={32} />
          </div>
          {open && (
            <div className="min-w-0 flex-1 opacity-100 transition-opacity duration-300">
              <div className="font-heading text-xl font-bold leading-none tracking-tight">VD-HARNESS</div>
              <div className="mt-1 text-[10px] tracking-widest text-[#00d4ff] uppercase font-medium">Super Agent</div>
            </div>
          )}
        </Link>
      </div>

      <div className="flex flex-col gap-3 p-4">
        <Link
          href="/workspace/chats/new"
          className={cn(
            "inline-flex h-11 items-center rounded-2xl bg-[linear-gradient(135deg,#00bfff,#a855f7)] font-semibold text-white shadow-[0_4px_20px_rgba(0,212,255,0.25)] transition-all hover:-translate-y-0.5 hover:shadow-[0_8px_28px_rgba(0,212,255,0.4)]",
            open ? "justify-center gap-2 px-4" : "justify-center",
          )}
        >
          <MessageSquarePlus className="h-4 w-4" />
          {open && "新对话"}
        </Link>

        <nav className={cn("surface-subtle flex gap-2 rounded-2xl p-1", !open && "flex-col")}>
          <SidebarNavLink href="/workspace/chats" open={open} active={pathname.startsWith("/workspace/chats")}>
            <MessagesSquare className="h-4 w-4" />
            {open && <span>Chats</span>}
          </SidebarNavLink>
          <SidebarNavLink href="/workspace/agents" open={open} active={pathname.startsWith("/workspace/agents")}>
            <Zap className="h-4 w-4" />
            {open && <span>Agents</span>}
          </SidebarNavLink>
        </nav>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-3 pb-3">
        <div className={cn("mb-3 flex items-center px-2 text-xs uppercase tracking-[0.24em] text-[var(--muted)]", !open && "justify-center")}>
          {open ? "最近对话" : "最近"}
        </div>
        <div className="min-h-0 space-y-1.5 overflow-y-auto px-2">
          {threads.slice(0, 12).map((thread) => {
            const active = pathname === `/workspace/chats/${thread.id}`;
            return (
              <div
                key={thread.id}
                className={cn(
                  "group relative flex flex-col rounded-[16px] transition-all hover:bg-white/5",
                  active && "bg-white/10 ring-1 ring-[var(--line-strong)]",
                )}
              >
                <Link
                  href={`/workspace/chats/${thread.id}`}
                  className={cn("flex items-center gap-3 px-3 py-2.5", !open && "justify-center")}
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white/5 text-[var(--muted)]">
                    <ChevronRight className={cn("h-4 w-4 transition-transform group-hover:translate-x-0.5", active && "text-[var(--accent)]")} />
                  </div>
                  {open && (
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-[var(--foreground)]">{thread.title}</div>
                      <div className="mt-0.5 truncate text-[11px] text-[var(--muted)]">
                        {formatRelativeTime(thread.updated_at)}
                      </div>
                    </div>
                  )}
                </Link>

                {open && active && (
                  <div className="flex items-center gap-1.5 px-3 pb-2.5 pt-0.5 opacity-80 transition group-hover:opacity-100">
                    <button
                      type="button"
                      className="glass-button inline-flex h-7 items-center gap-1 rounded-full px-2 text-[11px] text-[var(--muted)] hover:text-white"
                      onClick={() => handleRename(thread.id, thread.title)}
                      disabled={workingThreadId === thread.id}
                    >
                      <Pencil className="h-3 w-3" />
                      重命名
                    </button>
                    <button
                      type="button"
                      className="glass-button inline-flex h-7 items-center gap-1 rounded-full px-2 text-[11px] text-[var(--muted)] hover:text-white"
                      onClick={() => void handleShare(thread.id)}
                    >
                      <Share2 className="h-3 w-3" />
                      分享
                    </button>
                    <button
                      type="button"
                      className="inline-flex h-7 items-center gap-1 rounded-full bg-red-500/10 px-2 text-[11px] text-red-400 transition hover:bg-red-500/20"
                      onClick={() => handleDelete(thread.id)}
                      disabled={workingThreadId === thread.id}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="border-t border-[var(--line-soft)] p-3">
        <button
          type="button"
          className={cn(
            "glass-button inline-flex h-11 w-full items-center rounded-[20px] px-3 text-sm text-[var(--muted)] hover:text-[var(--foreground)]",
            open ? "justify-between" : "justify-center",
          )}
          onClick={onOpenSettings}
        >
          <span className="inline-flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            {open && "Settings"}
          </span>
          {open && <ChevronRight className="h-4 w-4" />}
        </button>
      </div>
    </aside>
  );
}

function SidebarNavLink({
  href,
  active,
  open,
  children,
}: {
  href: string;
  active: boolean;
  open: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex h-10 items-center rounded-xl px-2.5 text-sm transition-all duration-200",
        active
          ? "bg-white/10 text-white shadow-sm ring-1 ring-white/5"
          : "text-[var(--muted)] hover:bg-white/5 hover:text-white",
        open ? "flex-1 justify-start gap-2" : "w-full justify-center",
      )}
    >
      {children}
    </Link>
  );
}
