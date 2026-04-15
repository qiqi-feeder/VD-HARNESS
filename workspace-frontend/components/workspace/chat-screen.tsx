"use client";

import {
  Download,
  Ellipsis,
  Files,
  PencilLine,
  Share2,
  Sparkles,
} from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { toast } from "sonner";

import { ArtifactDrawer } from "@/components/workspace/artifact-drawer";
import { AnimatedGreeting } from "@/components/workspace/animated-greeting";
import { InputPanel } from "@/components/workspace/input-panel";
import { MessageList } from "@/components/workspace/message-list";
import { TodoPanel } from "@/components/workspace/todo-panel";
import { uploadThreadFiles } from "@/core/api/client";
import { getLangGraphClient } from "@/core/langgraph/client";
import { useStream as useThreadStream } from "@langchain/langgraph-sdk/react";
import { useModels } from "@/core/models/hooks";
import { usePersistentFlag, useThreadSettings } from "@/core/settings/hooks";
import { useRenameThread, useThread } from "@/core/threads/hooks";
import type {
  AgentThreadState,
  ChatMessage,
  FileInMessage,
  SSEEvent,
  StreamingState,
  ThreadSummary,
  ToolCallItem,
  UploadedFileInfo,
} from "@/core/types";
import { cn, downloadTextFile, formatTokenCount } from "@/lib/utils";

const QUICK_PROMPTS = [
  "先读这个仓库，给我核心架构图和风险点",
  "帮我拆一个执行计划，列出里程碑和依赖",
  "整理这次对话的结论，并输出可分享摘要",
];



function createEmptyStreamingState(): StreamingState {
  return {
    isStreaming: false,
    answerBuffer: "",
    thinkingBuffer: "",
    hasThinking: false,
    phaseLines: [],
    toolCalls: [],
    subtasks: [],
    tokenUsage: null,
  };
}

function exportThreadAsMarkdown(thread: ThreadSummary | null, messages: ChatMessage[]) {
  const title = thread?.title ?? "新对话";
  const markdown = [`# ${title}`, ""]
    .concat(
      messages.flatMap((message) => [
        `## ${message.role === "user" ? "User" : "Assistant"}`,
        message.content,
        message.thinking ? `\n> Thinking\n>\n> ${message.thinking.replace(/\n/g, "\n> ")}` : "",
        "",
      ]),
    )
    .join("\n");

  downloadTextFile(`${title}.md`, markdown, "text/markdown;charset=utf-8");
}

function exportThreadAsJson(thread: ThreadSummary | null, messages: ChatMessage[]) {
  const title = thread?.title ?? "新对话";
  downloadTextFile(`${title}.json`, JSON.stringify({ thread, messages }, null, 2), "application/json;charset=utf-8");
}

function processEvent(event: SSEEvent, state: StreamingState, setCurrentThreadId: (threadId: string) => void) {
  switch (event.type) {
    case "meta":
      setCurrentThreadId(event.thread_id);
      break;
    case "content":
      state.answerBuffer += event.text;
      break;
    case "thinking_start":
      state.hasThinking = true;
      state.thinkingBuffer = "";
      break;
    case "thinking_delta":
      state.hasThinking = true;
      state.thinkingBuffer += event.text;
      break;
    case "thinking_end":
      break;
    case "phase":
      if (event.text) state.phaseLines.push(event.text);
      break;
    case "tool_start": {
      const item: ToolCallItem = { tool: event.tool, status: "running" };
      if (event.task_id) item.taskId = event.task_id;
      if (event.description) item.description = event.description;
      if (event.subagent_type) item.subagentType = event.subagent_type;
      state.toolCalls.push(item);
      break;
    }
    case "tool_end": {
      const active = state.toolCalls.find((item) => item.tool === event.tool && item.status === "running");
      if (active) {
        active.status = "done";
        active.output = event.output;
      }
      break;
    }
    case "task_started": {
      const exists = state.subtasks.find((task) => task.taskId === event.task_id);
      if (!exists) {
        state.subtasks.push({
          taskId: event.task_id,
          description: event.description,
          subagentType: event.subagent_type ?? "general",
          status: "running",
          prompt: event.prompt,
        });
      }
      break;
    }
    case "task_running": {
      const task = state.subtasks.find((item) => item.taskId === event.task_id);
      if (task) {
        task.status = "running";
        task.latestMessage = event.message;
      }
      break;
    }
    case "task_completed": {
      const task = state.subtasks.find((item) => item.taskId === event.task_id);
      if (task) {
        task.status = "completed";
        task.output = event.result;
        task.elapsedSeconds = event.elapsed_seconds;
      }
      break;
    }
    case "task_failed":
    case "task_timed_out": {
      const task = state.subtasks.find((item) => item.taskId === event.task_id);
      if (task) {
        task.status = "failed";
        task.output = event.error;
      }
      break;
    }
    case "task_cancelled": {
      const task = state.subtasks.find((item) => item.taskId === event.task_id);
      if (task) {
        task.status = "failed";
      }
      break;
    }
    case "token_usage":
      state.tokenUsage = {
        input_tokens: event.input_tokens,
        output_tokens: event.output_tokens,
        total_tokens: event.total_tokens,
        reasoning_tokens: event.reasoning_tokens,
      };
      break;
    case "llm_retry":
      state.phaseLines.push(`重试中：${event.message}`);
      break;
    case "error":
      state.answerBuffer += `\n\n❌ ${event.text}`;
      break;
    case "done":
      break;
  }
}

