# JD 云模型思考模式支持情况

> 测试日期：2026-04-10
> 测试环境：京东云模型服务 (modelservice.jdcloud.com)

## 概述

本文档记录 JD 云平台各模型对「思考模式」（Thinking Mode / Deep Reasoning）的支持情况，包括调用参数、响应格式及实际测试结果。

---

## 测试结论汇总

| 模型 | 思考模式支持 | 实现方式 | 推荐使用 |
|------|-------------|---------|---------|
| DeepSeek-V3.2 | ✅ 完整支持 | `reasoning_content` 独立字段 | ✅ |
| GLM-5 | ✅ 完整支持 | `reasoning_content` 独立字段 | ✅ |
| GLM-4.7 | ✅ 完整支持 | `reasoning_content` 独立字段 | ✅ |
| Kimi-K2.5 | ✅ 完整支持 | `reasoning_content` 独立字段 | ✅ |
| MiniMax-M2.5 | ⚠️ 半支持 | 思考混在 content 中 | ❌ |
| Kimi-K2-Turbo | ⚠️ 半支持 | 思考混在 content 中 | ❌ |
| Qwen3-Coder | ❌ 不支持 | 无独立思考输出 | ❌ |

---

## 详细说明

### 完整支持的模型

以下模型通过 `thinking` 参数开启思考模式后，会返回独立的 `reasoning_content` 字段：

- **DeepSeek-V3.2**
- **GLM-5**
- **GLM-4.7**
- **Kimi-K2.5**

#### 调用方式

```python
payload = {
    "model": "GLM-5",  # 或其他支持的模型
    "messages": [
        {"role": "user", "content": "请思考后回答：37 * 43 等于多少？"}
    ],
    "max_tokens": 1024,
    "thinking": {
        "type": "enabled",
        "budget_tokens": 1024
    }
}
```

#### 响应格式

```json
{
    "choices": [{
        "message": {
            "role": "assistant",
            "content": "37 × 43 = 1591",
            "reasoning_content": "用户询问 37 × 43 的结果。我可以使用分配律...(思考过程)"
        }
    }],
    "usage": {
        "total_tokens": 294
    }
}
```

#### 特点

| 字段 | 内容 |
|------|------|
| `content` | 最终答案，简洁清晰 |
| `reasoning_content` | 完整思考过程，可用于展示推理链 |

---

### 半支持的模型

#### MiniMax-M2.5

- **状态**：响应中有 `reasoning_content` 字段，但值始终为 `null`
- **实际行为**：思考内容以特殊格式混在 `content` 中（如 `<tool_call>Write<arg_key>content</arg_key><arg_value>...

---

## 官方文档参考

| 模型厂商 | 文档链接 | 说明 |
|---------|---------|------|
| DeepSeek | https://api-docs.deepseek.com/ | `deepseek-reasoner` 是 DeepSeek-V3.2 的思考模式 |
| 智谱 GLM | https://docs.bigmodel.cn/ | 支持 `thinking` 参数和 `reasoning_content` 字段 |
| Kimi 月之暗面 | https://platform.kimi.com/docs/api/chat | 仅 `kimi-k2.5` 支持思考模式 |
| MiniMax | https://platform.minimaxi.com/ | 暂无独立思考字段文档 |
| 阿里云 Qwen | https://help.aliyun.com/zh/model-studio/ | 暂无思考模式相关参数 |

---

## 测试代码

测试脚本位于 `scripts/test_jd_models_thinking.py`，可直接运行：

```bash
# 确保已设置环境变量
export JDCODING_API_KEY=your_key_here

# 运行测试
python scripts/test_jd_models_thinking.py
```

---

## 建议

1. **需要独立思考输出的场景**：选择 DeepSeek-V3.2、GLM-5、GLM-4.7 或 Kimi-K2.5
2. **需要思考模式但不需要独立字段**：MiniMax-M2.5 和 Kimi-K2-Turbo 可用，但需自行解析 content
3. **代码生成场景**：Qwen3-Coder 本身定位为代码模型，思考模式支持有限

---

## 更新记录

| 日期 | 内容 |
|------|------|
| 2026-04-10 | 初始版本，完成 7 个模型测试 |
