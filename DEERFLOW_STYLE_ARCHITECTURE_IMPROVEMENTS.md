# VD-Flow 参考 DeerFlow 的架构改进文档

## 1. 结论先说

如果目标是把 `vd-flow` 做成一个可长期演进、可按需配置 `skills` 和 `middleware` 的通用助手，那么更适合照抄 DeerFlow 的**主思路**，而不是把系统先做成“内置若干垂直 workflow 的内核”。

最核心的判断只有一句：

**DeerFlow 的本质是“通用 Lead Agent + Prompt Template + Middleware Chain + Tool Loader + Skills Injection”，而不是“显式任务流注册中心”。**

所以 `vd-flow` 下一阶段最合理的方向是：

- 主 Agent 保持通用
- 垂直能力优先通过 `skills`、工具和可配置 middleware 挂载
- 主系统只负责对话控制、澄清、工具调用、线程状态和能力装配
- 不把 `research`、`code_assistant`、`writing` 这类能力写死进内核

## 2. DeerFlow 到底是怎么做的

### 2.1 单一入口，不拆多个主 Agent

DeerFlow 的运行时入口是一个 `make_lead_agent(config)`。

核心特点：

- 只有一个主 Agent runtime
- 根据运行时配置决定加载哪些工具、哪些 middleware、是否启用 subagent
- 根据 `agent_name` 加载不同的 `SOUL.md` 和 agent config
- 不为 research、code、writing 单独造一套核心 runtime

这意味着 DeerFlow 的“可扩展”不是靠多套主程序，而是靠**同一个通用 Agent 外挂能力**。

### 2.2 Prompt Template 是第一控制面

DeerFlow 的主 prompt 不是手写死字符串，而是模板装配：

- `role`
- `soul`
- `memory_context`
- `clarification_system`
- `skills_section`
- `deferred_tools_section`
- `subagent_section`
- `working_directory`
- `response_style`
- `citations`
- `critical_reminders`

也就是说，它的主 Agent 行为边界主要是靠**结构化 prompt section**定义，而不是靠一堆散落的 prompt 文案。

这点非常重要，因为这意味着：

- 规则是模块化的
- 能按能力开关拼装
- 后续可以替换某个 section，而不用重写整份系统提示

### 2.3 Middleware 只做横切，不做业务主流程

DeerFlow 的 middleware 主要负责横切问题：

- 线程目录初始化
- 上传文件注入
- sandbox 获取/释放
- summarization
- todo
- title
- memory
- vision
- clarification interrupt

它们不负责“research 的 search/evidence/synthesis”这种业务阶段逻辑。

这说明 DeerFlow 的默认哲学是：

**业务能力尽量放在 prompt + tool + skill 层；middleware 只负责运行时秩序。**

### 2.4 Skills 是“工作说明书”，不是 runtime 状态机

DeerFlow 会把可用技能注入到 `<available_skills>` 区块，并明确要求：

1. 命中 skill 场景时先读 `SKILL.md`
2. 再按 skill 指令执行
3. skill 引用的更多资料按需渐进加载

这说明 DeerFlow 里 skill 的定位是：

- 最佳实践包
- 复杂任务说明书
- prompt 内的能力挂载层

但它不是：

- 显式 phase runtime
- 可恢复 workflow state machine
- 内核级任务流注册器

### 2.5 Tools 是配置驱动装配，不是写死清单

DeerFlow 的工具装配思路也很值得照抄：

- 配置工具
- builtin 工具
- MCP 工具
- ACP 工具
- 条件工具

并且会根据运行时能力决定是否暴露：

- 是否允许 host bash
- 当前模型是否支持 vision
- 是否启用 subagent
- 是否启用 tool search

所以 DeerFlow 的工具系统不是“固定工具列表”，而是**配置驱动 + 能力驱动**。

### 2.6 Custom Agent 的方式不是分叉 runtime，而是换 Soul 和配置

DeerFlow 有 `SOUL.md + config.yaml` 机制。

这意味着：

- 还是同一个 `lead_agent`
- 只是人格、工具组、模型、skills 白名单发生变化

这个思路非常适合 `vd-flow`。

因为它避免了一个常见错误：

为每种能力都造一套新的主 Agent 工厂，最后系统越来越碎。

## 3. DeerFlow 值得直接照抄的部分

以下这些，我建议 `vd-flow` 基本原样照抄，只做轻量化而不是另起炉灶。

### 3.1 Lead Agent Template 化

目标：

- 不再用一个写死的 `BASE_PROMPT`
- 改成 `load_lead_prompt()` 或 `apply_prompt_template()` 风格
- 把系统提示拆成多个 section

建议 section：

- `role`
- `soul`
- `memory`
- `clarification_system`
- `skill_system`
- `working_directory`
- `response_style`
- `critical_reminders`

这样做的好处：

- 主 Agent 永远保持通用
- 可以单独替换某个 section
- 后续新增能力不会把主 prompt 写成一锅粥

### 3.2 Middleware Chain 化

目标：

