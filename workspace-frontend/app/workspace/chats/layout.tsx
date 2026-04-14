"use client";

import { useParams, usePathname } from "next/navigation";

import { ChatScreen } from "@/components/workspace/chat-screen";

export default function ChatsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  const params = useParams<{ threadId?: string }>();

  // Show thread list page when at /workspace/chats exactly
  if (pathname === "/workspace/chats") {
    return <>{children}</>;
  }

  // For /workspace/chats/new and /workspace/chats/[threadId],
  // render ChatScreen directly at the layout level so route changes
  // between new → threadId don't unmount/remount the component.
  const threadId = params.threadId ?? null;
  return <ChatScreen initialThreadId={threadId} />;
}
