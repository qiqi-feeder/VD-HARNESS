# VD-Flow 通用助手 MVP 执行模板

## 1. 目标定义

### 1.1 产品目标
把 `vd-flow` 从“带研究技能的聊天 Agent”改造成“通用助手内核 + 垂直能力任务流”的 MVP。

### 1.2 成功标准
MVP 成功不等于功能多，而等于这 4 件事成立：
- 主 Agent 默认是通用助手，不预设自己是研究助手、代码助手或写作助手。
- 所有垂直能力都以“任务流”形式挂载，而不是写死在主 prompt 里。
- 同一个线程里，系统能根据任务类型进入对应工作流，并把中间状态写入显式状态对象。
- Web 层、后续的 Feishu 层都只复用同一个线程内核，不各自维护独立逻辑。

### 1.3 非目标
本阶段不做这些事：
- 不先做多 Agent 编排。
- 不先做复杂长期记忆。
- 不先做 MCP。
- 不先做多渠道接入。
- 不先做 Docker 沙盒。
- 不先追求“全任务都强”，只先把架构方向做对。

## 2. 第一性原理

### 2.1 主 Agent 的职责
主 Agent 只做 4 件事：
- 理解用户意图
- 澄清不清楚的信息
- 选择任务流
- 汇总任务流结果并回复用户

主 Agent 不直接承担所有垂直领域细节。

### 2.2 垂直能力的职责
研究、代码分析、写作整理、文件理解这类能力，不是不同“人格”，而是不同“任务流”。

也就是说：
- `research` 不是主 Agent 的身份
- `code_assistant` 不是主 Agent 的身份
- 它们都是主 Agent 可以调用的工作方式

### 2.3 为什么要这样拆
因为如果把能力写进主 prompt：
- 任务边界会漂
- 行为难验证
- 中间状态不可控
- 后续接 Feishu、技能、更多能力时会越来越乱

如果把能力做成任务流：
- 可以定义进入条件
- 可以定义中间状态
- 可以定义验收条件
- 可以逐步扩展，不会把主 Agent 越写越肿

## 3. MVP 总体架构

```text
User Input
  -> Lead Agent
    -> Clarify
    -> Route TaskFlow
      -> TaskFlow Runtime
        -> Tools / Skills / Memory / Files
      -> TaskFlow Result
    -> Final Response
```

### 3.1 核心分层

#### A. Lead Agent
负责通用对话控制。

输入：用户消息、线程状态、上下文
输出：
- 直接回答
- 发起澄清
- 进入某个任务流

#### B. TaskFlow Registry
维护所有可用任务流：
- `research`
- `code_assistant`
- `writing`
- `file_analysis`

MVP 先做前 2-3 个即可。

#### C. TaskFlow Runtime
负责真正执行任务流阶段：
- 初始化状态
- 按阶段推进
- 工具调用
- 产出结果
- 回写线程状态

#### D. Thread / Conversation Core
继续复用现有 `thread_id` 机制，不再新造一套会话模型。

## 4. 推荐的 MVP 任务流集合

### 4.1 必做任务流

#### 1. `research`
适用于：行业调研、技术调研、方案对比、事实搜集、报告草稿

阶段建议：
- clarify
- scope
- search
- evidence
- synthesis
- output

输出：
- 结论型回答
- Markdown 报告
- 引用来源列表

#### 2. `code_assistant`
适用于：读代码、定位问题、改代码、解释架构、输出变更建议

阶段建议：
- clarify
- inspect
- plan
- patch
- verify
- output

输出：
- 分析结论
- 代码修改
- 验证结果

#### 3. `writing`
适用于：总结、润色、重写、提纲整理、文档生成

阶段建议：
- clarify
- collect_material
- outline
- draft
- refine
- output

输出：
- 文案
- 结构化文档

### 4.2 后做任务流
- `file_analysis`
- `data_analysis`
- `agent_builder`

原因：这些方向需要更明确的中间状态和工具边界，MVP 不该一开始做太多。

## 5. 状态设计

### 5.1 现状问题
当前 `vdflow.agent.state.ThreadState` 过于通用，只覆盖：
- messages
- title
- uploaded_files
- artifacts
- memory_context
- active_skills

这足够做聊天，不足够做任务流。

### 5.2 MVP 新增状态模型
建议保留 `ThreadState` 作为线程总状态，再增加一层任务状态。

