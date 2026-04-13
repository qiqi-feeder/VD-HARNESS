#!/usr/bin/env python3
"""测试所有 JD 云模型是否支持思考模式"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# JD 云模型配置
API_KEY = os.getenv("JDCODING_API_KEY", "")
BASE_URL = "https://modelservice.jdcloud.com/coding/openai/v1"

# 所有 JD 云模型列表
JD_MODELS = [
    "DeepSeek-V3.2",
    "GLM-5",
    "GLM-4.7",
    "MiniMax-M2.5",
    "Kimi-K2.5",
    "Kimi-K2-Turbo",
    "Qwen3-Coder",
]


def test_model(model: str, enable_thinking: bool) -> dict:
    """测试单个模型"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "请计算 15 + 27 等于多少？",
            }
        ],
        "max_tokens": 512,
    }

    # 开启思考模式
    if enable_thinking:
        payload["thinking"] = {"type": "enabled", "budget_tokens": 1024}

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        return {
            "status_code": response.status_code,
            "json": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
            "error": None,
        }
    except Exception as e:
        return {
            "status_code": None,
            "json": None,
            "error": str(e),
        }


def analyze_response(result: dict) -> dict:
    """分析响应结果"""
    if result["error"]:
        return {"status": "error", "error": result["error"]}

    if result["status_code"] == 429:
        return {"status": "rate_limit", "error": "RPM/TPM 限制"}

    if result["status_code"] and result["status_code"] >= 400:
        error_msg = ""
        if isinstance(result["json"], dict):
            error_msg = result["json"].get("error", {}).get("message", "")
        return {"status": "http_error", "error": f"HTTP {result['status_code']}: {error_msg}"}

    if result["status_code"] == 200 and isinstance(result["json"], dict):
        choices = result["json"].get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            usage = result["json"].get("usage", {})
            reasoning = message.get("reasoning_content")
            return {
                "status": "ok",
                "has_reasoning": reasoning is not None and len(reasoning) > 0,
                "reasoning_preview": reasoning[:100] + "..." if reasoning else None,
                "content_len": len(message.get("content", "")),
                "total_tokens": usage.get("total_tokens", 0),
            }

    return {"status": "unknown", "error": "无法解析响应"}


def main():
    if not API_KEY:
        print("错误: 请设置 JDCODING_API_KEY 环境变量")
        return

    results = []

    print("=" * 80)
    print("JD 云模型思考模式支持测试")
    print("=" * 80)
    print(f"模型数量: {len(JD_MODELS)}")
    print()

    for i, model in enumerate(JD_MODELS):
        print(f"[{i+1}/{len(JD_MODELS)}] 测试模型: {model}")

        # 测试 1: 不开思考模式
        print(f"  - 不开思考模式...", end=" ", flush=True)
        result1 = test_model(model, enable_thinking=False)
        info1 = analyze_response(result1)
        print(f"{info1['status']}")

        time.sleep(3)  # 避免限速

        # 测试 2: 开思考模式
        print(f"  - 开思考模式...", end=" ", flush=True)
        result2 = test_model(model, enable_thinking=True)
        info2 = analyze_response(result2)
        print(f"{info2['status']}")

        results.append({
            "model": model,
            "no_thinking": info1,
            "with_thinking": info2,
        })

        time.sleep(3)  # 避免限速
        print()

    # 打印汇总表格
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    print(f"{'模型':<20} {'不开思考':<15} {'开思考':<15} {'思考模式支持':<15}")
    print("-" * 80)

    for r in results:
        no_thinking_status = r["no_thinking"]["status"]
        with_thinking_status = r["with_thinking"]["status"]
        has_reasoning = r["with_thinking"].get("has_reasoning", False)

        if with_thinking_status == "ok" and has_reasoning:
            support = "✅ 支持"
        elif with_thinking_status == "ok" and not has_reasoning:
            support = "❌ 不支持"
        elif with_thinking_status == "rate_limit":
            support = "⏳ 限速"
        else:
            support = "❓ 未知"

        print(f"{r['model']:<20} {no_thinking_status:<15} {with_thinking_status:<15} {support:<15}")

    # 详细结果
    print("\n" + "=" * 80)
    print("详细结果 (仅展示成功且有思考内容的)")
    print("=" * 80)

    for r in results:
        if r["with_thinking"].get("has_reasoning"):
            print(f"\n模型: {r['model']}")
            print(f"  不开思考 tokens: {r['no_thinking'].get('total_tokens', 'N/A')}")
            print(f"  开思考 tokens: {r['with_thinking'].get('total_tokens', 'N/A')}")
            print(f"  思考内容预览: {r['with_thinking'].get('reasoning_preview', 'N/A')}")


if __name__ == "__main__":
    main()
