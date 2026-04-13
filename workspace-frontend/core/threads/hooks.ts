"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteThread, fetchThread, fetchThreads, renameThread } from "@/core/api/client";

export function useThreads(search = "") {
  return useQuery({
    queryKey: ["threads", search],
    queryFn: () => fetchThreads(search),
    staleTime: 5_000,
  });
}

export function useThread(threadId: string | null) {
  return useQuery({
    queryKey: ["thread", threadId],
    queryFn: () => fetchThread(threadId!),
    enabled: Boolean(threadId),
  });
}

export function useRenameThread() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) => renameThread(threadId, title),
    onSuccess: (thread) => {
      void queryClient.invalidateQueries({ queryKey: ["threads"] });
      void queryClient.invalidateQueries({ queryKey: ["thread", thread.id] });
    },
  });
}

export function useDeleteThread() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => deleteThread(threadId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["threads"] });
    },
  });
}
