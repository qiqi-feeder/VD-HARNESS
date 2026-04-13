# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules
以第一性原理！从原始需求和问题本质出发，不从惯例或模板出发。
不要假设我清楚自己想要什么。动机或目标不清晰时，停下来讨论。
目标清晰但路径不是最短的，直接告诉我并建议更好的办法。
遇到问题追根因，不打补丁。每个决策都要能回答"为什么"。
输出说重点，砍掉一切不改变决策的信息。
用中文回复

## Project Overview

VD-Flow is a lightweight AI Agent framework MVP inspired by DeerFlow. It provides a simplified but complete Agent system with memory and skills capabilities, built on LangGraph and LangChain.

## Commands

### Setup and Installation
```bash
# Create and activate virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure API keys (copy and edit .env)
cp .env.example .env
# Or export directly:
export OPENAI_API_KEY=your-key-here
```

### Running the Application
```bash
# Test installation
python test_installation.py

# Start the web server
python run.py

# Server runs at http://localhost:8000 by default
```

### Configuration
- Edit `config.yaml` to configure models, memory, skills, and server settings
- Environment variables can be referenced as `$VAR_NAME` in config.yaml
- The `use` field format: `"package_name.module_name:ClassName"` for dynamic model loading

## Architecture

### Core Modules (vdflow/)

**agent/** - Agent implementation using LangGraph
- `factory.py`: Creates agents with models and tools via `create_agent()` and `create_chat_model()`
- Dynamic model loading from configuration via the `use` field pattern

**config/** - Configuration management
- `models.py`: Pydantic models for all configuration sections (models, memory, skills, tools, server)
- `Config.from_yaml()` loads and expands environment variables

**memory/** - Persistent memory system
- `storage.py`: File-based JSON storage for user preferences, conversation history, and knowledge facts
- Memory is automatically loaded/saved and can be injected into agent prompts

**skills/** - Skills system
- `loader.py`: Loads skills from Markdown files with YAML frontmatter
- Skills defined in `skills/public/` and `skills/custom/` directories
- Each skill is a `SKILL.md` file with frontmatter metadata

**tools/** - Built-in tools
- `builtins.py`: Web search (DuckDuckGo), file read/write, bash execution, clarification requests
- Tools are LangChain `@tool` decorated functions

**web/** - FastAPI web interface
- `app.py`: REST API endpoints for chat, models, skills, and memory
- `static/`: HTML/CSS/JS frontend

### Data Flow
```
User Request → FastAPI (/api/chat) → Agent (LangGraph) → Tools → Memory Update → Response
```

### Adding New Components

**Adding a new model**: Add entry to `models` list in config.yaml with `use` path pointing to the LangChain chat model class

**Adding a new skill**: Create `skills/custom/<skill-name>/SKILL.md` with YAML frontmatter (name, description, enabled) followed by Markdown content

**Adding a new tool**: Create a `@tool` decorated function in `vdflow/tools/builtins.py` and add to `BUILTIN_TOOLS` list

## Model Configuration Pattern

Models use dynamic loading via the `use` field:
```yaml
- name: gpt-4o-mini
  use: langchain_openai:ChatOpenAI
  model: gpt-4o-mini
  api_key: $OPENAI_API_KEY
```

The factory parses `use` as `module_path:ClassName` and dynamically imports and instantiates the class with the remaining config fields as kwargs.

## Supported Model Providers

OpenAI, Anthropic (Claude), Google (Gemini), DeepSeek, Kimi/Moonshot, OpenRouter, Zhipu (GLM), Alibaba (Qwen/DashScope), Baidu (ERNIE), MiniMax, and local vLLM servers.
