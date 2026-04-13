"use client";

import { Client } from "@langchain/langgraph-sdk";

import type { AgentThreadState } from "@/core/types";
import { getLangGraphApiUrl } from "@/core/api/client";

let client: Client<AgentThreadState> | null = null;

export function getLangGraphClient() {
  if (!client) {
    client = new Client<AgentThreadState>({
      apiUrl: getLangGraphApiUrl(),
      apiKey: null,
    });
  }
  return client;
}
