# 搭建自定义Agent MVP原型 - 实施计划

## 上下文
用户想要构建一个自己的Agent系统，具有子代理（Sub-Agents）、记忆（Memory）和可扩展技能（Skills）功能。他们希望从MVP原型开始，基于DeerFlow项目的架构设计。用户选择了以下技术路径：
- 技术栈：Python + LangGraph + FastAPI（类似DeerFlow）
- 核心功能：Agent核心 + 记忆系统 + 简单技能系统
- 交互方式：网页界面
- 部署方式：本地运行

这个计划旨在为用户提供一个可快速启动的MVP原型，借鉴DeerFlow的架构但大幅简化复杂性。

## 推荐方案：简化的DeerFlow核心架构

### 架构概览
```
my-agent-mvp/
├── myagent/                  # 核心Python包
│   ├── agent/               # Agent核心实现
│   │   ├── __init__.py
│   │   ├── factory.py       # Agent工厂
│   │   ├── middleware.py    # 基础中间件
│   │   └── state.py         # Agent状态定义
│   ├── memory/              # 记忆系统
│   │   ├── __init__.py
│   │   ├── storage.py       # 记忆存储
│   │   └── updater.py       # 记忆更新逻辑
│   ├── skills/              # 技能系统
│   │   ├── __init__.py
│   │   ├── loader.py        # 技能加载器
│   │   └── registry.py      # 技能注册表
│   ├── tools/               # 工具系统
│   │   ├── __init__.py
│   │   └── builtins.py      # 内置工具
│   ├── config/              # 配置系统
│   │   ├── __init__.py
│   │   └── models.py        # 配置模型
│   └── web/                 # Web界面
│       ├── __init__.py
│       ├── app.py           # FastAPI应用
│       ├── routes.py        # API路由
│       └── static/          # 静态文件
│           └── index.html   # 简单Web界面
├── config.yaml              # 配置文件
├── requirements.txt         # Python依赖
├── README.md               # 项目说明
└── run.py                  # 启动脚本
```

### 核心组件设计

#### 1. Agent核心系统 (简化的LangGraph实现)
借鉴DeerFlow的`lead_agent`但大幅简化：
- **agent.factory.py**: 创建基础Agent的工厂函数
- **agent.state.py**: 仅包含基本状态的ThreadState（消息、工具调用、文件等）
- **agent.middleware.py**: 包含3个核心中间件：
  - **记忆中间件**: 将对话注入到context中
  - **工具错误处理中间ware**: 捕获工具错误
  - **文件上传中间件**: 处理上传的文件

#### 2. 记忆系统 (简化的实现)
- **memory.storage.py**: JSON文件存储，支持基本的记忆结构
- **memory.updater.py**: 简单的LLM调用提取记忆信息
- 记忆结构包括：
  - 用户偏好（preferences）
  - 历史对话摘要（conversation_history）
  - 知识事实（facts）

#### 3. 技能系统 (可扩展但简单)
- **skills.loader.py**: 从目录加载技能文件（.md格式）
- **skills.registry.py**: 技能注册和管理
- 技能格式：Markdown文件，包含YAML frontmatter定义技能元数据
- 技能注入：动态添加到Agent的system prompt中

#### 4. 工具系统
- **tools.builtins.py**: 包含5个核心工具：
  - **web_search**: 简单的网页搜索
  - **read_file**: 读取文件内容
  - **write_file**: 写入文件
  - **execute_command**: 执行bash命令（本地）
  - **ask_clarification**: 请求用户澄清

#### 5. Web界面
- **web.app.py**: FastAPI应用，提供以下API：
  - `POST /api/chat` - 发送消息并获取流式响应
  - `GET /api/threads/{thread_id}` - 获取对话历史
  - `POST /api/upload` - 上传文件
  - `GET /api/skills` - 获取可用技能列表
- **web.static/index.html**: 简单聊天界面（使用htmx或原生JS）

## 实施步骤