- 把 `vdflow/agent/middleware.py` 从几个散装类，变成明确顺序的 middleware chain

推荐先做这几层：

1. `ThreadDataMiddleware`
2. `FileUploadMiddleware`
3. `MemoryMiddleware`
4. `TitleMiddleware`
5. `ToolErrorMiddleware`
6. `ClarificationMiddleware`

关键原则：

- `ClarificationMiddleware` 必须在链路最后，以保证最先拦截 `ask_clarification`
- middleware 只处理横切能力，不碰垂直业务策略

### 3.3 线程目录和虚拟工作区

目标：

- 不再让文件写入逻辑散落在工具里
- 显式建立每线程的 `workspace / uploads / outputs`

建议目录语义：

- `workspace`: 临时工作目录
- `uploads`: 用户上传
- `outputs`: 最终产物

好处：

- 路径边界清晰
- 前端/后端/后续渠道都能复用同一线程空间
- 后面接 sandbox 时不用推翻重做

### 3.4 工具装配改为配置驱动

目标：

- 工具系统从“固定 builtin 列表”升级为“配置工具 + builtin 工具 + 条件工具”

建议保留：

- `ask_clarification`
- `read_file`
- `write_file`
- `web_search`
- `web_fetch`
- `bash`

但装配逻辑要改成：

- 按配置加载
- 按模型能力决定是否加 vision 类工具
- 按运行模式决定是否暴露高风险工具

### 3.5 Skills 保持“辅助手段”定位

这里的“辅助手段”不是弱化 skill 的价值，而是摆正它的位置。

正确理解是：

- skill 决定“怎么更好地做”
- 但不决定“系统主流程是什么”

也就是说：

- 主 Agent 仍然先通用理解和澄清
- 命中 skill 场景时，再去加载 skill
- skill 是工作手册，不是系统内核

这正是 DeerFlow 的做法。

### 3.6 Custom Agent / Agent Soul 机制

建议 `vd-flow` 后续也引入：

- `agents/<agent-name>/SOUL.md`
- `agents/<agent-name>/config.yaml`

这样你可以在不复制 runtime 的情况下做：

- 一个偏研究风格的助手
- 一个偏 coding 风格的助手
- 一个偏咨询风格的助手

但本质上都还是同一个 Lead Agent 框架。

## 4. 不建议照抄 DeerFlow 的部分

这里不是 DeerFlow 不好，而是对 `vd-flow` 当前阶段不划算。

### 4.1 不先抄 subagent

原因：

- 当前 `vd-flow` 还没有稳定的工具边界
- 文件空间和安全边界还不够强
- 先上 subagent 只会放大复杂度

建议：

- 先把单 Agent runtime 做对
- 后面再接 `task()` 或等价 delegation 能力

### 4.2 不先抄 MCP / ACP

原因：

- 这不是当前最短路径
- 会把系统重心从“内核做对”带偏到“接口接更多”

建议：

- 先把工具装配机制抽象好
- 预留接口，但不立刻接 MCP

### 4.3 不直接照抄 DeerFlow 的全部 prompt 复杂度

DeerFlow 的 prompt section 已经很重。

`vd-flow` 应该抄的是它的**装配方式**，不是字面复杂度。

也就是说：

- 学模块化
- 不学过度膨胀

## 5. 对 VD-Flow 的推荐目标架构

建议把 `vd-flow` 改造成下面这个结构。

```text
User Request
  -> Lead Agent Runtime
    -> Prompt Template Loader
    -> Middleware Chain
    -> Tool Loader
    -> Skills Injection
    -> Thread State / Thread Data
  -> Final Response / Artifacts
```

### 5.1 内核职责

内核只做这些：

- 对话入口
- 澄清优先
- 工具调用
- 线程状态维护
- 线程目录管理
- 能力装配

内核不做这些：

- 写死 research/code/writing 三大工作流
- 在内核里绑定某个垂直领域身份
- 用 prompt 假装 phase state machine

### 5.2 能力挂载层

能力挂载优先通过：

1. `skills`
2. `tools`
3. `middleware`
4. `agent soul`

而不是通过“新增一个内置 workflow 类型”。

### 5.3 线程状态应保持轻量但可扩展

参考 DeerFlow，`ThreadState` 更适合只保存通用运行时信息：

- `messages`
- `title`
- `artifacts`
- `uploaded_files`
- `memory_context`
- `thread_data`
- `active_skills`
- `viewed_images`
- `pending_clarification`

不要一开始就把 `ResearchState / CodeState / WritingState` 写死进顶层。

否则插件性会被反向锁死。

## 6. 对 VD-Flow 的升级改进建议

这里是我建议你**比 DeerFlow 更进一步**的地方。

这些不是现在就全做，而是作为架构留白。

### 6.1 比 DeerFlow 更强的 middleware 注册机制

DeerFlow 现在 middleware 顺序是代码里显式拼装的。

`vd-flow` 可以更进一步，做成：

- 配置驱动启用/禁用
- 顺序校验
- 依赖校验

