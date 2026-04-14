"use client";

import {
  ArrowDown,
  Bot,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  Copy,
  Cpu,
  File as FileIcon,
  GitBranch,
  Loader2,
  Network,
  Sparkles,
  Wrench,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github.min.css";

import type { ChatMessage, FileInMessage, StreamingState, SubtaskItem, TokenUsage, ToolCallItem } from "@/core/types";
import { getArtifactUrl } from "@/core/api/client";
import { cn, formatTokenCount, getFileName } from "@/lib/utils";

const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"];
const FILE_TYPE_MAP: Record<string, string> = {
  json: "JSON",
  csv: "CSV",
  txt: "TXT",
  md: "Markdown",
  py: "Python",
  js: "JavaScript",
  ts: "TypeScript",
  html: "HTML",
  css: "CSS",
  pdf: "PDF",
  png: "PNG",
  jpg: "JPG",
  jpeg: "JPEG",
  gif: "GIF",
  svg: "SVG",
  zip: "ZIP",
  xlsx: "Excel",
  docx: "Word",
};

type ChatTurn = {
  id: string;
  user?: ChatMessage;
  assistants: ChatMessage[];
};

function getFileExt(filename: string) {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

function getFileTypeLabel(filename: string) {
  const extension = getFileExt(filename);
  return FILE_TYPE_MAP[extension] ?? (extension.toUpperCase() || "FILE");
}

function isImageFile(filename: string) {
  return IMAGE_EXTENSIONS.includes(getFileExt(filename));
}

function formatBytes(bytes: number) {
  if (bytes === 0) return "—";
  const kb = bytes / 1024;
  return kb < 1024 ? `${kb.toFixed(1)} KB` : `${(kb / 1024).toFixed(1)} MB`;
}

function groupMessages(messages: ChatMessage[]) {
  const turns: ChatTurn[] = [];
  let current: ChatTurn | null = null;

  for (const message of messages) {
    if (message.role === "user") {
      if (current) turns.push(current);
      current = { id: message.id, user: message, assistants: [] };
      continue;
    }

    if (!current) {
      current = { id: message.id, assistants: [message] };
      continue;
    }

    current.assistants.push(message);
  }

  if (current) turns.push(current);
  return turns;
}

function CodeBlockCopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-xl border border-[var(--line-soft)] bg-white/80 text-[var(--muted)] opacity-0 transition hover:border-[var(--line-strong)] hover:text-[var(--foreground)] group-hover/code:opacity-100"
      aria-label="复制代码"
    >
      {copied ? <Check className="h-4 w-4 text-[var(--accent-secondary)]" /> : <Copy className="h-4 w-4" />}
    </button>
  );
}

function MessageCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="glass-button inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs text-[var(--muted)] hover:text-[var(--foreground)]"
      aria-label="复制回复"
    >
      {copied ? (
        <>
          <Check className="h-3.5 w-3.5 text-[var(--accent-secondary)]" /> 已复制
        </>
      ) : (
        <>
          <Copy className="h-3.5 w-3.5" /> 复制
        </>
      )}
    </button>
  );
}

function extractTextFromChildren(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(extractTextFromChildren).join("");
  if (children && typeof children === "object" && "props" in children) {
    return extractTextFromChildren((children as { props: { children?: React.ReactNode } }).props.children);
  }
  return "";
}

