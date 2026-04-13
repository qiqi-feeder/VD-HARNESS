# VD-Flow Workspace Frontend

这是新的 Workspace 前端实现，技术栈为：

- Next.js App Router
- React 19
- Tailwind CSS 4
- TanStack Query
- 现有 FastAPI 后端 API

当前目标是替代旧的 Vite 单页聊天壳，先完成 `workspace` 工作台的现代化重构，不包含 landing/docs/blog。

## 当前已接通能力

- `/workspace`
- `/workspace/chats`
- `/workspace/chats/new`
- `/workspace/chats/[threadId]`
- `/workspace/agents` 占位页
- 流式聊天
- thinking / tool / subtask 展示
- artifact 抽屉
- chats 搜索与线程管理
- settings 壳
- 浏览器后台完成通知

## 本地启动

1. 启动后端 API：

```bash
python run.py
```

2. 在当前目录配置环境变量：

```bash
cp .env.example .env.local
```

默认配置：

```bash
npm run dev
```

3. 打开 [http://localhost:3000/workspace](http://localhost:3000/workspace)

## 构建检查

```bash
npm run lint
npm run build
```

## 目录说明

- `app/`：路由与页面壳
- `components/workspace/`：工作台 UI
- `core/api`：后端 API 适配层
- `core/threads`：线程数据访问
- `core/settings`：线程级 UI 设置持久化
- `design-system/`：`ui-ux-pro-max` 生成的设计系统基线

## 设计系统

设计系统已经落盘：

- `design-system/vd-flow-workspace/MASTER.md`
- `design-system/vd-flow-workspace/pages/workspace-shell.md`
- `design-system/vd-flow-workspace/pages/chat-detail.md`
- `design-system/vd-flow-workspace/pages/artifact-panel.md`
- `design-system/vd-flow-workspace/pages/settings-dialog.md`

后续高保真 UI/UX 升级时，优先读取 page override，再回退到 `MASTER.md`。

## 当前未做

- 完整 agents 产品线
- MCP/tools 真配置页
- memory 导入导出
- 技能启停/安装
- 子 agent 高保真炫酷动效
- landing/docs/blog