function contentToText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) return String((part as { text?: unknown }).text ?? "");
        return "";
      })
      .join("");
  }
  return content == null ? "" : String(content);
}

function langGraphMessagesToChatMessages(messages: Array<Record<string, unknown>> = []): ChatMessage[] {
  const result: ChatMessage[] = [];
  for (const message of messages) {
    const type = String(message.type ?? message.role ?? "");
    const role = type === "human" || type === "user" ? "user" : type === "ai" || type === "assistant" ? "assistant" : "";
    if (!role) continue;
    const additional = (message.additional_kwargs ?? {}) as Record<string, unknown>;
    // Filter out SummarizationMiddleware's injected summary messages
    if (additional.lc_source === "summarization") continue;
    const rawFiles = Array.isArray(additional.files) ? (additional.files as FileInMessage[]) : undefined;
    const item: ChatMessage = {
      id: String(message.id ?? `msg-${Math.random().toString(36).slice(2)}`),
      role,
      content: contentToText(message.content),
      created_at: String(additional.created_at ?? ""),
      status: String(additional.status ?? "completed"),
      thinking: typeof additional.thinking === "string" ? additional.thinking : undefined,
      files: rawFiles,
    };
    if (item.content || item.thinking) result.push(item);
  }
  return result;
}

function processLangChainEvent(event: Record<string, unknown>, state: StreamingState) {
  const kind = String(event.event ?? "");
  const data = (event.data ?? {}) as Record<string, unknown>;
  if (kind === "on_chat_model_stream") {
    const chunk = (data.chunk ?? {}) as Record<string, unknown>;
    const content = chunk.content;
    if (Array.isArray(content)) {
      for (const part of content) {
        if (part && typeof part === "object") {
          const typed = part as { type?: string; text?: unknown };
          const text = String(typed.text ?? "");
          if (typed.type === "reasoning" || typed.type === "thinking") {
            state.hasThinking = true;
            state.thinkingBuffer += text;
          } else {
            state.answerBuffer += text;
          }
        }
      }
      return;
    }
    const text = contentToText(content);
    if (text) {
      state.answerBuffer += text;
    }
    return;
  }
  if (kind === "on_tool_start") {
    const tool = String(event.name ?? "tool");
    const toolInput = (data.input ?? {}) as Record<string, unknown>;
    const item: ToolCallItem = { tool, status: "running" };
    if (tool === "task") {
      item.taskId = String(event.run_id ?? "");
      item.description = String(toolInput.description ?? "子任务");
      item.subagentType = String(toolInput.subagent_type ?? "general");
    }
    state.toolCalls.push(item);
    return;
  }
  if (kind === "on_tool_end") {
    const tool = String(event.name ?? "tool");
    const active = state.toolCalls.find((item) => item.tool === tool && item.status === "running");
    if (active) {
      active.status = "done";
      active.output = contentToText(data.output);
    }
  }
}

function processCustomEvent(data: unknown, state: StreamingState) {
  if (!data || typeof data !== "object") return;
  processEvent(data as SSEEvent, state, () => {});
}

function sdkFiles(files: UploadedFileInfo[]) {
  return files.map((file) => ({
    filename: file.filename,
    size: file.size,
    path: file.path,
    virtual_path: file.virtual_path,
    artifact_url: file.artifact_url,
  }));
}