function ArtifactAwareMarkdown({
  content,
  threadId,
}: {
  content: string;
  threadId: string | null;
}) {
  const processed = content.replace(
    /(?<!\[.*?\]\()(?<!\()(\/?mnt\/user-data\/[^\s)]+)/g,
    (match) => `[文件 ${getFileName(match)}](${match})`,
  );

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, rehypeHighlight]}
      components={{
        a: ({ href, children }) => {
          if (!href || !threadId) {
            return <a href={href}>{children}</a>;
          }

          const artifactPath = href.startsWith("/mnt/") ? href.slice(1) : href.startsWith("mnt/") ? href : null;
          if (!artifactPath) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--accent-tertiary)] underline decoration-[var(--line-strong)] underline-offset-4"
              >
                {children}
              </a>
            );
          }

          return (
            <a
              href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/threads/${threadId}/artifacts/${artifactPath}?download=true`}
              className="glass-button inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm text-[var(--foreground)]"
            >
              {children}
            </a>
          );
        },
        pre: ({ children, ...props }) => {
          const code = extractTextFromChildren(children);
          return (
            <div className="group/code relative">
              <pre {...props}>{children}</pre>
              <CodeBlockCopyButton code={code} />
            </div>
          );
        },
        img: ({ src, alt, ...props }) => {
          if (!src || typeof src !== "string") return null;
          const resolvedSrc = src.startsWith("/mnt/") && threadId ? getArtifactUrl(threadId, src.slice(1)) : src;

          return (
            <a href={resolvedSrc} target="_blank" rel="noopener noreferrer">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={resolvedSrc}
                alt={alt ?? ""}
                className="max-w-[90%] rounded-2xl border border-[var(--line-soft)] shadow-[0_18px_44px_rgba(38,51,66,0.08)]"
                {...props}
              />
            </a>
          );
        },
      }}
    >
      {processed}
    </ReactMarkdown>
  );
}

function RichFileCard({ file, threadId }: { file: FileInMessage; threadId: string | null }) {
  const isUploading = file.status === "uploading";
  const isImage = isImageFile(file.filename);

  if (isUploading) {
    return (
      <div className="surface-subtle flex min-w-[132px] max-w-[220px] flex-col gap-1 rounded-[22px] p-3 opacity-70">
        <div className="flex items-start gap-2">
          <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-[var(--muted)]" />
          <span className="truncate text-sm font-medium" title={file.filename}>
            {file.filename}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="glass-badge rounded px-1.5 py-0.5 text-[10px] text-[var(--muted)]">{getFileTypeLabel(file.filename)}</span>
          <span className="text-[10px] text-[var(--muted)]">上传中...</span>
        </div>
      </div>
    );
  }

  if (!file.path && !file.virtual_path) return null;

  const fileUrl = threadId && file.path
    ? getArtifactUrl(threadId, file.path.startsWith("/mnt/") ? file.path.slice(1) : file.path)
    : undefined;

  if (isImage && fileUrl) {
    return (
      <a
        href={fileUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="group block overflow-hidden rounded-[24px] border border-[var(--line-soft)] bg-white/70"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={fileUrl} alt={file.filename} className="h-32 w-auto max-w-60 object-cover transition group-hover:scale-[1.03]" />
      </a>
    );
  }

  return (
    <div className="surface-subtle flex min-w-[132px] max-w-[220px] flex-col gap-1 rounded-[22px] p-3">
      <div className="flex items-start gap-2">
        <FileIcon className="mt-0.5 h-4 w-4 shrink-0 text-[var(--muted)]" />
        <span className="truncate text-sm font-medium" title={file.filename}>
          {file.filename}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="glass-badge rounded px-1.5 py-0.5 text-[10px] text-[var(--muted)]">{getFileTypeLabel(file.filename)}</span>
        <span className="text-[10px] text-[var(--muted)]">{formatBytes(file.size)}</span>
      </div>
    </div>
  );
}

export function MessageList({
  messages,
  streaming,
  threadId,
  emptyState,
}: {
  messages: ChatMessage[];
  streaming: StreamingState;
  threadId: string | null;
  emptyState?: React.ReactNode;
}) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [stickToBottom, setStickToBottom] = useState(true);
  const turns = useMemo(() => groupMessages(messages), [messages]);
  const hasContent = turns.length > 0 || streaming.isStreaming;

  useEffect(() => {
    if (!stickToBottom) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, stickToBottom, streaming.answerBuffer, streaming.thinkingBuffer, streaming.subtasks, streaming.toolCalls]);

  const handleScroll = useCallback(() => {
    const element = scrollerRef.current;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    setStickToBottom(distance < 120);
  }, []);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div ref={scrollerRef} onScroll={handleScroll} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 py-6 md:px-6 md:pb-8">
          {!hasContent && emptyState}
          {turns.map((turn, index) => (
            <TurnGroup
              key={turn.id}
              turn={turn}
              threadId={threadId}
              streaming={streaming.isStreaming && index === turns.length - 1 ? streaming : null}
            />
          ))}
          {streaming.isStreaming && turns.length === 0 && <StreamingBubble streaming={streaming} threadId={threadId} />}
          <div ref={bottomRef} />
        </div>
      </div>

      {hasContent && !stickToBottom && (
        <div className="pointer-events-none absolute bottom-6 right-6">
          <button
            type="button"
            className="pointer-events-auto inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-[var(--foreground)] shadow-lg backdrop-blur-sm hover:bg-white/15 transition-colors"
            onClick={() => bottomRef.current?.scrollIntoView({ behavior: "smooth" })}
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}

function TurnGroup({
  turn,
  threadId,
  streaming,
}: {
  turn: ChatTurn;
  threadId: string | null;
  streaming: StreamingState | null;
}) {
  const assistantsToRender = turn.assistants.filter(
    (msg, idx, arr) => 
      !!msg.content || !!msg.thinking || idx === arr.length - 1
  );

  return (
    <section className="space-y-4">
      {turn.user ? <UserMessageCard message={turn.user} threadId={threadId} /> : null}
      {assistantsToRender.length > 0 ? (
        assistantsToRender.map((message, index) => (
          <AssistantMessageCard key={`${message.id}-${index}`} message={message} threadId={threadId} />
        ))
      ) : streaming ? (
        <StreamingBubble streaming={streaming} threadId={threadId} />
      ) : null}
    </section>
  );
}

function UserMessageCard({ message, threadId }: { message: ChatMessage; threadId: string | null }) {
  return (
    <article className="flex justify-end rise-in">
      <div className="max-w-[85%] space-y-2">
        {message.files && message.files.length > 0 && (
          <div className="flex flex-wrap justify-end gap-2">
            {message.files.map((file, index) => (
              <RichFileCard key={`${file.filename}-${index}`} file={file} threadId={threadId} />
            ))}
          </div>
        )}
        <div className="rounded-2xl bg-white/[0.08] px-4 py-3 text-[14px] leading-relaxed text-white/90">
          <div className="whitespace-pre-wrap">{message.content}</div>
        </div>
      </div>
    </article>
  );
}

function AssistantMessageCard({ message, threadId }: { message: ChatMessage; threadId: string | null }) {
  const [reasoningOpen, setReasoningOpen] = useState(false);

  return (
    <article className="group/msg flex gap-2.5 rise-in">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-secondary)]/15 text-[var(--accent-secondary)] mt-1">
        <Bot className="h-3.5 w-3.5" />
      </div>

      <div className="w-full max-w-[90%] space-y-2">
        {message.content ? (
          <div className="overflow-hidden">
            <div className="flex items-center justify-between gap-3 mb-1">
              <div className="text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]/50 font-medium">Assistant</div>
              <div className="opacity-0 group-hover/msg:opacity-100 transition-opacity">
                <MessageCopyButton text={message.content} />
              </div>
            </div>
            <div className="prose max-w-none text-[14px] leading-7">
              <ArtifactAwareMarkdown content={message.content} threadId={threadId} />
            </div>
          </div>
        ) : !message.thinking ? (
          <div className="text-[var(--muted)]/40 text-[13px] flex items-center gap-2">
            <div className="h-1 w-1 rounded-full bg-[var(--muted)]/30" />
            生成内容为空
          </div>
        ) : null}

        {message.thinking ? (
          <div className="overflow-hidden rounded-xl border border-white/[0.04] transition-all duration-300">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-[12px] text-[var(--muted)]/60 hover:text-[var(--muted)] transition-colors duration-200"
              onClick={() => setReasoningOpen((value) => !value)}
            >
              <Brain className="h-3 w-3" />
              <span className="font-medium">思考过程</span>
              <ChevronDown className={cn("ml-auto h-3 w-3 opacity-40 transition-transform duration-300", reasoningOpen && "rotate-180")} />
            </button>
            {reasoningOpen ? (
              <div className="slide-down-enter border-t border-white/[0.04] px-3 py-3 text-[12px] leading-relaxed text-[var(--muted)]/60 whitespace-pre-wrap">
                {message.thinking}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function StreamingBubble({ streaming, threadId }: { streaming: StreamingState; threadId: string | null }) {
  const statusText = useMemo(() => {
    if (streaming.subtasks.length > 0) {
      const running = streaming.subtasks.filter((item) => item.status === "running").length;
      return running > 0 ? `子任务执行中 · ${running} 个运行中` : "子任务已完成，准备汇聚";
    }
    if (streaming.toolCalls.some((item) => item.status === "running")) return "正在调用工具";
    if (streaming.hasThinking && !streaming.answerBuffer) return "正在组织推理";
    if (streaming.answerBuffer) return "正在生成回复";
    return "正在思考";
  }, [streaming]);

  return (
    <article className="flex gap-2.5 rise-in">
      <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-secondary)]/15 text-[var(--accent-secondary)] mt-1">
        <Bot className="h-3.5 w-3.5" />
        <span className="absolute inset-0 rounded-lg animate-pulse-ring text-[var(--accent-secondary)]/30" />
      </div>

      <div className="w-full max-w-[90%] space-y-2">
        <ExecutionStepsBlock streaming={streaming} />

        {streaming.answerBuffer ? (
          <div className="overflow-hidden fade-in-up">
            <div className="mb-1 text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]/50 font-medium">Assistant</div>
            <div className="prose max-w-none text-[14px] leading-7">
              <ArtifactAwareMarkdown content={streaming.answerBuffer} threadId={threadId} />
            </div>
            <span className="ml-1 inline-block h-4 w-[2px] animate-typing-cursor rounded-full bg-[var(--accent-secondary)] align-middle" />
          </div>
        ) : (
          /* Skeleton placeholder while waiting */
          !streaming.hasThinking && streaming.toolCalls.length === 0 && streaming.subtasks.length === 0 && (
            <div className="space-y-2.5 py-2">
              <div className="h-3 w-3/4 rounded-full bg-white/[0.04] animate-skeleton" />
              <div className="h-3 w-1/2 rounded-full bg-white/[0.04] animate-skeleton" style={{ animationDelay: "0.15s" }} />
              <div className="h-3 w-2/3 rounded-full bg-white/[0.04] animate-skeleton" style={{ animationDelay: "0.3s" }} />
            </div>
          )
        )}

        {/* Status indicator */}
        <div className="flex items-center gap-2 text-[var(--muted)]/60 px-0.5">
          <span className="inline-flex items-center gap-1">
            <span className="h-1 w-1 animate-bouncing rounded-full bg-[var(--accent-secondary)]/60" />
            <span className="h-1 w-1 animate-bouncing rounded-full bg-[var(--accent-secondary)]/60" style={{ animationDelay: "0.2s" }} />
            <span className="h-1 w-1 animate-bouncing rounded-full bg-[var(--accent-secondary)]/60" style={{ animationDelay: "0.4s" }} />
          </span>
          <span className="text-[11px] font-medium tracking-wide shimmer-text">{statusText}</span>
        </div>
      </div>
    </article>
  );
}

function ExecutionStepsBlock({ streaming }: { streaming: StreamingState }) {
  const [isOpen, setIsOpen] = useState(true);
  
  const content = streaming.thinkingBuffer || streaming.phaseLines.join("\n");
  const hasThinking = !!content;
  const tools = streaming.toolCalls.filter((t) => t.tool !== "task");
  const subtasks = streaming.subtasks;
  const stepCount = (hasThinking ? 1 : 0) + tools.length + subtasks.length;
  const runningCount = tools.filter((t) => t.status === "running").length
    + subtasks.filter((t) => t.status === "running").length
    + (hasThinking && !streaming.answerBuffer ? 1 : 0);

  if (stepCount === 0) return null;

  return (
    <div className="overflow-hidden rounded-[20px] border border-white/[0.06] w-full max-w-3xl transition-all duration-300 text-[13px] bg-white/[0.02] backdrop-blur-sm">
      {/* Header bar with step count */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full cursor-pointer items-center gap-2.5 px-4 py-3 hover:bg-white/[0.02] select-none transition-colors duration-200 group/toggle"
      >
        <Cpu className="h-3.5 w-3.5 text-[var(--accent-secondary)] opacity-70" />
        <span className="font-medium text-[12px] text-[var(--muted)] group-hover/toggle:text-white transition-colors">
          {isOpen ? "执行步骤" : "展开步骤"}
        </span>
        <span className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-white/[0.06] px-1.5 text-[10px] font-semibold text-[var(--muted)]">
          {stepCount}
        </span>
        {runningCount > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-[var(--accent-secondary)]">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>{runningCount} 运行中</span>
          </span>
        )}
        <ChevronDown className={cn(
          "ml-auto h-3.5 w-3.5 text-[var(--muted)] opacity-40 transition-transform duration-300",
          isOpen && "rotate-180"
        )} />
      </button>

      {/* Shimmer progress bar when running */}
      {runningCount > 0 && (
        <div className="h-[1px] w-full bg-white/[0.04] overflow-hidden">
          <div className="h-full w-1/2 bg-gradient-to-r from-transparent via-[var(--accent-secondary)]/40 to-transparent" style={{ animation: "progress-sweep 2s ease-in-out infinite" }} />
        </div>
      )}

      {isOpen && (
        <div className="slide-down-enter border-t border-white/[0.04] px-4 py-4 space-y-1 stagger-children">
          {/* Thinking step */}
          {hasThinking && (
            <div className="timeline-step fade-in-up pb-4">
              <div className={cn("timeline-dot", streaming.answerBuffer ? "done" : "active")} />
              <div className="flex items-center gap-2 text-[13px] mb-2">
                <Brain className="h-3.5 w-3.5 text-[var(--accent-secondary)]" />
                <span className="font-semibold text-white/90">推理分析</span>
                {!streaming.answerBuffer && (
                  <Loader2 className="h-3 w-3 animate-spin text-[var(--accent-secondary)] ml-1" />
                )}
              </div>
              <div className="rounded-xl bg-white/[0.03] border border-white/[0.04] px-3 py-2.5 text-[12px] leading-relaxed text-[var(--muted)] whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                {content}
              </div>
            </div>
          )}
          
          {/* Tool call steps */}
          {tools.map((item, index) => (
            <div key={`${item.tool}-${index}`} className="timeline-step fade-in-up pb-4">
              <div className={cn("timeline-dot", item.status === "running" ? "active" : "done")} />
              <div className="flex items-center gap-2 text-[13px]">
                <ToolIcon tool={item.tool} />
                <span className="font-semibold text-white/90">{formatToolName(item.tool)}</span>
                {item.status === "running" && (
                  <Loader2 className="h-3 w-3 animate-spin text-[var(--accent-secondary)] ml-1" />
                )}
                {item.status === "done" && (
                  <CheckCircle2 className="h-3 w-3 text-green-400/70 ml-1" />
                )}
              </div>
              {item.description ? (
                <div className={cn(
                  "mt-2 rounded-lg border px-2.5 py-1.5 text-[11px] font-mono text-[var(--muted)] max-w-full truncate",
                  item.status === "running"
                    ? "border-[var(--accent-secondary)]/15 bg-[var(--accent-secondary)]/[0.04] animate-shimmer"
                    : "border-white/[0.04] bg-white/[0.02]"
                )}>
                  {item.description}
                </div>
              ) : null}
            </div>
          ))}

          {/* Subtask steps */}
          {subtasks.map((task) => (
            <div key={task.taskId} className="timeline-step fade-in-up pb-4">
              <div className={cn(
                "timeline-dot",
                task.status === "running" ? "active" : task.status === "failed" ? "failed" : "done"
              )} />
              <div className="flex items-center gap-2 text-[13px] flex-wrap">
                <GitBranch className="h-3.5 w-3.5 text-[var(--accent-tertiary)]" />
                <span className="font-semibold text-white/90">{task.description}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-[var(--accent-secondary)]/10 px-2 py-0.5 text-[10px] uppercase font-bold text-[var(--accent-secondary)] tracking-wider">
                  {task.subagentType}
                </span>
                {task.status === "running" && (
                  <Loader2 className="h-3 w-3 animate-spin text-[var(--accent-secondary)]" />
                )}
                {task.status === "failed" && (
                  <XCircle className="h-3 w-3 text-[var(--danger)]" />
                )}
                {(task.status === "completed") && (
                  <CheckCircle2 className="h-3 w-3 text-green-400/70" />
                )}
              </div>
              {(task.latestMessage || task.output) ? (
                <div className={cn(
                  "mt-2 rounded-xl border px-3 py-2 text-[11px] leading-relaxed text-[var(--muted)] whitespace-pre-wrap font-mono max-h-32 overflow-y-auto",
                  task.status === "running"
                    ? "border-[var(--accent-secondary)]/10 bg-[var(--accent-secondary)]/[0.03]"
                    : "border-white/[0.04] bg-black/20"
                )}>
                  {task.output || task.latestMessage}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ToolIcon({ tool }: { tool: string }) {
  const name = tool.toLowerCase();
  if (name.includes("search") || name.includes("web")) return <Network className="h-3.5 w-3.5 text-[var(--accent-secondary)]" />;
  if (name.includes("code") || name.includes("bash") || name.includes("shell")) return <Cpu className="h-3.5 w-3.5 text-green-400/80" />;
  if (name.includes("file") || name.includes("read") || name.includes("write")) return <FileIcon className="h-3.5 w-3.5 text-amber-400/70" />;
  if (name.includes("skill")) return <Sparkles className="h-3.5 w-3.5 text-[var(--accent-tertiary)]" />;
  return <Wrench className="h-3.5 w-3.5 text-[var(--accent-secondary)]" />;
}

function formatToolName(tool: string) {
  return tool.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
}

function TokenUsageStrip({ usage }: { usage: TokenUsage }) {
  return (
    <div className="flex flex-wrap gap-2 text-xs text-[var(--muted)]">
      <Badge>输入 {formatTokenCount(usage.input_tokens)}</Badge>
      <Badge>输出 {formatTokenCount(usage.output_tokens)}</Badge>
      <Badge>总计 {formatTokenCount(usage.total_tokens)}</Badge>
      {(usage.reasoning_tokens ?? 0) > 0 ? <Badge>推理 {formatTokenCount(usage.reasoning_tokens)}</Badge> : null}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="glass-badge rounded-full px-3 py-1.5">{children}</span>;
}
