"use client";

import { TopNav } from "@/components/dashboard/top-nav";
import { ProjectSidebar } from "@/components/dashboard/project-sidebar";
import { MapViewer } from "@/components/dashboard/map-viewer";
import { AuditorPanel } from "@/components/dashboard/auditor-panel";
import { useDashboard } from "@/lib/store";

export default function DashboardPage() {
  const { isLoading, error } = useDashboard();

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 mx-auto rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <p className="text-sm font-[var(--font-mono)] text-muted-foreground">Loading projects…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-2 max-w-sm">
          <p className="text-sm font-bold text-destructive">Failed to load projects</p>
          <p className="text-xs text-muted-foreground font-[var(--font-mono)]">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <TopNav />
      <div className="flex flex-1 overflow-hidden">
        <ProjectSidebar />
        <MapViewer />
        <AuditorPanel />
      </div>
    </div>
  );
}