```python
ThreadState
- messages
- thread_id
- title
- uploaded_files
- artifacts
- memory_context
- active_skills
- current_task
- task_history
- taskflow_state
```

```python
TaskflowState
- flow_name
- status
- phase
- goal
- assumptions
- missing_info
- inputs
- intermediate_outputs
- final_output
- metadata
```

### 5.3 研究任务流状态
```python
ResearchState
- topic
- scope
- questions
- search_queries
- sources
- evidence_items
- claims
- outline
- report_path
```

### 5.4 代码任务流状态
```python
CodeAssistantState
- target_paths
- issue_summary
- plan
- changed_files
- verification_results
- risks
```

原则只有一个：
**中间结果必须进状态，不要只存在模型脑子里。**

## 6. 路由策略

### 6.1 MVP 不做复杂分类器
先用简单可控的方式：
- Lead Agent 先判断是否需要澄清
- 澄清后输出 `task_type`
- 系统再进入对应任务流

### 6.2 推荐的任务类型枚举
- `general_chat`
- `research`
- `code_assistant`
- `writing`

### 6.3 路由规则
- 无需任务流的简单问答 -> `general_chat`
- 明确要求调研、比较、收集资料 -> `research`
- 明确要求看代码、改代码、分析仓库 -> `code_assistant`
- 明确要求重写、总结、写文档 -> `writing`

## 7. 与 DeerFlow 对齐的设计原则

### 7.1 学 DeerFlow 的地方
- 主 Agent 保持通用，不先垂直化。
- 澄清优先于行动。
- 技能和工具是能力挂载层，不是主身份。
- 会话与渠道解耦。
- 中间件只做横切能力，不承担业务任务流本身。

### 7.2 不直接照搬 DeerFlow 的地方
- MVP 阶段不先做 subagent。
- MVP 阶段不先做多渠道。
- MVP 阶段不先做很重的 runtime 装配。

### 7.3 你的落地版本
对 `vd-flow`，最合理的是：
- 先保留单 Agent runtime
- 在 runtime 内新增 TaskFlow 层
- 先把 research / code_assistant 两条任务流做实
- 后面再考虑 subagent 和 Feishu

## 8. 文件级改造模板

### 8.1 必改文件

#### `/home/jiang/project/vd-flow/vdflow/agent/state.py`
目标：从纯聊天状态升级为“线程状态 + 任务流状态容器”。

应完成：
- 新增 `current_task`
- 新增 `task_history`
- 新增 `taskflow_state`
- 定义基础 `TaskflowState`

#### `/home/jiang/project/vd-flow/vdflow/agent/factory.py`
目标：让 Agent runtime 能挂载任务流路由与执行能力。

应完成：
- 保留通用 Lead Agent
- 增加任务流执行入口
- 不把 research prompt 写死为主 prompt

#### `/home/jiang/project/vd-flow/vdflow/agent/middleware.py`
目标：只保留横切关注点。

应承担：
- clarification interrupt
- memory injection
- tool error handling

不应承担：
- 研究流程主逻辑
- 代码任务主逻辑

#### `/home/jiang/project/vd-flow/vdflow/tools/builtins.py`
目标：工具继续做原子动作，不承载完整工作流。

应完成：
- 保留 `ask_clarification`
- 保留文件工具、搜索工具
- 不把“整份研究报告生成逻辑”塞进单工具里

### 8.2 建议新增目录

```text
vdflow/taskflows/
  __init__.py
  base.py
  registry.py
  router.py
  research.py
  code_assistant.py
  writing.py
```

### 8.3 各文件职责

#### `vdflow/taskflows/base.py`
定义：
- TaskFlow 抽象接口
- Phase 枚举
- 输入输出约定

#### `vdflow/taskflows/registry.py`
定义：
- 任务流注册
- 名称到实现的映射

#### `vdflow/taskflows/router.py`
定义：
- 从用户意图到 `task_type`
- 从 `task_type` 到 taskflow

#### `vdflow/taskflows/research.py`
定义：
- ResearchState
- 阶段推进逻辑
- 报告产出

#### `vdflow/taskflows/code_assistant.py`
定义：
- CodeAssistantState
- inspect/plan/patch/verify 流程

#### `vdflow/taskflows/writing.py`
定义：
- 文档整理与写作流

## 9. MVP 执行阶段

