#!/usr/bin/env python3
"""详细测试各模型的思考模式支持情况 - 多种参数组合"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("JDCODING_API_KEY", "")
BASE_URL = "https://modelservice.jdcloud.com/coding/openai/v1"

# 之前测试"不支持"的模型
MODELS_TO_TEST = [
    "MiniMax-M2.5",
    "Kimi-K2-Turbo",
    "Qwen3-Coder",
]

# 多种思考模式参数组合
THINKING_PARAMS = [
    ("无参数", None),
    ("thinking=enabled", {"thinking": {"type": "enabled", "budget_tokens": 1024}}),
    ("enable_thinking=true", {"enable_thinking": True}),
    ("reasoning_effort=high", {"reasoning_effort": "high"}),
]


def test_model(model: str, extra_params: dict | None) -> dict:
    """测试单个模型"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "请详细思考后回答：一个农夫有17只羊，除了9只以外都死了，还剩几只？请一步步思考。"}],
        "max_tokens": 1024,
    }

    if extra_params:
        payload.update(extra_params)

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"raw": response.text}

        result = {
            "status_code": response.status_code,
            "has_reasoning": False,
            "reasoning_content": None,
            "content_len": 0,
            "tokens": 0,
            "error": None,
            "response_keys": list(data.keys()) if isinstance(data, dict) else [],
        }

        if response.status_code == 200 and isinstance(data, dict):
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                result["content_len"] = len(msg.get("content", ""))
                result["tokens"] = data.get("usage", {}).get("total_tokens", 0)
                result["response_keys"] = list(msg.keys())

                # 检查各种可能的思考字段
                for key in ["reasoning_content", "thinking", "reasoning", "thought"]:
                    val = msg.get(key)
                    if val is not None and val != "" and val != [] and val != {}:
                        result["has_reasoning"] = True
                        result["reasoning_content"] = str(val)[:100]
                        result["reasoning_key"] = key
                        break

        elif response.status_code >= 400:
            result["error"] = data.get("error", {}).get("message", str(data))[:100]

        return result

    except Exception as e:
        return {"status_code": None, "error": str(e)}


def main():
    if not API_KEY:
        print("错误: 请设置 JDCODING_API_KEY 环境变量")
        return

    for model in MODELS_TO_TEST:
        print("=" * 80)
        print(f"模型: {model}")
        print("=" * 80)

        for param_name, params in THINKING_PARAMS:
            print(f"\n测试参数: {param_name}")
            result = test_model(model, params)

            if result.get("error"):
                print(f"  错误: {result['error']}")
            else:
                print(f"  状态码: {result['status_code']}")
                print(f"  响应字段: {result.get('response_keys', [])}")
                print(f"  tokens: {result.get('tokens', 0)}")

                if result.get("has_reasoning"):
                    print(f"  ✅ 发现思考字段 '{result.get('reasoning_key')}': {result['reasoning_content']}...")
                else:
                    print(f"  ❌ 未发现独立思考字段")

            time.sleep(2)  # 避免限速

        print()


if __name__ == "__main__":
    main()