### 第1步：项目初始化
1. 创建项目目录结构
2. 配置依赖：`langchain`, `langgraph`, `fastapi`, `uvicorn`, `pydantic`, `openai`
3. 创建基本配置文件和启动脚本

### 第2步：实现核心Agent
1. 创建Agent状态定义（ThreadState）
2. 实现Agent工厂函数（create_agent）
3. 集成基础工具（web_search, file_operations等）
4. 实现记忆中间件（简化版）

### 第3步：实现记忆系统
1. 创建JSON记忆存储
2. 实现记忆提取和更新逻辑
3. 集成到Agent工作流中

### 第4步：实现技能系统
1. 创建技能加载器和注册表
2. 定义技能文件格式
3. 实现技能动态注入

### 第5步：创建Web界面
1. 实现FastAPI后端API
2. 创建简单的前端界面
3. 实现流式响应支持

### 第6步：配置和部署
1. 创建配置文件（config.yaml）
2. 编写启动脚本
3. 编写使用说明文档

## 关键文件路径

### 新文件
1. `myagent/agent/factory.py` - 核心Agent创建逻辑
2. `myagent/agent/state.py` - 状态定义
3. `myagent/memory/storage.py` - 记忆存储
4. `myagent/skills/loader.py` - 技能加载
5. `myagent/web/app.py` - Web服务器
6. `config.yaml` - 配置文件
7. `run.py` - 启动脚本

### 借鉴自DeerFlow的关键模式
1. **Agent创建模式**：参考`backend/packages/harness/deerflow/agents/factory.py`
2. **中间件链模式**：参考`backend/packages/harness/deerflow/agents/lead_agent/agent.py`
3. **记忆系统架构**：参考`backend/packages/harness/deerflow/agents/memory/`
4. **工具系统设计**：参考`backend/packages/harness/deerflow/tools/builtins/`

## 简化点（相对于完整DeerFlow）

### 移除的复杂功能：
1. **子代理系统** - MVP暂时不需要复杂的子代理编排
2. **Docker沙盒** - 使用本地文件系统和命令执行
3. **MCP服务器集成** - 后续扩展时添加
4. **IM通道集成** - 专注Web界面
5. **LangSmith集成** - 简化调试
6. **复杂的中间件链** - 仅保留核心中间件

### 简化的设计：
1. **单一Agent类型** - 不区分lead_agent和subagent
2. **简化的记忆结构** - 不使用复杂的分层记忆
3. **文件系统存储** - 不使用数据库
4. **本地执行** - 不使用容器化执行环境
5. **简单的技能格式** - 纯Markdown格式

## 验证计划

### 端到端测试流程：
1. **环境配置**：
   - 安装依赖：`pip install -r requirements.txt`
   - 配置OpenAI API密钥
   - 启动服务：`python run.py`
2. **功能验证**：
   - 访问Web界面：http://localhost:8000
   - 发送聊天消息
   - 验证记忆功能（多轮对话中记忆信息）
   - 测试工具调用（文件操作、搜索等）
   - 验证技能加载（添加自定义技能）
3. **性能测试**：
   - 并发用户测试
   - 响应时间验证
   - 内存使用检查

### 关键测试点：
1. Agent创建和会话管理
2. 记忆的持久化和检索
3. 技能动态加载和注入
4. 工具的正确调用
5. Web界面的流式响应

## 后续扩展路径

### 阶段2扩展（增强功能）：
1. **子代理系统**：添加基本的任务分解和委派
2. **数据库支持**：添加SQLite/PostgreSQL存储
3. **认证系统**：简单的API密钥验证
4. **Docker支持**：容器化部署

### 阶段3扩展（企业级功能）：
1. **完整子代理系统**：实现复杂的任务编排
2. **MCP集成**：支持模型上下文协议
3. **IM通道集成**：Telegram/Slack支持
4. **LangSmith集成**：添加可观察性

这个MVP设计在保持核心功能的同时大幅简化了实现复杂度，预计可在2-3天内完成基础版本，让您快速体验核心概念并进行后续扩展。