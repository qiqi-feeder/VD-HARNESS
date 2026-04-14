import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatRelativeTime(value?: number | string | null) {
  if (!value) return "刚刚";
  const date = new Date(typeof value === "number" && value < 1e11 ? value * 1000 : value);
  if (Number.isNaN(date.getTime())) return "刚刚";

  const diff = Date.now() - date.getTime();
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diff < minute) return "刚刚";
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

export function formatTokenCount(value?: number) {
  if (!value) return "0";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(value);
}

export function downloadTextFile(filename: string, content: string, type = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function getFileName(path: string) {
  return path.split("/").filter(Boolean).at(-1) ?? path;
}

export function isImagePath(path: string) {
  return /\.(png|jpe?g|gif|webp|svg)$/i.test(path);
}

export function isMarkdownPath(path: string) {
  return /\.(md|markdown)$/i.test(path);
}

export function isTextLikePath(path: string) {
  return /\.(md|markdown|txt|json|py|ts|tsx|js|jsx|css|html|yaml|yml|log|xml|csv)$/i.test(path);
}
