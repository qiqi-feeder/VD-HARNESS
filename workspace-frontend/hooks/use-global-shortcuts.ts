import { useEffect } from "react";

interface GlobalShortcut {
  key: string;
  meta?: boolean;
  shift?: boolean;
  action: () => void;
}

/**
 * Registers global keyboard shortcuts that fire on `keydown`.
 * Each shortcut is defined by a key, optional meta/shift modifiers, and an action callback.
 */
export function useGlobalShortcuts(shortcuts: GlobalShortcut[]) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const meta = event.metaKey || event.ctrlKey;

      for (const shortcut of shortcuts) {
        const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase();
        const metaMatch = shortcut.meta ? meta : !meta;
        const shiftMatch = shortcut.shift ? event.shiftKey : true;

        if (keyMatch && metaMatch && shiftMatch) {
          event.preventDefault();
          shortcut.action();
          return;
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [shortcuts]);
}
