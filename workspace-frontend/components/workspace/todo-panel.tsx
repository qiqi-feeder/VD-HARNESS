"use client";

import { ListTodo } from "lucide-react";

import type { TodoItem } from "@/core/types";
import { cn } from "@/lib/utils";

export function TodoPanel({ todos }: { todos: TodoItem[] }) {
  if (!todos.length) return null;

  return (
    <div className="surface-subtle flex flex-col gap-3 rounded-[24px] px-4 py-3 md:flex-row md:items-center md:justify-between">
      <div className="inline-flex items-center gap-2 text-sm text-[var(--foreground)]">
        <ListTodo className="h-4 w-4 text-[var(--accent-secondary)]" />
        当前任务清单
      </div>
      <div className="flex flex-1 flex-wrap gap-2 md:justify-end">
        {todos.map((todo, index) => (
          <span
            key={`${todo.content}-${index}`}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs",
              todo.status === "completed" && "bg-[rgba(24,182,164,0.12)] text-[var(--accent-secondary)]",
              todo.status === "in_progress" && "bg-[rgba(255,107,87,0.12)] text-[var(--accent)]",
              todo.status === "pending" && "bg-white/70 text-[var(--muted)]",
            )}
          >
            {todo.content}
          </span>
        ))}
      </div>
    </div>
  );
}