例如：

- `ClarificationMiddleware` 必须最后
- `ThreadDataMiddleware` 必须在文件/工具相关 middleware 之前

这样系统会更“可配置”，而不是只能改源码。

### 6.2 比 DeerFlow 更轻的能力切换模型

DeerFlow 有 custom agent，但对很多场景来说仍然偏“整套 agent profile”。

`vd-flow` 可以做得更轻：

- 一个主 agent
- 支持按线程选择 `agent_name`
- 同时允许只切换 `skills` 集合或 `tool_groups`

也就是说，不是只有“切人格”这一种切法，还能做“切能力包”。

### 6.3 比 DeerFlow 更清晰的前端状态语义

DeerFlow 强在运行时，但前端消费这些内部结构时并不总是最轻。

`vd-flow` 可以更明确地给 UI 暴露：

- 当前线程状态
- 当前是否等待澄清
- 已生成 artifact 列表
- 当前活跃 skill
- 最近一次工具动作摘要

重点是暴露“运行状态”，而不是暴露一堆内部实现细节。

### 6.4 比 DeerFlow 更严格的本地代码改写边界

如果 `vd-flow` 要做 coding assistant，建议比 DeerFlow 更保守：

- 默认只读
- 用户明确要求后才允许写
- 允许写的路径必须白名单
- 验证命令必须白名单

也就是说：

**本地改码要比“读 skill / 查资料”更高权限。**

### 6.5 把显式 workflow 做成“可选增强层”，不是核心层

这是最关键的升级建议。

我不建议现在把系统核心直接改成“内建 workflow registry”。

更好的办法是：

- 先把 DeerFlow 风格主干做好
- 以后如果确实需要某个高价值场景的强结构化控制
- 再把 workflow 做成可选插件

也就是说：

- 默认系统 = DeerFlow 风格
- 高强度流程控制 = 可选增强，不是默认哲学

这样不会把整个系统过早绑定到某几类垂直流程。

## 7. 建议的改造顺序

严格建议按这个顺序推进。

### 阶段 1：主 Agent 去垂直化

目标：

- 去掉“研究助手”身份
- 改成通用 Lead Agent
- 主 prompt 改为 template loader

产出：

- `load_lead_prompt()` 或等价实现
- prompt sections 初版

### 阶段 2：middleware 体系化

目标：

- 建立可维护的 middleware chain
- 把澄清中断做成真正 runtime 能力
- 增加 thread data 目录管理

产出：

- `ThreadDataMiddleware`
- `ClarificationMiddleware`
- `TitleMiddleware`
- middleware builder

### 阶段 3：工具装配重构

目标：

- 按配置加载工具
- 加入条件工具逻辑
- 统一 builtin tool 策略

产出：

- `get_available_tools()`
- builtin/config tools 合并装配

### 阶段 4：skills 降级为辅助手段

目标：

- 从“主流程控制器”变为“工作说明书”
- 保留技能价值，但不让它接管系统内核

产出：

- 新的 skill prompt section
- skill 命中与加载约定

### 阶段 5：custom agent / soul 机制

目标：

- 同一个 runtime 支持多个 agent profile

产出：

- `agents/<name>/SOUL.md`
- `agents/<name>/config.yaml`

### 阶段 6：可选增强层

可选项，不是首批必做：

- workflow 插件
- subagent
- MCP
- 更强的前端状态协议

## 8. 对当前 VD-Flow 的明确建议

如果按这份文档执行，我建议你现在做的不是：

- 先写死 `research` 和 `code_assistant` 的 graph

而应该是：

- 先把 `vd-flow` 改成 DeerFlow 风格的通用主干
- `research` 先作为 skill 留着
- `code_assistant` 先通过工具边界 + soul/skill 方式挂载
- 等你确认确实需要强结构化流程，再把 workflow 做成插件层

一句话说：

**先做“通用助手平台”，再做“可选工作流插件”；不要反过来。**

## 9. 最终推荐决策

我推荐的最终路线是：

### 9.1 短期

完全按 DeerFlow 主思路改造 `vd-flow`：

- 通用 Lead Agent
- Prompt Template
- Middleware Chain
- Tool Loader
- Skills Injection
- Thread Data
- Custom Agent/Soul

### 9.2 中期

在不破坏主干的前提下增强：

- middleware 配置化
- tool 权限分级
- 更清晰的 UI 状态协议
- custom capability packs

### 9.3 长期

如果出现明显需要强约束的高价值任务，再增加：

- 可选 workflow plugin runtime

而不是让 workflow 成为系统核心哲学。

---

## 10. 一句话判断标准

如果改完以后，`vd-flow` 仍然需要靠主 prompt 先把自己定义成“研究助手”或“代码助手”，那方向还是错的。

如果改完以后，系统可以做到：

- 主 Agent 永远通用
- 能力靠 skills / tools / middleware / soul 挂载
- 线程状态和工作目录统一
- 后续新增能力不用重写主 runtime

那这次改造方向就是对的。
