# VD-Flow 项目概览

## 🎯 项目目标

VD-Flow 是一个轻量级的 AI Agent 框架 MVP，旨在提供一个简单但功能完整的 Agent 系统，具备以下核心能力：

1. **智能对话 Agent** - 基于大语言模型的对话能力
2. **记忆系统** - 持久化存储用户偏好和上下文
3. **技能系统** - 可扩展的功能模块
4. **工具集成** - 内置常用工具（搜索、文件操作等）
5. **Web 界面** - 简洁易用的聊天界面

## 📊 项目统计

- **总文件数**: 24 个核心文件
- **代码行数**: ~2000+ 行
- **核心模块**: 6 个（agent, memory, skills, tools, config, web）
- **支持模型**: 10+ 种主流大模型
- **开发时间**: 约 2-3 小时完成核心框架

## 🏗️ 架构亮点

### 1. 简洁的模块化设计
- **agent/** - Agent 核心实现，使用 LangGraph
- **memory/** - 记忆存储和更新
- **skills/** - 技能加载和管理
- **tools/** - 内置工具集合
- **config/** - 配置管理系统
- **web/** - FastAPI Web 服务

### 2. 借鉴 DeerFlow 但大幅简化
- ✅ 保留核心 Agent 和记忆系统
- ✅ 简化的技能系统
- ✅ 直接的工具集成
- ❌ 移除复杂的子代理编排
- ❌ 移除 Docker 沙盒
- ❌ 移除 MCP 和 IM 集成

### 3. 易于扩展
- 添加新模型：编辑 config.yaml
- 添加新技能：创建 Markdown 文件
- 添加新工具：编写 Python 函数

## 🔧 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| Agent 框架 | LangGraph + LangChain | Agent 编排和工具调用 |
| Web 框架 | FastAPI | REST API 服务 |
| 前端 | HTML/CSS/JavaScript | 聊天界面 |
| 配置管理 | Pydantic + YAML | 配置验证和加载 |
| 存储 | JSON 文件 | 记忆和会话数据 |

## 📈 核心功能流程

```
用户输入 → Web API → Agent 系统
                          ↓
                      工具选择和执行
                          ↓
                      记忆更新
                          ↓
                      响应生成
                          ↓
                    返回给用户
```

## 🎨 特色功能

### 1. 多模型支持
- OpenAI (GPT-4, GPT-4o-mini)
- Anthropic (Claude 3.5)
- Google (Gemini 2.0)
- DeepSeek (R1, V3)
- 国产模型（通义千问、文心一言、GLM等）
- OpenRouter（多模型网关）

### 2. 智能记忆
- 自动提取用户偏好
- 对话历史摘要
- 知识事实存储
- 相似度检索

### 3. 灵活技能
- Markdown 格式定义
- 自动加载和注入
- 启用/禁用控制

### 4. 内置工具
- 网页搜索（DuckDuckGo）
- 文件读写
- Bash 命令执行
- 用户澄清请求

## 🚀 快速开始三步走

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API 密钥
export OPENAI_API_KEY=your-key

# 3. 启动服务
python run.py
```

访问 http://localhost:8000 开始使用！

## 📝 与 DeerFlow 的对比

| 特性 | DeerFlow | VD-Flow |
|------|----------|---------|
| Agent 系统 | ✅ 完整 | ✅ 简化但完整 |
| 子代理 | ✅ 复杂编排 | ❌ 未实现 |
| 记忆系统 | ✅ 分层记忆 | ✅ 简化记忆 |
| 技能系统 | ✅ 完整 | ✅ 核心功能 |
| 沙盒环境 | ✅ Docker | ❌ 本地执行 |
| MCP 集成 | ✅ | ❌ |
| IM 通道 | ✅ 多平台 | ❌ |
| Web 界面 | ✅ Next.js | ✅ 简单 HTML |
| 学习曲线 | 中等 | 简单 |
| 部署复杂度 | 中等 | 简单 |

## 🎓 学习价值

这个 MVP 项目非常适合：
- **初学者**：了解 Agent 系统的核心概念
- **开发者**：快速搭建自己的 Agent 应用
- **研究者**：探索 Agent 架构设计
- **创业者**：快速验证产品想法

## 🔄 扩展路径

### 阶段 2 - 增强功能
- [ ] 简单的子代理系统
- [ ] SQLite 数据库支持
- [ ] 用户认证
- [ ] Docker 部署

### 阶段 3 - 企业级
- [ ] 完整的子代理编排
- [ ] MCP 服务器集成
- [ ] IM 通道支持
- [ ] 可观察性工具

## 💡 使用建议

1. **开发环境**：使用 Python 虚拟环境
2. **API 密钥**：从环境变量读取，不要硬编码
3. **测试工具**：先用 test_installation.py 验证安装
4. **调试模式**：config.yaml 中设置 debug: true

## 🙏 致谢

本项目受到 [DeerFlow](https://github.com/bytedance/deer-flow) 的启发，是一个学习和简化版本。感谢：
- **ByteDance** 的 DeerFlow 团队
- **LangChain** 框架
- **FastAPI** 框架
- 开源社区的所有贡献者

---

**项目地址**: `/home/jiang/project/vd-flow`  
**创建时间**: 2026-04-09  
**版本**: 0.1.0 MVP
