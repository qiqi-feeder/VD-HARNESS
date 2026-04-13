import type {
  Agent,
  MCPConfigInfo,
  MCPDiscoveredTool,
  MCPServerInfo,
  MemorySnapshot,
  ModelInfo,
  ReasoningEffort,
  SSEEvent,
  SkillInfo,
  ThreadDetailResponse,
  ThreadSummary,
  ToolsConfig,
  UploadedFileInfo,
} from "@/core/types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? response.statusText);
  }

  return (await response.json()) as T;
}

export function getApiBaseUrl() {
  return API_BASE;
}

export function getLangGraphApiUrl() {
  return `${API_BASE}/api/langgraph`;
}

export async function fetchThreads(query = "") {
  const q = query.trim();
  const search = q ? `?q=${encodeURIComponent(q)}` : "";
  const data = await requestJson<{ threads: ThreadSummary[] }>(`/api/threads${search}`);
  return data.threads ?? [];
}

export async function fetchThread(threadId: string) {
  return requestJson<ThreadDetailResponse>(`/api/threads/${threadId}`);
}

export async function deleteThread(threadId: string) {
  await requestJson<{ success: boolean }>(`/api/threads/${threadId}`, { method: "DELETE" });
}

export async function renameThread(threadId: string, title: string) {
  const data = await requestJson<{ thread: ThreadSummary }>(`/api/threads/${threadId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
  return data.thread;
}

export async function fetchModels() {
  const data = await requestJson<{ models: ModelInfo[] }>("/api/models");
  return data.models ?? [];
}

export async function fetchMemory() {
  return requestJson<MemorySnapshot>("/api/memory");
}

export async function exportMemory() {
  return requestJson<MemorySnapshot>("/api/memory/export");
}

export async function importMemory(memory: MemorySnapshot, mode: "replace" | "merge") {
  return requestJson<{
    success: boolean;
    mode: "replace" | "merge";
    memory: MemorySnapshot;
    counts: { preferences: number; conversation_history: number; facts: number };
  }>("/api/memory/import", {
    method: "POST",
    body: JSON.stringify({ memory, mode }),
  });
}

export async function clearMemory() {
  return requestJson<{ success: boolean; message: string }>("/api/memory/clear", {
    method: "POST",
  });
}

export async function fetchSkills() {
  const data = await requestJson<{ skills: SkillInfo[] }>("/api/skills");
  return data.skills ?? [];
}

export async function updateSkillEnabled(skillName: string, enabled: boolean) {
  const data = await requestJson<{ skill: SkillInfo }>(`/api/skills/${encodeURIComponent(skillName)}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  return data.skill;
}

export async function installSkillFromArtifact(payload: { threadId: string; path: string; name?: string }) {
  return requestJson<{ success: boolean; name: string }>("/api/skills/install", {
    method: "POST",
    body: JSON.stringify({ thread_id: payload.threadId, path: payload.path, name: payload.name }),
  });
}

export async function fetchAgents() {
  const data = await requestJson<{ agents: Agent[] }>("/api/agents");
  return data.agents ?? [];
}

export async function checkAgentName(name: string) {
  return requestJson<{ name: string; valid: boolean; available: boolean; reason?: string }>(
    `/api/agents/check?name=${encodeURIComponent(name)}`,
  );
}

export async function createAgent(payload: Agent) {
  const data = await requestJson<{ agent: Agent }>("/api/agents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data.agent;
}

export async function fetchAgent(name: string) {
  const data = await requestJson<{ agent: Agent }>(`/api/agents/${encodeURIComponent(name)}`);
  return data.agent;
}

export async function updateAgent(name: string, payload: Partial<Agent>) {
  const data = await requestJson<{ agent: Agent }>(`/api/agents/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return data.agent;
}

export async function deleteAgent(name: string) {
  return requestJson<{ success: boolean }>(`/api/agents/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export async function uploadThreadFiles(threadId: string, files: File[]) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const response = await fetch(`${API_BASE}/api/threads/${threadId}/uploads`, {
    method: "POST",
    body: form,
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? response.statusText);
  }
  const data = (await response.json()) as { files: UploadedFileInfo[] };
  return data.files ?? [];
}

export async function fetchThreadUploads(threadId: string) {
  const data = await requestJson<{ files: UploadedFileInfo[] }>(`/api/threads/${threadId}/uploads/list`);
  return data.files ?? [];
}

export async function deleteThreadUpload(threadId: string, filename: string) {
  return requestJson<{ success: boolean }>(
    `/api/threads/${threadId}/uploads/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );
}

export async function fetchToolsConfig() {
  return requestJson<ToolsConfig>("/api/tools/config");
}

export async function updateToolsConfig(payload: {
  tool_groups?: Array<{ name: string; enabled: boolean }>;
  allow_host_bash?: boolean;
}) {
  return requestJson<ToolsConfig>("/api/tools/config", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function fetchMcpConfig() {
  return requestJson<MCPConfigInfo>("/api/mcp/config");
}

export async function updateMcpConfig(payload: { enabled?: boolean }) {
  return requestJson<MCPConfigInfo>("/api/mcp/config", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function createMcpServer(server: MCPServerInfo) {
  const data = await requestJson<{ server: MCPServerInfo }>("/api/mcp/servers", {
    method: "POST",
    body: JSON.stringify(server),
  });
  return data.server;
}

export async function updateMcpServer(serverName: string, server: MCPServerInfo) {
  const data = await requestJson<{ server: MCPServerInfo }>(`/api/mcp/servers/${encodeURIComponent(serverName)}`, {
    method: "PATCH",
    body: JSON.stringify(server),
  });
  return data.server;
}

export async function deleteMcpServer(serverName: string) {
  return requestJson<{ success: boolean }>(`/api/mcp/servers/${encodeURIComponent(serverName)}`, {
    method: "DELETE",
  });
}

export async function discoverMcpServer(serverName: string) {
  return requestJson<{
    server: MCPServerInfo;
    tools: MCPDiscoveredTool[];
    connected: boolean;
  }>(`/api/mcp/servers/${encodeURIComponent(serverName)}/discover`, {
    method: "POST",
  });
}

export function getArtifactUrl(threadId: string, path: string, options?: { download?: boolean }) {
  const normalizedPath = path.replace(/^\//, "");
  const encodedPath = normalizedPath
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const query = options?.download ? "?download=true" : "";
  return `${API_BASE}/api/threads/${threadId}/artifacts/${encodedPath}${query}`;
}

export async function fetchArtifactText(threadId: string, path: string) {
  const response = await fetch(getArtifactUrl(threadId, path), { cache: "no-store" });
  if (!response.ok) {
    throw new Error("无法读取文件内容");
  }
  return response.text();
}

export async function* streamChat(options: {
  message: string;
  threadId: string | null;
  model: string;
  mode: string;
  reasoningEffort: ReasoningEffort;
  signal?: AbortSignal;
}): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message: options.message,
      thread_id: options.threadId,
      model: options.model,
      mode: options.mode,
      reasoning_effort: options.reasoningEffort,
    }),
    signal: options.signal,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? response.statusText);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("流式响应不可用");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6);
      try {
        yield JSON.parse(payload) as SSEEvent;
      } catch {
        // Skip malformed frames.
      }
    }
  }
}
