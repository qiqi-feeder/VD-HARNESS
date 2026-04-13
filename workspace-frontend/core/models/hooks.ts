"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchModels } from "@/core/api/client";

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: fetchModels,
    staleTime: 30_000,
  });
}
