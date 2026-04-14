"use client";

import { useParams } from "next/navigation";

import { ChatScreen } from "@/components/workspace/chat-screen";

export default function AgentChatsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const params = useParams<{ agentName: string; threadId?: string }>();
  const threadId = params.threadId ?? null;
  const agentName = params.agentName;

  return <ChatScreen initialThreadId={threadId} agentName={agentName} />;
}
