"use client";

import {
  Brain,
  Loader2,
  type LucideIcon,
  Network,
  Paperclip,
  Send,
  Square,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import type { ChatMode, ModelInfo, ThreadUISettings } from "@/core/types";
import { cn } from "@/lib/utils";

const MODES: Array<{
  value: ChatMode;
  label: string;
  icon: LucideIcon;
  description: string;
  tooltip: string;
}> = [
  { value: "flash", label: "Flash", icon: Zap, description: "极速响应", tooltip: "最快速度，直接回复，不启用推理链和工具" },
  { value: "thinking", label: "Think", icon: Brain, description: "轻推理", tooltip: "启用深度思考推理链，适合需要分析的问题" },
  { value: "pro", label: "Pro", icon: Wand2, description: "推理 + 工具", tooltip: "推理 + 工具调用 + 计划，适合复杂任务" },
  { value: "ultra", label: "Parallel", icon: Network, description: "并行子任务", tooltip: "并行子任务编排，多个 subagent 同时工作，适合大型任务" },
];

const EFFORT_OPTIONS = [
  { value: "minimal", label: "Minimal" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
] as const;

export function InputPanel({
  models,
  settings,
  isBusy,
  isNewThread,
  onSettingsChange,
  onSend,
  onStop,
}: {
  models: ModelInfo[];
  settings: ThreadUISettings;
  isBusy: boolean;
  isNewThread: boolean;
  onSettingsChange: (next: ThreadUISettings) => void;
  onSend: (text: string, files?: File[]) => void;
  onStop: () => void;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const selectedModel = useMemo(
    () => models.find((model) => model.name === settings.modelName) ?? models[0],
    [models, settings.modelName],
  );
  const thinkingSupported = selectedModel?.supports_thinking ?? false;

  function submit() {
    if (isBusy) {
      onStop();
      return;
    }
    const message = text.trim();
    if (!message) return;
    onSend(message, files);
    setText("");
    setFiles([]);
    textareaRef.current?.focus();
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
    if (event.key === "Escape" && isBusy) {
      onStop();
    }
  }

  return (
    <div className={cn("relative w-full transition-all duration-300", isNewThread ? "max-w-4xl" : "max-w-5xl")}>
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl p-3 outline-none shadow-2xl flex flex-col gap-2 transition-colors focus-within:border-white/[0.15]">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => {
            const selected = Array.from(event.target.files ?? []);
            setFiles((current) => [...current, ...selected]);
            event.target.value = "";
          }}
        />
        <div className="flex flex-col">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            rows={isNewThread ? 3 : 2}
            placeholder="输入你的任务、问题或要协作推进的指令..."
            className={cn(
              "w-full resize-none bg-transparent px-1.5 py-1.5 text-[14px] leading-relaxed text-[var(--foreground)] outline-none placeholder:text-[var(--muted)]/40",
              isNewThread ? "min-h-[96px]" : "min-h-[64px]",
            )}
          />

          <div className="flex items-center justify-between gap-2 pt-1">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isBusy}
                className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[var(--muted)]/60 transition-colors hover:bg-white/5 hover:text-white disabled:opacity-50"
                title="添加附件"
              >
                <Paperclip className="h-3.5 w-3.5" />
              </button>

              <div className="h-4 w-px bg-white/[0.06] mx-1" />

              {MODES.map((mode) => {
                const Icon = mode.icon;
                const disabled = !thinkingSupported && mode.value !== "flash";
                return (
                  <button
                    key={mode.value}
                    type="button"
                    disabled={disabled}
                    onClick={() =>
                      onSettingsChange({
                        ...settings,
                        mode: mode.value,
                        reasoningEffort:
                          mode.value === "ultra"
                            ? "high"
                            : mode.value === "pro"
                              ? "medium"
                              : mode.value === "thinking"
                                ? "low"
                                : "minimal",
                      })
                    }
                    className={cn(
                      "group relative inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-medium transition-all duration-200",
                      settings.mode === mode.value
                        ? "bg-white/[0.08] text-white"
                        : "text-[var(--muted)]/60 hover:text-[var(--muted)]",
                      disabled && "cursor-not-allowed opacity-30",
                    )}
                  >
                    <Icon className={cn("h-3 w-3", settings.mode === mode.value ? "text-[var(--accent-secondary)]" : "")} />
                    <span>{mode.label}</span>
                    <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden -translate-x-1/2 whitespace-nowrap rounded-lg border border-white/10 bg-[#1c1c23] px-3 py-2 text-[11px] text-[var(--muted)] shadow-xl group-hover:block">
                      <strong className="block text-white mb-0.5">{mode.label}</strong>
                      {mode.tooltip}
                    </span>
                  </button>
                );
              })}

              <div className="h-4 w-px bg-white/[0.06] mx-1" />

              <select
                className="bg-transparent text-[11px] text-[var(--muted)]/70 outline-none hover:text-[var(--muted)] transition-colors cursor-pointer [&>option]:bg-[#1c1c23]"
                value={settings.modelName}
                onChange={(event) => onSettingsChange({ ...settings, modelName: event.target.value })}
              >
                {models.map((model) => (
                  <option key={model.name} value={model.name}>
                    {model.display_name}
                  </option>
                ))}
              </select>

              <select
                className="bg-transparent text-[11px] text-[var(--muted)]/70 outline-none hover:text-[var(--muted)] disabled:opacity-40 transition-colors cursor-pointer [&>option]:bg-[#1c1c23]"
                value={settings.reasoningEffort}
                disabled={!thinkingSupported}
                onChange={(event) =>
                  onSettingsChange({
                    ...settings,
                    reasoningEffort: event.target.value as ThreadUISettings["reasoningEffort"],
                  })
                }
              >
                {EFFORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={submit}
              disabled={!isBusy && !text.trim()}
              className={cn(
                "inline-flex h-7 w-7 items-center justify-center rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed",
                isBusy
                  ? "bg-amber-500/15 text-amber-400 hover:bg-amber-500/25"
                  : text.trim()
                  ? "bg-[var(--accent-secondary)] text-white shadow-sm hover:brightness-110"
                  : "bg-white/5 text-[var(--muted)]/40"
              )}
            >
              {isBusy ? <Square className="h-3 w-3 fill-current" /> : <Send className="h-3 w-3" />}
            </button>
          </div>
        </div>
      </div>

      {files.length > 0 && (
        <div className="absolute bottom-full left-0 mb-3 flex flex-wrap gap-2">
          {files.map((file, index) => (
            <span
              key={`${file.name}-${file.size}-${index}`}
              className="glass-badge inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs text-white shadow-md"
            >
              {file.name}
              <button
                type="button"
                className="text-white/70 transition hover:text-white"
                onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                aria-label={`移除 ${file.name}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