export function ChatScreen({ initialThreadId, agentName }: { initialThreadId: string | null; agentName?: string }) {
  const queryClient = useQueryClient();
  const renameThread = useRenameThread();
  const { data: models = [] } = useModels();
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(initialThreadId);
  const currentThreadIdRef = useRef<string | null>(initialThreadId);
  const threadQuery = useThread(currentThreadId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<StreamingState>(createEmptyStreamingState());
  const [isBusy, setIsBusy] = useState(false);
  const [artifactOpen, setArtifactOpen] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [headerMenuOpen, setHeaderMenuOpen] = useState(false);
  const streamingStateRef = useRef<StreamingState | null>(null);
  const [notificationsEnabled] = usePersistentFlag("vdharness.notifications", true);
  const [settings, setSettings] = useThreadSettings(currentThreadId ?? "new", models);
  const threadStream = useThreadStream<AgentThreadState>({
    client: getLangGraphClient(),
    assistantId: agentName ?? "lead_agent",
    threadId: currentThreadId,
    fetchStateHistory: false,
    onThreadId: (threadId) => {
      if (!currentThreadIdRef.current) {
        const nextUrl = agentName ? `/workspace/agents/${agentName}/chats/${threadId}` : `/workspace/chats/${threadId}`;
        window.history.replaceState(window.history.state, "", nextUrl);
      }
      currentThreadIdRef.current = threadId;
      setCurrentThreadId(threadId);
    },
    onLangChainEvent: (event) => {
      const active = streamingStateRef.current;
      if (!active) return;
      processLangChainEvent(event as Record<string, unknown>, active);
      setStreaming({ ...active, toolCalls: [...active.toolCalls], subtasks: [...active.subtasks] });
    },
    onCustomEvent: (event) => {
      const active = streamingStateRef.current;
      if (!active) return;
      processCustomEvent(event, active);
      setStreaming({ ...active, toolCalls: [...active.toolCalls], subtasks: [...active.subtasks] });
    },
    onFinish: (state) => {
      setMessages(langGraphMessagesToChatMessages((state.values.messages ?? []) as Array<Record<string, unknown>>));
    },
  });

  const thread = threadQuery.data?.thread ?? null;
  const artifacts = (threadStream.values.artifacts?.length ? threadStream.values.artifacts : threadQuery.data?.artifacts) ?? [];
  const todos = (threadStream.values.todos?.length ? threadStream.values.todos : threadQuery.data?.todos) ?? [];
  const activeSkills = (threadStream.values.active_skills?.length
    ? threadStream.values.active_skills
    : threadQuery.data?.active_skills) ?? [];
  const hasConversation = messages.length > 0 || streaming.isStreaming;

  useEffect(() => {
    setCurrentThreadId(initialThreadId);
    currentThreadIdRef.current = initialThreadId;
  }, [initialThreadId]);

  useEffect(() => {
    if (!isBusy) {
      const sdkMessages = langGraphMessagesToChatMessages(
        (threadStream.values.messages ?? []) as Array<Record<string, unknown>>,
      );
      setMessages(sdkMessages.length ? sdkMessages : (threadQuery.data?.messages ?? []));
    }
  }, [isBusy, threadQuery.data?.messages, threadStream.values.messages]);

  useEffect(() => {
    setTitleDraft(thread?.title ?? "");
  }, [thread?.title]);

  const renameMutation = useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      renameThread.mutateAsync({ threadId, title }),
  });

  async function handleShare() {
    if (typeof window === "undefined") return;
    const targetUrl = window.location.href;
    try {
      await navigator.clipboard.writeText(targetUrl);
      toast.success("链接已复制到剪贴板");
    } catch {
      toast.error("复制失败");
    }
  }

  async function saveTitle() {
    const nextTitle = titleDraft.trim();
    if (!currentThreadId || !nextTitle || nextTitle === thread?.title) {
      setEditingTitle(false);
      return;
    }
    await renameMutation.mutateAsync({ threadId: currentThreadId, title: nextTitle });
    await queryClient.invalidateQueries({ queryKey: ["thread", currentThreadId] });
    setEditingTitle(false);
  }

  async function handleSend(text: string, files: File[] = []) {
    if (!settings.modelName) return;

    const optimisticFiles: FileInMessage[] = files.map((file) => ({
      filename: file.name,
      size: file.size,
      path: "",
      status: "uploading" as const,
    }));
    setMessages((current) => [
      ...current,
      {
        id: `local-${Date.now()}`,
        role: "user",
        content: text,
        files: optimisticFiles.length > 0 ? optimisticFiles : undefined,
      },
    ]);
    setIsBusy(true);
    const nextState = createEmptyStreamingState();
    nextState.isStreaming = true;
    streamingStateRef.current = nextState;
    setStreaming(nextState);

    try {
      let targetThreadId = currentThreadIdRef.current;
      if (!targetThreadId && files.length) {
        const created = await getLangGraphClient().threads.create({
          metadata: { title: text, agent_name: agentName },
        });
        targetThreadId = created.thread_id;
        threadStream.switchThread(targetThreadId);
        currentThreadIdRef.current = targetThreadId;
        setCurrentThreadId(targetThreadId);
        const nextUrl = agentName ? `/workspace/agents/${agentName}/chats/${targetThreadId}` : `/workspace/chats/${targetThreadId}`;
        window.history.replaceState(window.history.state, "", nextUrl);
      }

      const uploadedFiles = targetThreadId && files.length ? await uploadThreadFiles(targetThreadId, files) : [];
      await threadStream.submit(
        {
          messages: [
            {
              type: "human",
              content: [{ type: "text", text }],
              additional_kwargs: { files: sdkFiles(uploadedFiles) },
            },
          ],
          uploaded_files: sdkFiles(uploadedFiles),
        } as Partial<AgentThreadState>,
        {
          threadId: targetThreadId ?? undefined,
          streamMode: ["events", "values", "custom", "tools"],
          streamSubgraphs: true,
          streamResumable: true,
          config: { recursion_limit: 1000 },
          context: {
            model: settings.modelName,
            mode: settings.mode,
            reasoning_effort: settings.reasoningEffort,
            agent_name: agentName,
            thread_id: targetThreadId,
            subagent_enabled: settings.mode === "ultra",
          },
          metadata: {
            model: settings.modelName,
            mode: settings.mode,
            reasoning_effort: settings.reasoningEffort,
            agent_name: agentName,
          },
        },
      );
    } catch (error) {
      if (error instanceof Error && error.name !== "AbortError") {
        nextState.answerBuffer += `\n\n❌ ${error.message}`;
      }
    } finally {
      nextState.isStreaming = false;
      streamingStateRef.current = null;
      setStreaming(createEmptyStreamingState());
      setIsBusy(false);
      const latestThreadId = currentThreadIdRef.current;
      await queryClient.invalidateQueries({ queryKey: ["threads"] });
      if (latestThreadId) {
        await queryClient.invalidateQueries({ queryKey: ["thread", latestThreadId] });
      }

      if (
        notificationsEnabled &&
        typeof window !== "undefined" &&
        latestThreadId &&
        !document.hasFocus() &&
        "Notification" in window &&
        Notification.permission === "granted"
      ) {
        const latestText = nextState.answerBuffer.trim() || text;
        new Notification(thread?.title ?? "VD-HARNESS Workspace", {
          body: latestText.length > 160 ? `${latestText.slice(0, 160)}...` : latestText,
        });
      }
    }
  }

  function handleStop() {
    void threadStream.stop();
  }


  return (
    <>
      <section className="flex min-h-0 flex-1 flex-col">
        {!hasConversation ? (
          /* ── Centered landing: welcome + input together ── */
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4 landing-enter">
            <div className="w-full max-w-2xl space-y-8 text-center -mt-12">
              <AnimatedGreeting />

              <div className="flex flex-wrap items-center justify-center gap-2">
                {QUICK_PROMPTS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    className="inline-flex h-8 items-center rounded-full border border-white/[0.06] bg-white/[0.03] px-3.5 text-[12px] text-[var(--muted)] hover:text-white hover:bg-white/[0.06] hover:border-white/[0.12] transition-colors cursor-pointer"
                    onClick={() => handleSend(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>

              <div className="pt-4 input-glow rounded-2xl">
                <InputPanel
                  models={models}
                  settings={settings}
                  isBusy={isBusy}
                  isNewThread={true}
                  onSettingsChange={setSettings}
                  onSend={handleSend}
                  onStop={handleStop}
                />
              </div>

              <div className="text-[11px] text-[var(--muted)]/40">
                <span className="opacity-60">⌘K</span> 命令面板 · <span className="opacity-60">⌘,</span> 设置
              </div>
            </div>
          </div>
        ) : (
          /* ── Conversation mode: header + messages + sticky input ── */
          <>
            <header className="px-4 pb-0 pt-1 md:px-6 conversation-enter">
              <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-1 py-1.5">
                <div className="min-w-0 flex-1 flex items-center gap-2">
                  {!editingTitle ? (
                    <div className="group/title flex items-center gap-2 min-w-0">
                      <h1 className="truncate text-sm font-normal text-[var(--muted)] hover:text-white/80 transition-colors">{thread?.title ?? "新对话"}</h1>
                      {currentThreadId ? (
                        <button
                          type="button"
                          className="inline-flex h-5 w-5 items-center justify-center rounded text-[var(--muted)]/50 opacity-0 group-hover/title:opacity-100 hover:text-white transition-all"
                          onClick={() => setEditingTitle(true)}
                        >
                          <PencilLine className="h-2.5 w-2.5" />
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <input
                      value={titleDraft}
                      onChange={(event) => setTitleDraft(event.target.value)}
                      onBlur={() => void saveTitle()}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void saveTitle();
                        if (event.key === "Escape") setEditingTitle(false);
                      }}
                      autoFocus
                      className="h-7 w-full max-w-md rounded-lg bg-white/5 px-3 text-xs text-white outline-none ring-1 ring-white/10 focus:ring-white/20"
                    />
                  )}
                </div>

                <div className="relative flex items-center gap-1.5">
                  {artifacts.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setArtifactOpen(true)}
                      className="inline-flex h-7 items-center gap-1.5 rounded-lg px-2 text-[11px] text-[var(--muted)] hover:text-white hover:bg-white/5 transition-colors"
                    >
                      <Files className="h-3 w-3" />
                      <span>{artifacts.length}</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setHeaderMenuOpen((v) => !v)}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[var(--muted)] hover:text-white hover:bg-white/5 transition-colors"
                  >
                    <Ellipsis className="h-4 w-4" />
                  </button>

                  {headerMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-40" onClick={() => setHeaderMenuOpen(false)} />
                      <div className="absolute right-0 top-full z-50 mt-1 w-44 rounded-xl border border-white/[0.08] bg-[#1a1a22]/95 p-1 shadow-2xl backdrop-blur-xl slide-down-enter">
                        <button
                          type="button"
                          onClick={() => { handleShare(); setHeaderMenuOpen(false); }}
                          disabled={!currentThreadId}
                          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-[var(--muted)] hover:bg-white/5 hover:text-white disabled:opacity-40 transition-colors"
                        >
                          <Share2 className="h-3.5 w-3.5" /> 分享链接
                        </button>
                        <button
                          type="button"
                          onClick={() => { exportThreadAsMarkdown(thread, messages); toast.success("已导出"); setHeaderMenuOpen(false); }}
                          disabled={messages.length === 0}
                          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-[var(--muted)] hover:bg-white/5 hover:text-white disabled:opacity-40 transition-colors"
                        >
                          <Download className="h-3.5 w-3.5" /> 导出 Markdown
                        </button>
                        <button
                          type="button"
                          onClick={() => { exportThreadAsJson(thread, messages); toast.success("已导出"); setHeaderMenuOpen(false); }}
                          disabled={messages.length === 0}
                          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-[var(--muted)] hover:bg-white/5 hover:text-white disabled:opacity-40 transition-colors"
                        >
                          <Download className="h-3.5 w-3.5" /> 导出 JSON
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </header>

            <div className="min-h-0 flex-1 conversation-enter">
              <MessageList
                messages={messages}
                streaming={streaming}
                threadId={currentThreadId}
                emptyState={undefined}
              />
            </div>

            <div className="sticky bottom-0 z-10 px-4 pb-3 pt-2 md:px-6 conversation-enter">
              <div className="mx-auto flex w-full max-w-5xl flex-col gap-2 bg-[linear-gradient(180deg,transparent_0%,rgba(9,9,11,0.8)_20%,rgba(9,9,11,0.96)_45%,rgba(9,9,11,1)_100%)] pt-3">
                <TodoPanel todos={todos} />
                {activeSkills.length > 0 ? (
                  <div className="inline-flex flex-wrap items-center gap-2 rounded-lg px-3 py-1.5 text-[11px] text-[var(--muted)] mx-auto">
                    <Sparkles className="h-3 w-3 text-[var(--accent)]" />
                    {activeSkills.map((skill) => (
                      <span key={skill} className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-[var(--foreground)]">
                        {skill}
                      </span>
                    ))}
                  </div>
                ) : null}
                <InputPanel
                  models={models}
                  settings={settings}
                  isBusy={isBusy}
                  isNewThread={false}
                  onSettingsChange={setSettings}
                  onSend={handleSend}
                  onStop={handleStop}
                />
              </div>
            </div>
          </>
        )}
      </section>

      <ArtifactDrawer open={artifactOpen} onClose={() => setArtifactOpen(false)} threadId={currentThreadId} artifacts={artifacts} />
    </>
  );
}
