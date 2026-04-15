export type ChatMode = "flash" | "thinking" | "pro" | "ultra";
export type ReasoningEffort = "minimal" | "low" | "medium" | "high";

export interface ModelInfo {
  name: string;
  display_name: string;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  supports_vision?: boolean;
}

export interface ThreadSummary {
  id: string;
  thread_id: string;
  title: string;
  status: string;
  preview: string;
  updated_at?: number | string | null;
  created_at?: number | string | null;
  model?: string;
  message_count?: number;
  metadata?: Record<string, unknown>;
}

export interface FileInMessage {
  filename: string;
  size: number;
  path: string;
  virtual_path?: string;
  status?: "uploading" | "uploaded";
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  status?: string;
  thinking?: string;
  files?: FileInMessage[];
}

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

export interface ThreadDetailResponse {
  thread: ThreadSummary;
  messages: ChatMessage[];
  thread_data?: Record<string, unknown> | null;
  artifacts: string[];
  active_skills: string[];
  pending_clarification?: Record<string, unknown> | null;
  todos: TodoItem[];
}

export interface Agent {
  name: string;
  description: string;
  model?: string | null;
  tool_groups?: string[] | null;
  soul?: string | null;
}

export interface UploadedFileInfo {
  filename: string;
  size: number;
  path: string;
  virtual_path: string;
  artifact_url: string;
  extension?: string;
  modified?: string;
}

export interface RunRecord {
  run_id: string;
  thread_id: string;
  assistant_id?: string;
  status: "pending" | "running" | "success" | "error" | "interrupted" | string;
  metadata?: Record<string, unknown>;
  kwargs?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface AgentThreadState {
  [key: string]: unknown;
  messages: Array<Record<string, unknown>>;
  artifacts?: string[];
  todos?: TodoItem[];
  active_skills?: string[];
  pending_clarification?: Record<string, unknown> | null;
  thread_data?: Record<string, unknown> | null;
  token_usage?: Record<string, unknown>;
  uploaded_files?: UploadedFileInfo[];
}

export interface ToolCallItem {
  tool: string;
  status: "running" | "done";
  taskId?: string;
  description?: string;
  subagentType?: string;
  output?: string;
}

export interface SubtaskItem {
  taskId: string;
  description: string;
  subagentType: string;
  status: "pending" | "running" | "completed" | "failed";
  output?: string;
  latestMessage?: string;
  prompt?: string;
  elapsedSeconds?: number;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  reasoning_tokens?: number;
}

export interface StreamingState {
  isStreaming: boolean;
  answerBuffer: string;
  thinkingBuffer: string;
  hasThinking: boolean;
  phaseLines: string[];
  toolCalls: ToolCallItem[];
  subtasks: SubtaskItem[];
  tokenUsage: TokenUsage | null;
}

export interface ThreadUISettings {
  modelName: string;
  mode: ChatMode;
  reasoningEffort: ReasoningEffort;
}

export interface MemorySnapshot {
  version?: string;
  storageBackend?: string;
  lastUpdated?: string;
  preferences?: Record<string, unknown>;
  conversation_history?: Array<Record<string, unknown>>;
  facts?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface SkillInfo {
  name: string;
  description: string;
  enabled: boolean;
  path?: string;
}

export interface ToolGroupInfo {
  name: string;
  enabled: boolean;
  tool_count: number;
}

export interface ToolInventoryItem {
  name: string;
  group?: string | null;
  configured: boolean;
  enabled: boolean;
  group_enabled: boolean;
  host_only: boolean;
}

export interface ToolsConfig {
  tool_groups: ToolGroupInfo[];
  tools: ToolInventoryItem[];
  runtime: {
    allow_host_bash: boolean;
  };
  mcp: {
    supported: boolean;
    enabled: boolean;
    servers: Array<Record<string, unknown>>;
    enabled_server_count: number;
    reason?: string;
  };
}

export interface MCPServerInfo {
  name: string;
  transport: "stdio" | "sse" | "streamable_http";
  command: string;
  args: string[];
  url: string;
  env: Record<string, string>;
  enabled: boolean;
  timeout_seconds: number;
}

export interface MCPConfigInfo {
  enabled: boolean;
  servers: MCPServerInfo[];
}

export interface MCPDiscoveredTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  server_name: string;
}

export type SSEEvent =
  | {
      type: "meta";
      thread_id: string;
      model?: string;
      mode?: ChatMode;
      reasoning_effort?: ReasoningEffort;
    }
  | { type: "content"; text: string }
  | { type: "thinking_start" }
  | { type: "thinking_delta"; text: string }
  | { type: "thinking_end" }
  | { type: "phase"; text: string; stage?: string; tool?: string }
  | {
      type: "tool_start";
      tool: string;
      task_id?: string;
      description?: string;
      subagent_type?: string;
    }
  | {
      type: "tool_end";
      tool: string;
      task_id?: string;
      status?: string;
      output?: string;
    }
  | {
      type: "token_usage";
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      reasoning_tokens?: number;
    }
  | {
      type: "task_started";
      task_id: string;
      description: string;
      subagent_type?: string;
      prompt?: string;
    }
  | {
      type: "task_running";
      task_id: string;
      message?: string;
      message_index?: number;
      total_messages?: number;
    }
  | { type: "task_completed"; task_id: string; result?: string; elapsed_seconds?: number }
  | { type: "task_failed"; task_id: string; error?: string }
  | { type: "task_timed_out"; task_id: string; error?: string }
  | { type: "task_cancelled"; task_id: string }
  | {
      type: "llm_retry";
      attempt: number;
      max_attempts: number;
      wait_ms: number;
      reason: string;
      message: string;
    }
  | { type: "error"; text: string }
  | { type: "done" };
