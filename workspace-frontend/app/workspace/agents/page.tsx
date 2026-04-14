"use client";

import { Bot, Plus, Sparkles } from "lucide-react";
import Link from "next/link";

import { useAgents } from "@/core/agents/hooks";

export default function AgentsPage() {
  const { data: agents = [], isLoading } = useAgents();

  return (
    <section className="mx-auto flex h-full w-full max-w-6xl flex-col px-6 py-8">
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-[var(--muted)]">
            Agent Gallery
          </span>
          <h1 className="mt-4 font-heading text-5xl text-[var(--foreground)]">创建、训练和进入你的专属 Agent</h1>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-[var(--muted)]">
            每个 Agent 都会落盘为 `agents/name/config.yaml` 和 `SOUL.md`，运行时复用同一个 VD-HARNESS lead agent。
          </p>
        </div>
        <Link
          href="/workspace/agents/new"
          className="inline-flex h-12 items-center justify-center gap-2 rounded-2xl bg-[var(--accent)] px-5 text-sm font-semibold text-[#04110a] transition hover:brightness-110"
        >
          <Plus className="h-4 w-4" />
          创建 Agent
        </Link>
      </div>

      {isLoading ? (
        <div className="panel p-8 text-sm text-[var(--muted)]">正在加载 Agents...</div>
      ) : agents.length === 0 ? (
        <div className="panel flex flex-col items-center justify-center gap-4 p-12 text-center">
          <Sparkles className="h-10 w-10 text-[var(--accent)]" />
          <h2 className="font-heading text-3xl">还没有自定义 Agent</h2>
          <p className="max-w-xl text-sm leading-7 text-[var(--muted)]">
            从创建向导开始：先命名，再通过对话完善 SOUL，最后跳转到这个 Agent 的专属聊天入口。
          </p>
          <Link
            href="/workspace/agents/new"
            className="inline-flex h-11 items-center justify-center rounded-2xl border border-[var(--line-strong)] px-4 text-sm text-[var(--foreground)] transition hover:bg-white/10"
          >
            开始创建
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => (
            <Link
              key={agent.name}
              href={`/workspace/agents/${agent.name}/chats/new`}
              className="panel group flex min-h-52 flex-col justify-between p-6 transition hover:-translate-y-1 hover:border-[var(--line-strong)]"
            >
              <div>
                <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-[var(--accent)]">
                  <Bot className="h-5 w-5" />
                </div>
                <h2 className="font-heading text-3xl">{agent.name}</h2>
                <p className="mt-3 line-clamp-3 text-sm leading-7 text-[var(--muted)]">
                  {agent.description || "尚未填写描述。进入创建向导继续完善它的定位、能力边界和交付风格。"}
                </p>
              </div>
              <span className="mt-6 text-xs text-[var(--muted)] group-hover:text-[var(--foreground)]">
                进入专属聊天
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
