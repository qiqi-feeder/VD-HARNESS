#!/usr/bin/env python3
"""简单测试 GLM-5 是否支持思考模式"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# GLM-5 配置
API_KEY = os.getenv("JDCODING_API_KEY", "")
BASE_URL = "https://modelservice.jdcloud.com/coding/openai/v1"
MODEL = "GLM-5"


def test_thinking_mode(enable_thinking: bool) -> dict:
    """测试调用 GLM-5，可选开启思考模式"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": "请仔细思考后回答：37 * 43 等于多少？",
            }
        ],
        "max_tokens": 1024,
    }

    # 开启思考模式
    if enable_thinking:
        payload["thinking"] = {"type": "enabled", "budget_tokens": 1024}

    response = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )

    return {
        "status_code": response.status_code,
        "json": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
    }


def main():
    if not API_KEY:
        print("错误: 请设置 JDCODING_API_KEY 环境变量")
        return

    print("=" * 60)
    print("测试 1: 不开启思考模式")
    print("=" * 60)
    result1 = test_thinking_mode(enable_thinking=False)
    print(f"状态码: {result1['status_code']}")
    print(f"响应: {result1['json']}")

    print("\n等待 5 秒后进行下一次测试...\n")
    time.sleep(5)

    print("=" * 60)
    print("测试 2: 开启思考模式")
    print("=" * 60)
    result2 = test_thinking_mode(enable_thinking=True)
    print(f"状态码: {result2['status_code']}")
    print(f"响应: {result2['json']}")

    # 检测思考内容
    if result2["status_code"] == 200 and isinstance(result2["json"], dict):
        choices = result2["json"].get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            # 检查是否有 reasoning_content 字段（GLM-5 用这个字段）
            if "reasoning_content" in message and message["reasoning_content"]:
                print("\n✅ 检测到思考模式输出!")
                print(f"思考内容: {message['reasoning_content'][:300]}...")
            else:
                print("\n❌ 未检测到独立的思考字段")

            # 对比两次结果
            print("\n" + "=" * 60)
            print("对比分析")
            print("=" * 60)
            if result1["status_code"] == 200 and isinstance(result1["json"], dict):
                msg1 = result1["json"]["choices"][0]["message"]
                msg2 = result2["json"]["choices"][0]["message"]
                usage1 = result1["json"].get("usage", {})
                usage2 = result2["json"].get("usage", {})

                print(f"不开思考模式:")
                print(f"  - content 长度: {len(msg1.get('content', ''))}")
                print(f"  - reasoning_content: {msg1.get('reasoning_content')}")
                print(f"  - tokens: {usage1.get('total_tokens')}")

                print(f"\n开思考模式:")
                print(f"  - content 长度: {len(msg2.get('content', ''))}")
                reasoning = msg2.get('reasoning_content')
                if reasoning:
                    print(f"  - reasoning_content 长度: {len(reasoning)}")
                    print(f"  - reasoning_content 内容: {reasoning[:200]}...")
                else:
                    print(f"  - reasoning_content: None")
                print(f"  - tokens: {usage2.get('total_tokens')}")


if __name__ == "__main__":
    main()
