"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkAgentName,
  createAgent,
  deleteAgent,
  fetchAgent,
  fetchAgents,
  updateAgent,
} from "@/core/api/client";
import type { Agent } from "@/core/types";

export function useAgents() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: fetchAgents,
    staleTime: 5_000,
  });
}

export function useAgent(name: string | null) {
  return useQuery({
    queryKey: ["agent", name],
    queryFn: () => fetchAgent(name!),
    enabled: Boolean(name),
  });
}

export function useCheckAgentName() {
  return useMutation({ mutationFn: checkAgentName });
}

export function useCreateAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agent: Agent) => createAgent(agent),
    onSuccess: (agent) => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
      void queryClient.invalidateQueries({ queryKey: ["agent", agent.name] });
    },
  });
}

export function useUpdateAgent(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agent: Partial<Agent>) => updateAgent(name, agent),
    onSuccess: (agent) => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
      void queryClient.invalidateQueries({ queryKey: ["agent", agent.name] });
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteAgent,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}
