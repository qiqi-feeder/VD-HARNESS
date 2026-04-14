"use client";

import { Command, Menu, PanelLeftClose } from "lucide-react";
import { createContext, useContext, useCallback, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { WorkspaceCommandPalette } from "@/components/workspace/command-palette";
import { SettingsDialog } from "@/components/workspace/settings-dialog";
import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";
import { useGlobalShortcuts } from "@/hooks/use-global-shortcuts";
import { cn } from "@/lib/utils";

type WorkspaceShellContextValue = {
  openSettings: () => void;
  toggleSidebar: () => void;
  sidebarOpen: boolean;
};

const WorkspaceShellContext = createContext<WorkspaceShellContextValue | null>(null);

export function useWorkspaceShell() {
  const value = useContext(WorkspaceShellContext);
  if (!value) {
    throw new Error("useWorkspaceShell must be used inside WorkspaceShell");
  }
  return value;
}

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const handleNewChat = useCallback(() => {
    router.push("/workspace/chats/new");
  }, [router]);

  const shortcuts = useMemo(
    () => [
      { key: "k", meta: true, action: () => setPaletteOpen((v) => !v) },
      { key: ",", meta: true, action: () => setSettingsOpen(true) },
      { key: "b", meta: true, action: () => setSidebarOpen((v) => !v) },
      { key: "n", meta: true, shift: true, action: handleNewChat },
    ],
    [handleNewChat],
  );

  useGlobalShortcuts(shortcuts);

  const contextValue = useMemo<WorkspaceShellContextValue>(
    () => ({
      openSettings: () => setSettingsOpen(true),
      toggleSidebar: () => setSidebarOpen((value) => !value),
      sidebarOpen,
    }),
    [sidebarOpen],
  );

  return (
    <WorkspaceShellContext.Provider value={contextValue}>
      <div className="workspace-bg min-h-screen bg-transparent text-[var(--foreground)]">
        <div className="flex min-h-screen w-full">
          <WorkspaceSidebar open={sidebarOpen} pathname={pathname} onOpenSettings={() => setSettingsOpen(true)} />
          <div className="flex min-w-0 flex-1 flex-col relative">
            <header className="sticky top-0 z-30 px-4 py-1.5 md:py-2">
              <div className="flex min-h-[40px] items-center justify-between gap-3 px-2">
                <div className="flex items-center">
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-xl text-[var(--muted)] hover:text-white hover:bg-white/5 transition-colors"
                    onClick={() => setSidebarOpen((value) => !value)}
                  >
                    {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => setPaletteOpen(true)}
                  className="hidden h-7 items-center gap-1.5 rounded-lg px-2 text-[11px] text-[var(--muted)] hover:text-white hover:bg-white/5 transition-colors md:inline-flex"
                >
                  <Command className="h-3 w-3" />
                  <span className="opacity-60">⌘K</span>
                </button>
              </div>
            </header>

            <main className={cn("flex min-h-0 flex-1 flex-col", pathname === "/workspace/chats" ? "" : "overflow-hidden")}>
              {children}
            </main>
          </div>
        </div>
      </div>

      <WorkspaceCommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} onOpenSettings={() => setSettingsOpen(true)} />
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </WorkspaceShellContext.Provider>
  );
}
