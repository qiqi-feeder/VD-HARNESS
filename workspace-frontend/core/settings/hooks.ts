"use client";

import { useEffect, useState } from "react";

import type { ModelInfo, ThreadUISettings } from "@/core/types";

const SETTINGS_PREFIX = "vdflow.workspace.thread-settings.";

const DEFAULT_SETTINGS: ThreadUISettings = {
  modelName: "",
  mode: "pro",
  reasoningEffort: "medium",
};

function readSettings(key: string): ThreadUISettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  const saved = window.localStorage.getItem(`${SETTINGS_PREFIX}${key}`);
  if (!saved) return DEFAULT_SETTINGS;

  try {
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(saved) as Partial<ThreadUISettings>) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function useThreadSettings(threadKey: string, models: ModelInfo[] | undefined) {
  const [settings, setSettings] = useState<ThreadUISettings>(() => readSettings(threadKey));

  useEffect(() => {
    setSettings(readSettings(threadKey));
  }, [threadKey]);

  useEffect(() => {
    if (!models?.length) return;
    const activeModel = models.find((item) => item.name === settings.modelName) ?? models[0];
    if (!activeModel) return;

    const nextSettings: ThreadUISettings = {
      ...settings,
      modelName: activeModel.name,
      mode:
        activeModel.supports_thinking || settings.mode === "flash"
          ? settings.mode
          : "flash",
      reasoningEffort:
        settings.mode === "ultra"
          ? "high"
          : settings.mode === "pro"
            ? "medium"
            : settings.mode === "thinking"
              ? "low"
              : "minimal",
    };

    if (JSON.stringify(nextSettings) !== JSON.stringify(settings)) {
      setSettings(nextSettings);
    }
  }, [models, settings]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(`${SETTINGS_PREFIX}${threadKey}`, JSON.stringify(settings));
  }, [settings, threadKey]);

  return [settings, setSettings] as const;
}

export function usePersistentFlag(key: string, initialValue = false) {
  const [value, setValue] = useState(() => {
    if (typeof window === "undefined") return initialValue;
    const saved = window.localStorage.getItem(key);
    if (saved === "true") return true;
    if (saved === "false") return false;
    return initialValue;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(key, String(value));
  }, [key, value]);

  return [value, setValue] as const;
}
