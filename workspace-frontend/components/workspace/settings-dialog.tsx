"use client";

import { Bot, Brain, Info, Palette, Plus, Sparkles, Trash2, Wrench } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent, type ReactNode } from "react";

import {
  clearMemory,
  createAgent,
  createMcpServer,
  deleteAgent,
  deleteMcpServer,
  discoverMcpServer,
  exportMemory,
  fetchAgents,
  fetchMemory,
  fetchMcpConfig,
  fetchSkills,
  fetchToolsConfig,
  getApiBaseUrl,
  importMemory,
  updateAgent,
  updateMcpConfig,
  updateMcpServer,
  updateSkillEnabled,
  updateToolsConfig,
} from "@/core/api/client";
import type { Agent, MCPServerInfo, MemorySnapshot } from "@/core/types";
import { usePersistentFlag } from "@/core/settings/hooks";

const SECTIONS = [
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "agents", label: "Agents", icon: Bot },
  { id: "skills", label: "Skills", icon: Sparkles },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "about", label: "About", icon: Info },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];
type MemoryImportMode = "replace" | "merge";

function splitShellLikeArgs(input: string) {
  return input.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g)?.map((part) => part.replace(/^["']|["']$/g, "")) ?? [];
}

export function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [activeSection, setActiveSection] = useState<SectionId>("appearance");
  const [notificationsEnabled, setNotificationsEnabled] = usePersistentFlag("vdharness.notifications", true);
  const [reducedMotion, setReducedMotion] = usePersistentFlag("vdharness.reduced-motion", false);
  const [memoryStatus, setMemoryStatus] = useState<string | null>(null);
  const [memoryImportMode, setMemoryImportMode] = useState<MemoryImportMode>("merge");
  const [skillsStatus, setSkillsStatus] = useState<string | null>(null);
  const [agentsStatus, setAgentsStatus] = useState<string | null>(null);
  const [selectedAgentName, setSelectedAgentName] = useState("");
  const [newAgentName, setNewAgentName] = useState("");
  const [agentDescription, setAgentDescription] = useState("");
  const [agentModel, setAgentModel] = useState("");
  const [agentSoul, setAgentSoul] = useState("");
  const [toolsStatus, setToolsStatus] = useState<string | null>(null);
  const [mcpStatus, setMcpStatus] = useState<string | null>(null);
  const [newMcpName, setNewMcpName] = useState("");
  const [newMcpCommand, setNewMcpCommand] = useState("");
  const [newMcpArgs, setNewMcpArgs] = useState("");
  const memoryInputRef = useRef<HTMLInputElement | null>(null);
  const queryClient = useQueryClient();

  const memoryQuery = useQuery({
    queryKey: ["memory"],
    queryFn: fetchMemory,
    enabled: open && activeSection === "memory",
  });
  const skillsQuery = useQuery({
    queryKey: ["skills"],
    queryFn: fetchSkills,
    enabled: open && activeSection === "skills",
  });
  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: fetchAgents,
    enabled: open && activeSection === "agents",
  });
  const toolsQuery = useQuery({
    queryKey: ["tools-config"],
    queryFn: fetchToolsConfig,
    enabled: open && activeSection === "tools",
  });
  const mcpQuery = useQuery({
    queryKey: ["mcp-config"],
    queryFn: fetchMcpConfig,
    enabled: open && activeSection === "tools",
  });

  const clearMemoryMutation = useMutation({
    mutationFn: clearMemory,
    onSuccess: async () => {
      setMemoryStatus("Memory 已清空。");
      await queryClient.invalidateQueries({ queryKey: ["memory"] });
    },
    onError: (error: Error) => setMemoryStatus(error.message),
  });

  const exportMemoryMutation = useMutation({
    mutationFn: exportMemory,
    onSuccess: (snapshot) => {
      const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "vdharness-memory-export.json";
      link.click();
      URL.revokeObjectURL(url);
      setMemoryStatus("Memory 已导出。");
    },
    onError: (error: Error) => setMemoryStatus(error.message),
  });

  const importMemoryMutation = useMutation({
    mutationFn: ({ memory, mode }: { memory: MemorySnapshot; mode: MemoryImportMode }) => importMemory(memory, mode),
    onSuccess: async (result) => {
      setMemoryStatus(
        `导入完成：${result.counts.preferences} 个偏好，${result.counts.conversation_history} 条历史，${result.counts.facts} 条事实。`,
      );
      await queryClient.invalidateQueries({ queryKey: ["memory"] });
    },
    onError: (error: Error) => setMemoryStatus(error.message),
  });

  const updateSkillMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) => updateSkillEnabled(name, enabled),
    onSuccess: async (skill) => {
      setSkillsStatus(`技能 ${skill.name} 已${skill.enabled ? "启用" : "停用"}。`);
      await queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
    onError: (error: Error) => setSkillsStatus(error.message),
  });

  const createAgentMutation = useMutation({
    mutationFn: createAgent,
    onSuccess: async (agent) => {
      setAgentsStatus(`Agent ${agent.name} 已创建。`);
      setSelectedAgentName(agent.name);
      setNewAgentName("");
      setAgentDescription(agent.description);
      setAgentModel(agent.model ?? "");
      setAgentSoul(agent.soul ?? "");
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error: Error) => setAgentsStatus(error.message),
  });

  const updateAgentMutation = useMutation({
    mutationFn: ({ name, agent }: { name: string; agent: Partial<Agent> }) => updateAgent(name, agent),
    onSuccess: async (agent) => {
      setAgentsStatus(`Agent ${agent.name} 已保存。`);
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error: Error) => setAgentsStatus(error.message),
  });

  const deleteAgentMutation = useMutation({
    mutationFn: deleteAgent,
    onSuccess: async () => {
      setAgentsStatus("Agent 已删除。");
      setSelectedAgentName("");
      setAgentDescription("");
      setAgentModel("");
      setAgentSoul("");
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error: Error) => setAgentsStatus(error.message),
  });

  const updateToolsMutation = useMutation({
    mutationFn: updateToolsConfig,
    onSuccess: async () => {
      setToolsStatus("工具运行时配置已更新，新会话会立即生效。");
      await queryClient.invalidateQueries({ queryKey: ["tools-config"] });
    },
    onError: (error: Error) => setToolsStatus(error.message),
  });

  const updateMcpConfigMutation = useMutation({
    mutationFn: updateMcpConfig,
    onSuccess: async () => {
      setMcpStatus("MCP 总开关已更新。");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["mcp-config"] }),
        queryClient.invalidateQueries({ queryKey: ["tools-config"] }),
      ]);
    },
    onError: (error: Error) => setMcpStatus(error.message),
  });

  const createMcpServerMutation = useMutation({
    mutationFn: createMcpServer,
    onSuccess: async (server) => {
      setMcpStatus(`MCP server ${server.name} 已创建。`);
      setNewMcpName("");
      setNewMcpCommand("");
      setNewMcpArgs("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["mcp-config"] }),
        queryClient.invalidateQueries({ queryKey: ["tools-config"] }),
      ]);
    },
    onError: (error: Error) => setMcpStatus(error.message),
  });

  const updateMcpServerMutation = useMutation({
    mutationFn: ({ name, server }: { name: string; server: MCPServerInfo }) => updateMcpServer(name, server),
    onSuccess: async (server) => {
      setMcpStatus(`MCP server ${server.name} 已更新。`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["mcp-config"] }),
        queryClient.invalidateQueries({ queryKey: ["tools-config"] }),
      ]);
    },
    onError: (error: Error) => setMcpStatus(error.message),
  });

  const deleteMcpServerMutation = useMutation({
    mutationFn: deleteMcpServer,
    onSuccess: async () => {
      setMcpStatus("MCP server 已删除。");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["mcp-config"] }),
        queryClient.invalidateQueries({ queryKey: ["tools-config"] }),
      ]);
    },
    onError: (error: Error) => setMcpStatus(error.message),
  });

  const discoverMcpServerMutation = useMutation({
    mutationFn: discoverMcpServer,
    onSuccess: (result) => {
      setMcpStatus(`发现 ${result.tools.length} 个 MCP 工具：${result.tools.map((tool) => tool.name).join(", ") || "无"}`);
    },
    onError: (error: Error) => setMcpStatus(error.message),
  });

  if (!open) return null;

  async function handleMemoryFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as MemorySnapshot;
      importMemoryMutation.mutate({ memory: parsed, mode: memoryImportMode });
    } catch {
      setMemoryStatus("导入失败：文件不是有效的 JSON。");
    }
  }

  function beginMemoryImport(mode: MemoryImportMode) {
    setMemoryImportMode(mode);
    memoryInputRef.current?.click();
  }

  function createNewMcpServer() {
    const name = newMcpName.trim();
    const command = newMcpCommand.trim();
    if (!name || !command) {
      setMcpStatus("请输入 MCP server 名称和 stdio 命令。");
      return;
    }
    createMcpServerMutation.mutate({
      name,
      transport: "stdio",
      command,
      args: splitShellLikeArgs(newMcpArgs),
      url: "",
      env: {},
      enabled: true,
      timeout_seconds: 10,
    });
  }

  function selectAgent(agent: Agent) {
    setSelectedAgentName(agent.name);
    setNewAgentName("");
    setAgentDescription(agent.description);
    setAgentModel(agent.model ?? "");
    setAgentSoul(agent.soul ?? "");
  }

  function createNewAgent() {
    const name = newAgentName.trim().toLowerCase().replace(/\s+/g, "-");
    if (!name) {
      setAgentsStatus("请输入 Agent 名称。");
      return;
    }
    createAgentMutation.mutate({
      name,
      description: agentDescription,
      model: agentModel.trim() || null,
      tool_groups: [],
      soul: agentSoul || `# ${name}\n\n## 定位\n请补充这个 Agent 的目标、边界和交付风格。`,
    });
  }

  function saveSelectedAgent() {
    if (!selectedAgentName) {
      setAgentsStatus("请先选择一个 Agent。");
      return;
    }
    updateAgentMutation.mutate({
      name: selectedAgentName,
      agent: {
        description: agentDescription,
        model: agentModel.trim() || null,
        soul: agentSoul,
      },
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 px-4 py-10 backdrop-blur-sm">
      <div className="panel flex h-[80vh] w-full max-w-6xl overflow-hidden p-0">
        <aside className="w-[240px] border-r border-white/8 bg-white/[0.03] p-4">
          <div className="mb-6">
            <div className="font-heading text-2xl">Workspace Settings</div>
            <p className="mt-2 text-sm leading-6 text-[var(--muted)]">只接通本轮真正可落地的能力，其余明确标注状态。</p>
          </div>
          <div className="space-y-2">
            {SECTIONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveSection(id)}
                className={`flex h-11 w-full items-center gap-3 rounded-2xl border px-3 text-left text-sm transition ${
                  activeSection === id
                    ? "border-[var(--line-strong)] bg-[var(--accent-soft)] text-[var(--foreground)]"
                    : "border-white/8 bg-white/4 text-[var(--muted)] hover:border-[var(--line-strong)] hover:text-[var(--foreground)]"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>
        </aside>

        <section className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-white/8 px-6 py-4">
            <div className="text-sm uppercase tracking-[0.24em] text-[var(--muted)]">{activeSection}</div>
            <button
              type="button"
              className="rounded-full border border-white/8 px-3 py-1 text-sm text-[var(--muted)] transition hover:border-[var(--line-strong)] hover:text-[var(--foreground)]"
              onClick={onClose}
            >
              关闭
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-6">
            {activeSection === "appearance" && (
              <div className="space-y-5">
                <SettingsCard title="视觉基线" description="高保真审美升级后置，这里只维护工作台级交互和可读性开关。">
                  <ToggleRow
                    label="减少动效"
                    description="为后续编排动画和过渡效果预留可访问性开关。"
                    checked={reducedMotion}
                    onChange={() => setReducedMotion((value) => !value)}
                  />
                  <ToggleRow
                    label="通知提醒"
                    description="会用于后台完成提醒和后续 command/agent 结束通知。"
                    checked={notificationsEnabled}
                    onChange={async () => {
                      if (!notificationsEnabled && typeof window !== "undefined" && "Notification" in window) {
                        if (Notification.permission === "default") {
                          await Notification.requestPermission();
                        }
                      }
                      setNotificationsEnabled((value) => !value);
                    }}
                  />
                  <div className="rounded-3xl border border-white/8 bg-white/[0.03] px-4 py-4 text-sm text-[var(--muted)]">
                    浏览器通知权限：
                    <span className="ml-2 text-[var(--foreground)]">
                      {typeof window !== "undefined" && "Notification" in window
                        ? Notification.permission
                        : "unsupported"}
                    </span>
                  </div>
                </SettingsCard>
              </div>
            )}

            {activeSection === "memory" && (
              <div className="space-y-5">
                <SettingsCard title="Memory" description="Memory 已经收敛进 sqlite，这里提供真实的导出、导入和清空能力。">
                  <input
                    ref={memoryInputRef}
                    type="file"
                    accept="application/json"
                    className="hidden"
                    onChange={handleMemoryFileChange}
                  />
                  <div className="mb-4 flex flex-wrap items-center justify-end gap-3">
                    <ActionButton onClick={() => exportMemoryMutation.mutate()} pending={exportMemoryMutation.isPending}>
                      导出 JSON
                    </ActionButton>
                    <ActionButton
                      onClick={() => beginMemoryImport("merge")}
                      pending={importMemoryMutation.isPending && memoryImportMode === "merge"}
                    >
                      导入并合并
                    </ActionButton>
                    <ActionButton
                      onClick={() => beginMemoryImport("replace")}
                      pending={importMemoryMutation.isPending && memoryImportMode === "replace"}
                    >
                      导入并替换
                    </ActionButton>
                    <button
                      type="button"
                      onClick={() => clearMemoryMutation.mutate()}
                      className="rounded-full border border-red-400/30 bg-red-500/10 px-3 py-1.5 text-sm text-red-200 transition hover:border-red-400/50 disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={clearMemoryMutation.isPending}
                    >
                      {clearMemoryMutation.isPending ? "清空中..." : "清空 Memory"}
                    </button>
                  </div>
                  {memoryStatus && (
                    <div className="mb-4 rounded-3xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-[var(--muted)]">
                      {memoryStatus}
                    </div>
                  )}
                  <pre className="max-h-[420px] overflow-auto rounded-3xl border border-white/8 bg-black/20 p-4 text-xs leading-6 text-[var(--muted)]">
                    {memoryQuery.isLoading ? "加载中..." : JSON.stringify(memoryQuery.data ?? { empty: true }, null, 2)}
                  </pre>
                </SettingsCard>
              </div>
            )}

            {activeSection === "skills" && (
              <div className="space-y-5">
                <SettingsCard title="Skills" description="这里的启停会真实写回技能 frontmatter，并影响后续新会话注入的可用技能。">
                  {skillsStatus && (
                    <div className="mb-4 rounded-3xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-[var(--muted)]">
                      {skillsStatus}
                    </div>
                  )}
                  <div className="space-y-3">
                    {(skillsQuery.data ?? []).map((skill) => (
                      <div key={skill.name} className="rounded-3xl border border-white/8 bg-white/[0.03] p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold">{skill.name}</div>
                            <div className="mt-2 text-sm leading-6 text-[var(--muted)]">{skill.description || "暂无说明"}</div>
                            {skill.path && <div className="mt-2 truncate text-xs text-[var(--muted)]">{skill.path}</div>}
                          </div>
                          <ToggleRow
                            compact
                            label={skill.enabled ? "Enabled" : "Disabled"}
                            description={updateSkillMutation.isPending && updateSkillMutation.variables?.name === skill.name ? "保存中..." : "点击切换"}
                            checked={skill.enabled}
                            disabled={updateSkillMutation.isPending}
                            onChange={() => updateSkillMutation.mutate({ name: skill.name, enabled: !skill.enabled })}
                          />
                        </div>
                      </div>
                    ))}
                    {!skillsQuery.isLoading && (skillsQuery.data ?? []).length === 0 && (
                      <div className="rounded-3xl border border-dashed border-white/8 px-4 py-8 text-sm text-[var(--muted)]">
                        当前没有可展示技能。
                      </div>
                    )}
                  </div>
                </SettingsCard>
              </div>
            )}

            {activeSection === "agents" && (
              <div className="space-y-5">
                <SettingsCard title="Agents" description="这里接的是自定义 Agent 的真实文件配置：agents/{name}/config.yaml 与 SOUL.md。">
                  {agentsStatus && (
                    <div className="mb-4 rounded-3xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-[var(--muted)]">
                      {agentsStatus}
                    </div>
                  )}

                  <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
                    <div className="space-y-3">
                      <div className="rounded-3xl border border-white/8 bg-white/[0.03] p-4">
                        <div className="mb-3 text-sm font-semibold">创建新 Agent</div>
                        <input
                          value={newAgentName}
                          onChange={(event) => {
                            setNewAgentName(event.target.value);
                            setSelectedAgentName("");
                          }}
                          placeholder="research-copilot"
                          className="mb-3 h-11 w-full rounded-2xl border border-white/8 bg-black/20 px-3 text-sm outline-none transition focus:border-[var(--line-strong)]"
                        />
                        <ActionButton onClick={createNewAgent} pending={createAgentMutation.isPending}>
                          <span className="inline-flex items-center gap-2">
                            <Plus className="h-3.5 w-3.5" />
                            新建 Agent
                          </span>
                        </ActionButton>
                      </div>

                      <div className="space-y-2">
                        {(agentsQuery.data ?? []).map((agent) => (
                          <button
                            key={agent.name}
                            type="button"
                            onClick={() => selectAgent(agent)}
                            className={`w-full rounded-3xl border p-4 text-left transition ${
                              selectedAgentName === agent.name
                                ? "border-[var(--line-strong)] bg-[var(--accent-soft)] text-[var(--foreground)]"
                                : "border-white/8 bg-white/[0.03] text-[var(--muted)] hover:border-[var(--line-strong)] hover:text-[var(--foreground)]"
                            }`}
                          >
                            <div className="text-sm font-semibold">{agent.name}</div>
                            <div className="mt-2 line-clamp-2 text-xs leading-5">{agent.description || "暂无描述"}</div>
                          </button>
                        ))}
                        {!agentsQuery.isLoading && (agentsQuery.data ?? []).length === 0 && (
                          <div className="rounded-3xl border border-dashed border-white/8 px-4 py-8 text-sm text-[var(--muted)]">
                            当前没有 Agent。可以在这里新建，也可以去 `/workspace/agents/new` 走完整创建向导。
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-3xl border border-white/8 bg-white/[0.03] p-4">
                      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold">
                            {selectedAgentName || newAgentName.trim() || "选择或创建 Agent"}
                          </div>
                          <div className="mt-1 text-xs text-[var(--muted)]">
                            修改后会影响后续进入该 Agent 专属聊天时的系统提示注入。
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <ActionButton onClick={saveSelectedAgent} pending={updateAgentMutation.isPending}>
                            保存配置
                          </ActionButton>
                          <button
                            type="button"
                            disabled={!selectedAgentName || deleteAgentMutation.isPending}
                            onClick={() => selectedAgentName && deleteAgentMutation.mutate(selectedAgentName)}
                            className="inline-flex items-center gap-2 rounded-full border border-red-400/30 bg-red-500/10 px-3 py-1.5 text-sm text-red-200 transition hover:border-red-400/50 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            删除
                          </button>
                        </div>
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        <label className="block">
                          <span className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Description</span>
                          <input
                            value={agentDescription}
                            onChange={(event) => setAgentDescription(event.target.value)}
                            placeholder="这个 Agent 解决什么问题？"
                            className="mt-2 h-11 w-full rounded-2xl border border-white/8 bg-black/20 px-3 text-sm outline-none transition focus:border-[var(--line-strong)]"
                          />
                        </label>
                        <label className="block">
                          <span className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Model Override</span>
                          <input
                            value={agentModel}
                            onChange={(event) => setAgentModel(event.target.value)}
                            placeholder="留空则使用当前会话模型"
                            className="mt-2 h-11 w-full rounded-2xl border border-white/8 bg-black/20 px-3 text-sm outline-none transition focus:border-[var(--line-strong)]"
                          />
                        </label>
                      </div>

                      <label className="mt-4 block">
                        <span className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">SOUL.md</span>
                        <textarea
                          value={agentSoul}
                          onChange={(event) => setAgentSoul(event.target.value)}
                          rows={18}
                          placeholder="# Agent SOUL\n\n## 定位\n..."
                          className="mt-2 w-full resize-none rounded-3xl border border-white/8 bg-black/20 px-4 py-3 font-mono text-xs leading-6 outline-none transition focus:border-[var(--line-strong)]"
                        />
                      </label>
                    </div>
                  </div>
                </SettingsCard>
              </div>
            )}

            {activeSection === "tools" && (
              <div className="space-y-5">
                <SettingsCard title="Tools Runtime" description="这里接的是运行时真开关。修改后，新会话创建的 agent 会按新配置加载工具。">
                  {toolsStatus && (
                    <div className="mb-4 rounded-3xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-[var(--muted)]">
                      {toolsStatus}
                    </div>
                  )}
                  <div className="space-y-4">
                    {(toolsQuery.data?.tool_groups ?? []).map((group) => (
                      <ToggleRow
                        key={group.name}
                        label={`工具组 · ${group.name}`}
                        description={`包含 ${group.tool_count} 个工具。关闭后该组工具不会进入后续 agent 运行时。`}
                        checked={group.enabled}
                        disabled={updateToolsMutation.isPending}
                        onChange={() =>
                          updateToolsMutation.mutate({
                            tool_groups: [{ name: group.name, enabled: !group.enabled }],
                          })
                        }
                      />
                    ))}
                    <ToggleRow
                      label="允许 Host Bash"
                      description="关闭后，即使 bash 组开启，也不会把宿主 bash 注入到运行时。"
                      checked={toolsQuery.data?.runtime.allow_host_bash ?? false}
                      disabled={updateToolsMutation.isPending}
                      onChange={() =>
                        updateToolsMutation.mutate({
                          allow_host_bash: !(toolsQuery.data?.runtime.allow_host_bash ?? false),
                        })
                      }
                    />
                  </div>
                  <div className="mt-6 rounded-3xl border border-white/8 bg-white/[0.03] p-4">
                    <div className="text-sm font-semibold">工具清单</div>
                    <div className="mt-3 space-y-2">
                      {(toolsQuery.data?.tools ?? []).map((tool) => (
                        <div key={tool.name} className="flex items-center justify-between gap-4 rounded-2xl border border-white/8 px-3 py-2 text-sm">
                          <div>
                            <span className="font-medium">{tool.name}</span>
                            <span className="ml-2 text-[var(--muted)]">{tool.group ?? "ungrouped"}</span>
                          </div>
                          <span className={`rounded-full border px-3 py-1 text-xs ${tool.enabled ? "border-emerald-400/30 text-emerald-200" : "border-white/8 text-[var(--muted)]"}`}>
                            {tool.enabled ? "active" : "inactive"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mt-6 rounded-3xl border border-dashed border-white/8 px-4 py-5 text-sm leading-7 text-[var(--muted)]">
                    MCP 状态：<strong className="text-[var(--foreground)]">{toolsQuery.data?.mcp.supported ? "available" : "not wired"}</strong>
                    <br />
                    {toolsQuery.data?.mcp.reason ?? "当前没有 MCP 运行时配置。"}
                  </div>
                  <div className="mt-6 rounded-3xl border border-white/8 bg-white/[0.03] p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <div className="text-sm font-semibold">MCP Servers</div>
                        <div className="mt-1 text-sm text-[var(--muted)]">
                          当前先接通 stdio server。新建或启停后，新会话会重新发现 MCP tools。
                        </div>
                      </div>
                      <ToggleRow
                        compact
                        label={mcpQuery.data?.enabled ? "MCP Enabled" : "MCP Disabled"}
                        description={`${mcpQuery.data?.servers.length ?? 0} servers`}
                        checked={mcpQuery.data?.enabled ?? false}
                        disabled={updateMcpConfigMutation.isPending}
                        onChange={() => updateMcpConfigMutation.mutate({ enabled: !(mcpQuery.data?.enabled ?? false) })}
                      />
                    </div>
                    {mcpStatus && (
                      <div className="mt-4 rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm text-[var(--muted)]">
                        {mcpStatus}
                      </div>
                    )}
                    <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto]">
                      <input
                        value={newMcpName}
                        onChange={(event) => setNewMcpName(event.target.value)}
                        placeholder="server name"
                        className="rounded-2xl border border-white/8 bg-black/20 px-3 py-2 text-sm outline-none"
                      />
                      <input
                        value={newMcpCommand}
                        onChange={(event) => setNewMcpCommand(event.target.value)}
                        placeholder="command, e.g. npx"
                        className="rounded-2xl border border-white/8 bg-black/20 px-3 py-2 text-sm outline-none"
                      />
                      <input
                        value={newMcpArgs}
                        onChange={(event) => setNewMcpArgs(event.target.value)}
                        placeholder="args"
                        className="rounded-2xl border border-white/8 bg-black/20 px-3 py-2 text-sm outline-none"
                      />
                      <ActionButton onClick={createNewMcpServer} pending={createMcpServerMutation.isPending}>
                        添加
                      </ActionButton>
                    </div>
                    <div className="mt-4 space-y-3">
                      {(mcpQuery.data?.servers ?? []).map((server) => (
                        <div key={server.name} className="rounded-3xl border border-white/8 bg-black/20 p-4">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-sm font-semibold">{server.name}</div>
                              <div className="mt-1 truncate text-xs text-[var(--muted)]">
                                {server.transport} · {server.command || server.url} {server.args.join(" ")}
                              </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <ActionButton
                                onClick={() => discoverMcpServerMutation.mutate(server.name)}
                                pending={discoverMcpServerMutation.isPending && discoverMcpServerMutation.variables === server.name}
                              >
                                发现工具
                              </ActionButton>
                              <ActionButton
                                onClick={() =>
                                  updateMcpServerMutation.mutate({
                                    name: server.name,
                                    server: { ...server, enabled: !server.enabled },
                                  })
                                }
                                pending={updateMcpServerMutation.isPending && updateMcpServerMutation.variables?.name === server.name}
                              >
                                {server.enabled ? "停用" : "启用"}
                              </ActionButton>
                              <button
                                type="button"
                                onClick={() => deleteMcpServerMutation.mutate(server.name)}
                                className="rounded-full border border-red-400/30 bg-red-500/10 px-3 py-1.5 text-sm text-red-200 transition hover:border-red-400/50 disabled:cursor-not-allowed disabled:opacity-60"
                                disabled={deleteMcpServerMutation.isPending}
                              >
                                删除
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                      {!mcpQuery.isLoading && (mcpQuery.data?.servers ?? []).length === 0 && (
                        <div className="rounded-3xl border border-dashed border-white/8 px-4 py-8 text-sm text-[var(--muted)]">
                          当前没有 MCP server。添加一个 stdio server 后，可以先“发现工具”验证。
                        </div>
                      )}
                    </div>
                  </div>
                </SettingsCard>
              </div>
            )}

            {activeSection === "about" && (
              <div className="space-y-5">
                <SettingsCard title="About" description="当前正式工作台已收敛到 workspace-frontend；旧 Vite 前端和 FastAPI 静态托管入口已移除。">
                  <dl className="grid gap-3 text-sm text-[var(--muted)]">
                    <div className="rounded-3xl border border-white/8 bg-white/[0.03] p-4">
                      <dt className="text-xs uppercase tracking-[0.24em]">API Base</dt>
                      <dd className="mt-2 break-all text-[var(--foreground)]">{getApiBaseUrl()}</dd>
                    </div>
                    <div className="rounded-3xl border border-white/8 bg-white/[0.03] p-4">
                      <dt className="text-xs uppercase tracking-[0.24em]">Upgrade Mode</dt>
                      <dd className="mt-2 text-[var(--foreground)]">Workspace-first, Next.js App Router, no legacy Vite fallback.</dd>
                    </div>
                  </dl>
                </SettingsCard>
              </div>
            )}
          </div>
        </section>
      </div>
      <button type="button" aria-label="关闭设置" className="absolute inset-0 -z-10" onClick={onClose} />
    </div>
  );
}

function SettingsCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="panel p-6">
      <h2 className="font-heading text-3xl">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{description}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function ActionButton({
  children,
  pending = false,
  onClick,
}: {
  children: ReactNode;
  pending?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      className="rounded-full border border-white/8 bg-white/[0.03] px-3 py-1.5 text-sm text-[var(--foreground)] transition hover:border-[var(--line-strong)] disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pending ? "处理中..." : children}
    </button>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  disabled = false,
  compact = false,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <div className={`flex items-center justify-between gap-4 rounded-3xl border border-white/8 bg-white/[0.03] ${compact ? "px-3 py-3" : "px-4 py-4"}`}>
      <div>
        <div className="text-sm font-semibold">{label}</div>
        <div className="mt-1 text-sm text-[var(--muted)]">{description}</div>
      </div>
      <button
        type="button"
        aria-pressed={checked}
        onClick={onChange}
        disabled={disabled}
        className={`relative h-8 w-14 rounded-full transition ${checked ? "bg-[var(--accent)]" : "bg-white/10"} disabled:cursor-not-allowed disabled:opacity-50`}
      >
        <span
          className={`absolute top-1 h-6 w-6 rounded-full bg-[#020617] transition ${checked ? "left-7" : "left-1"}`}
        />
      </button>
    </div>
  );
}