### 阶段 A：通用主 Agent 去垂直化
目标：先把“研究助手身份”从主入口中剥离。

任务：
- 清理主 prompt 中默认研究导向表述
- 将 `quick_research` 从默认主路径降级为可选能力
- 明确 Lead Agent 的通用职责

完成标准：
- 主 Agent 面对普通聊天、代码问题、写作需求时不会默认进入 research 模式

### 阶段 B：引入 TaskFlow 基础设施
目标：建立“任务流”这一层，而不是继续靠 skills 拼。

任务：
- 新建 `taskflows/`
- 定义 `TaskFlow` 抽象
- 建立 router
- 在线程状态中加入 taskflow_state

完成标准：
- 系统可以显式知道“当前正在跑哪个任务流、跑到哪个阶段”

### 阶段 C：落地第一个强任务流 `research`
目标：保住你现在已有优势，但改成可控结构。

任务：
- 把 research 拆成 5-6 个阶段
- 建立中间证据状态
- 让输出依赖中间状态而不是一次性生成

完成标准：
- 同一研究请求可以看到阶段推进
- 生成报告前能拿到 sources / evidence / outline

### 阶段 D：落地第二个任务流 `code_assistant`
目标：验证这套架构不是只适用于 research。

任务：
- 增加 inspect / patch / verify 流
- 输出 changed_files 和验证结果

完成标准：
- 用户提出代码分析或改造请求时，系统进入 code_assistant 流

### 阶段 E：统一 Web 交互语义
目标：前端不再只展示纯消息，而能显示任务状态。

任务：
- 暴露当前任务流名称
- 暴露阶段状态
- 暴露中间产物摘要

完成标准：
- Web 层能看到 `task_type` 和 `phase`

## 10. 每阶段验收标准

### A 阶段验收
- 主 prompt 不再把系统默认定义为研究助手
- 普通对话请求不会误入研究流

### B 阶段验收
- `ThreadState` 中有显式任务流状态
- 新增 `taskflows/` 目录和注册机制

### C 阶段验收
- `research` 流最少有 4 个阶段
- 研究结果能追溯到来源
- 报告不再完全靠一次性生成

### D 阶段验收
- `code_assistant` 能输出结构化结果
- 至少能覆盖“分析代码”和“修改代码”两类请求

### E 阶段验收
- `/api/chat` 或 `/api/chat/stream` 能返回任务流元信息
- 前端可展示任务阶段

## 11. 风险与约束

### 11.1 最大风险
把“任务流”继续做成 prompt 约定，而不是 runtime 结构。

如果这样做，看起来像完成了，实际上没有：
- 不可验证
- 不可恢复
- 不可复用
- 之后接 Feishu 会更难

### 11.2 第二风险
一开始做太多任务流。

MVP 正确数量是 2 到 3 个，不是 8 个。

### 11.3 第三风险
过早做 subagent。

没有稳定任务流之前，subagent 只会放大噪声。

## 12. 推荐的首个交付范围

MVP 第一版只做这些：
- 通用 Lead Agent
- TaskFlow Registry
- `research` 任务流
- `code_assistant` 任务流
- 前端展示 `task_type + phase`

先不要做：
- 多 Agent
- Feishu
- MCP
- Docker
- 复杂记忆

## 13. 里程碑模板

### Milestone 1
主题：主 Agent 去研究化
输出：通用主 prompt + 简单路由

### Milestone 2
主题：TaskFlow 基础设施
输出：taskflows 目录、注册器、状态模型

### Milestone 3
主题：Research TaskFlow
输出：可控研究流程与中间状态

### Milestone 4
主题：Code Assistant TaskFlow
输出：第二条可复用垂直任务流

### Milestone 5
主题：Web 状态可视化
输出：前端可见的任务阶段

## 14. 执行顺序建议

严格按这个顺序推进：
1. 去掉主 Agent 的研究身份
2. 建立任务流抽象层
3. 先把 research 流结构化
4. 再做 code_assistant 流
5. 最后才让 Web 展示任务状态
6. 后续再考虑 Feishu 接入

## 15. 一句话判断标准

如果改完以后，系统仍然要靠主 prompt 去“记住自己现在在做研究”，那这次改造就是失败的。

如果改完以后，系统可以明确回答：
- 当前是什么任务流
- 当前在哪个阶段
- 中间结果是什么
- 为什么可以进入下一阶段

那这个 MVP 方向就是对的。
