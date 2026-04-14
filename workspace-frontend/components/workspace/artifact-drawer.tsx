"use client";

import { Copy, Download, ExternalLink, Eye, FileCode2, X } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fetchArtifactText, getArtifactUrl } from "@/core/api/client";
import { cn, getFileName, isImagePath, isMarkdownPath, isTextLikePath } from "@/lib/utils";

export function ArtifactDrawer({
  open,
  onClose,
  threadId,
  artifacts,
}: {
  open: boolean;
  onClose: () => void;
  threadId: string | null;
  artifacts: string[];
}) {
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(artifacts[0] ?? null);
  const [viewMode, setViewMode] = useState<"preview" | "code">("preview");

  const selectedPath = selectedArtifact ?? artifacts[0] ?? null;
  const isImage = selectedPath ? isImagePath(selectedPath) : false;
  const isMarkdown = selectedPath ? isMarkdownPath(selectedPath) : false;
  const isTextLike = selectedPath ? isTextLikePath(selectedPath) : false;

  const artifactQuery = useQuery({
    queryKey: ["artifact", threadId, selectedPath],
    queryFn: () => fetchArtifactText(threadId!, selectedPath!),
    enabled: open && Boolean(threadId && selectedPath && isTextLike),
  });

  if (!open || !threadId) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-[rgba(27,36,48,0.18)] backdrop-blur-sm">
      <button type="button" className="flex-1" aria-label="关闭产物面板" onClick={onClose} />
      <aside className="panel-strong flex h-full w-full max-w-5xl overflow-hidden rounded-none border-l border-[var(--line-soft)] p-0">
        <div className="flex w-[320px] flex-col border-r border-[var(--line-soft)] bg-white/40">
          <div className="flex items-center justify-between border-b border-[var(--line-soft)] px-4 py-4">
            <div>
              <div className="font-heading text-2xl">Artifacts</div>
              <div className="mt-1 text-xs text-[var(--muted)]">线程产物与输出文件</div>
            </div>
            <button type="button" className="glass-button rounded-full p-2 text-[var(--muted)] hover:text-[var(--foreground)]" onClick={onClose}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            {artifacts.map((path) => (
              <button
                key={path}
                type="button"
                className={cn(
                  "w-full rounded-[22px] border px-4 py-3 text-left transition",
                  selectedPath === path
                    ? "border-[var(--accent-secondary)] bg-[var(--accent-secondary-soft)]"
                    : "border-[var(--line-soft)] bg-white/58 hover:border-[var(--line-strong)] hover:bg-white/78",
                )}
                onClick={() => {
                  setSelectedArtifact(path);
                  setViewMode(isImagePath(path) ? "preview" : "code");
                }}
              >
                <div className="truncate text-sm font-semibold">{getFileName(path)}</div>
                <div className="mt-1 truncate text-xs text-[var(--muted)]">{path}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between gap-3 border-b border-[var(--line-soft)] px-5 py-4">
            <div className="min-w-0">
              <div className="truncate text-lg font-semibold">{selectedPath ? getFileName(selectedPath) : "未选择文件"}</div>
              {selectedPath && <div className="truncate text-xs text-[var(--muted)]">{selectedPath}</div>}
            </div>

            {selectedPath && (
              <div className="flex items-center gap-2">
                {isTextLike && (
                  <div className="glass-badge inline-flex rounded-full p-1">
                    <button
                      type="button"
                      onClick={() => setViewMode("preview")}
                      className={cn(
                        "rounded-full px-3 py-1.5 text-sm transition",
                        viewMode === "preview" ? "bg-[var(--accent)] text-white" : "text-[var(--muted)]",
                      )}
                    >
                      <Eye className="mr-2 inline h-4 w-4" />
                      预览
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewMode("code")}
                      className={cn(
                        "rounded-full px-3 py-1.5 text-sm transition",
                        viewMode === "code" ? "bg-[var(--accent)] text-white" : "text-[var(--muted)]",
                      )}
                    >
                      <FileCode2 className="mr-2 inline h-4 w-4" />
                      代码
                    </button>
                  </div>
                )}

                <a
                  href={getArtifactUrl(threadId, selectedPath)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="glass-button inline-flex h-10 w-10 items-center justify-center rounded-full text-[var(--muted)] hover:text-[var(--foreground)]"
                >
                  <ExternalLink className="h-4 w-4" />
                </a>
                <a
                  href={getArtifactUrl(threadId, selectedPath, { download: true })}
                  className="glass-button inline-flex h-10 w-10 items-center justify-center rounded-full text-[var(--muted)] hover:text-[var(--foreground)]"
                >
                  <Download className="h-4 w-4" />
                </a>
                {isTextLike && artifactQuery.data && (
                  <button
                    type="button"
                    onClick={() => navigator.clipboard.writeText(artifactQuery.data)}
                    className="glass-button inline-flex h-10 w-10 items-center justify-center rounded-full text-[var(--muted)] hover:text-[var(--foreground)]"
                  >
                    <Copy className="h-4 w-4" />
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-5">
            {!selectedPath && <div className="text-sm text-[var(--muted)]">暂无可用产物。</div>}

            {selectedPath && isImage && (
              <div className="flex h-full items-center justify-center rounded-[32px] border border-[var(--line-soft)] bg-white/56 p-6">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={getArtifactUrl(threadId, selectedPath)} alt={getFileName(selectedPath)} className="max-h-full rounded-2xl shadow-[0_24px_64px_rgba(38,51,66,0.16)]" />
              </div>
            )}

            {selectedPath && isTextLike && artifactQuery.isLoading && (
              <div className="rounded-[32px] border border-[var(--line-soft)] bg-white/56 p-6 text-sm text-[var(--muted)]">读取文件中...</div>
            )}

            {selectedPath && isTextLike && artifactQuery.data && viewMode === "preview" && (
              <div className="rounded-[32px] border border-[var(--line-soft)] bg-white/70 p-6">
                {isMarkdown ? (
                  <article className="prose max-w-none prose-pre:rounded-2xl">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifactQuery.data}</ReactMarkdown>
                  </article>
                ) : (
                  <pre className="whitespace-pre-wrap text-sm leading-7 text-[var(--foreground)]">{artifactQuery.data}</pre>
                )}
              </div>
            )}

            {selectedPath && isTextLike && artifactQuery.data && viewMode === "code" && (
              <pre className="overflow-auto rounded-[32px] border border-[var(--line-soft)] bg-[#eef2f8] p-6 font-mono text-sm leading-7 text-[var(--foreground)]">
                {artifactQuery.data}
              </pre>
            )}

            {selectedPath && !isImage && !isTextLike && (
              <div className="rounded-[32px] border border-dashed border-[var(--line-soft)] bg-white/56 p-6 text-sm leading-7 text-[var(--muted)]">
                当前类型不支持内嵌预览，请使用右上角“打开新窗口”或“下载”。
              </div>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
