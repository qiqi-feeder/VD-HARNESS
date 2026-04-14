"use client";

import { CheckCircle2, Loader2, MessageSquare, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ChatScreen } from "@/components/workspace/chat-screen";
import { useCreateAgent, useUpdateAgent } from "@/core/agents/hooks";

function normalizeAgentName(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, "-");
}

export default function NewAgentPage() {
  const router = useRouter();
  const createAgent = useCreateAgent();
  const [createdName, setCreatedName] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [soul, setSoul] = useState("");
  const updateAgent = useUpdateAgent(createdName || "draft");

  async function createEmptyAgent() {
    const normalized = normalizeAgentName(name);
    if (!normalized) return;
    const agent = await createAgent.mutateAsync({
      name: normalized,
      description,
      model: null,
      tool_groups: [],
      soul: soul || `# ${normalized}\n\n## 定位\n请通过 setup 对话继续完善这个 Agent。`,
    });
    setCreatedName(agent.name);
    setName(agent.name);
    setSoul(agent.soul ?? "");
  }

  async function saveAndOpen() {
    if (!createdName) return;
    await updateAgent.mutateAsync({ description, soul });
    router.push(`/workspace/agents/${createdName}/chats/new`);
  }

  return (
    <section className="flex h-full min-h-0 flex-col xl:flex-row">
      <aside className="w-full border-b border-white/8 bg-[var(--panel)]/70 p-6 xl:h-full xl:w-[420px] xl:border-b-0 xl:border-r">
        <div className="space-y-6">
          <div>
            <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-[var(--muted)]">
              Agent Wizard
            </span>
            <h1 className="mt-4 font-heading text-4xl">完整创建向导</h1>
            <p className="mt-3 text-sm leading-7 text-[var(--muted)]">
              先创建空 Agent，再通过右侧 setup 对话完善 SOUL。保存后会进入这个 Agent 的专属聊天入口。
            </p>
          </div>

          <div className="space-y-3">
            <label className="block text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Name</label>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={Boolean(createdName)}
              placeholder="research-copilot"
              className="h-12 w-full rounded-2xl border border-white/8 bg-black/20 px-4 text-sm outline-none transition focus:border-[var(--line-strong)] disabled:opacity-60"
            />
          </div>

          <div className="space-y-3">
            <label className="block text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Description</label>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              placeholder="这个 Agent 解决什么问题？"
              className="w-full resize-none rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm leading-6 outline-none transition focus:border-[var(--line-strong)]"
            />
          </div>

          <div className="space-y-3">
            <label className="block text-xs uppercase tracking-[0.2em] text-[var(--muted)]">SOUL.md</label>
            <textarea
              value={soul}
              onChange={(event) => setSoul(event.target.value)}
              rows={10}
              placeholder="# Agent SOUL\n\n## 定位\n..."
              className="w-full resize-none rounded-2xl border border-white/8 bg-black/20 px-4 py-3 font-mono text-xs leading-6 outline-none transition focus:border-[var(--line-strong)]"
            />
          </div>

          {!createdName ? (
            <button
              type="button"
              onClick={() => void createEmptyAgent()}
              disabled={!name.trim() || createAgent.isPending}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-[var(--accent)] px-4 text-sm font-semibold text-[#04110a] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {createAgent.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              创建空 Agent
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void saveAndOpen()}
              disabled={updateAgent.isPending}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-[var(--accent)] px-4 text-sm font-semibold text-[#04110a] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {updateAgent.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              保存并进入聊天
            </button>
          )}

          {createAgent.error instanceof Error && (
            <p className="text-sm text-red-300">{createAgent.error.message}</p>
          )}
        </div>
      </aside>

      <div className="min-h-0 flex-1">
        {createdName ? (
          <ChatScreen initialThreadId={null} agentName={createdName} />
        ) : (
          <div className="flex h-full items-center justify-center p-8 text-center">
            <div className="panel max-w-xl space-y-4 p-8">
              <MessageSquare className="mx-auto h-10 w-10 text-[var(--accent)]" />
              <h2 className="font-heading text-3xl">先命名，再进入 setup 对话</h2>
              <p className="text-sm leading-7 text-[var(--muted)]">
                创建空 Agent 后，右侧会打开专属 setup chat。你可以让 VD-HARNESS 帮你把目标、语气、工具边界整理成 SOUL。
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
