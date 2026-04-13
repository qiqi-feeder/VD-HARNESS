# VD-Flow 快速启动指南

## 📦 安装步骤

### 1. 进入项目目录
```bash
cd /home/jiang/project/vd-flow
```

### 2. 创建虚拟环境（推荐）
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

### 4. 配置 API 密钥

复制环境变量示例文件：
```bash
cp .env.example .env
```

编辑 `.env` 文件，添加至少一个模型的 API 密钥：
```bash
# 例如，使用 OpenAI
OPENAI_API_KEY=sk-your-api-key-here
```

或者直接导出环境变量：
```bash
export OPENAI_API_KEY=sk-your-api-key-here
```

### 5. 测试安装
```bash
python test_installation.py
```

### 6. 启动服务
```bash
python run.py
```

### 7. 访问界面
打开浏览器访问：http://localhost:8000

## 🎯 快速测试

### 使用命令行测试
```python
# test_cli.py
from vdflow.config import Config
from vdflow.agent import create_agent
from vdflow.tools import get_builtin_tools
from langchain_core.messages import HumanMessage

# 加载配置
config = Config.from_yaml("config.yaml")

# 创建 agent
tools = get_builtin_tools()
agent = create_agent(config, tools=tools)

# 发送消息
async def chat():
    result = await agent.ainvoke({
        "messages": [HumanMessage(content="Hello! What can you do?")]
    })
    print(result["messages"][-1].content)

import asyncio
asyncio.run(chat())
```

## 🔧 常见问题

### Q: 提示"No models configured"
A: 编辑 `config.yaml`，确保至少有一个模型的配置，并且对应的 API 密钥已设置。

### Q: 导入错误
A: 确保已激活虚拟环境并安装了所有依赖：
```bash
pip install -r requirements.txt
```

### Q: 端口被占用
A: 修改 `config.yaml` 中的 `server.port` 为其他端口。

## 📚 下一步

1. **添加自定义技能**：在 `skills/custom/` 目录下创建新的技能
2. **探索 API**：查看 README.md 了解所有可用的 API 接口
3. **定制配置**：根据需要调整 `config.yaml` 中的各项设置

## 🆘 需要帮助？

- 查看 README.md 获取详细文档
- 查看 MVP_AGENT_IMPLEMENTATION_PLAN.md 了解架构设计
- 参考 DeerFlow 项目获取更多灵感

祝使用愉快！ 🎉
