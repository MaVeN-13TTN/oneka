"use client";

import React from "react";
import { useDashboard } from "@/lib/store";
import type { AuditStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";

const statusColor: Record<AuditStatus, string> = {
  green: "bg-emerald-500",
  yellow: "bg-amber-400",
  red: "bg-red-500",
};

const statusLabel: Record<AuditStatus, string> = {
  green: "On Track",
  yellow: "Watch",
  red: "Flagged",
};

const statusBadgeVariant: Record<AuditStatus, "default" | "secondary" | "destructive"> = {
  green: "default",
  yellow: "secondary",
  red: "destructive",
};

function formatKES(n: number) {
  if (n >= 1_000_000_000) return `KES ${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(0)}M`;
  return `KES ${n.toLocaleString()}`;
}

export function ProjectSidebar() {
  const { projects, selectedProjectId, selectProject } = useDashboard();

  return (
    <aside className="w-80 border-r border-border bg-card flex flex-col overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border">
        <h2 className="text-xs tracking-[0.2em] uppercase font-[var(--font-mono)] text-primary font-medium">
          <span className="opacity-50">{"//"}</span> Project List
        </h2>
        <p className="text-[11px] text-muted-foreground mt-0.5">{projects.length} projects</p>
      </div>
      <ScrollArea className="flex-1">
        <div className="py-1">
        {projects.map((p) => {
          const active = p.id === selectedProjectId;
          return (
              <button
                key={p.id}
                onClick={() => selectProject(p.id)}
                className={cn(
                  "w-full text-left px-5 py-3.5 transition-all border-l-2",
                  active
                    ? "bg-primary/10 border-l-primary"
                    : "hover:bg-muted/60 border-l-transparent"
                )}
              >
                <div className="flex items-start gap-2.5 mb-1.5">
                  <Tooltip>
                    <TooltipTrigger>
                      <span
                        className={cn("w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5", statusColor[p.status])}
                      />
                    </TooltipTrigger>
                    <TooltipContent>{statusLabel[p.status]}</TooltipContent>
                  </Tooltip>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "text-sm font-[var(--font-sans)] font-bold truncate",
                        active ? "text-primary" : "text-foreground"
                      )}>
                        {p.name}
                      </span>
                      <Badge
                        variant={statusBadgeVariant[p.status]}
                        className="text-[9px] h-4 px-1.5 flex-shrink-0"
                      >
                        {statusLabel[p.status]}
                      </Badge>
                    </div>
                    <div className="text-xs font-[var(--font-mono)] text-muted-foreground flex justify-between mt-1">
                      <span>{p.id}</span>
                      <span className="font-medium">{formatKES(p.totalAllocation)}</span>
                    </div>
                    <div className="text-xs font-[var(--font-mono)] text-muted-foreground/70 mt-0.5">
                      {p.county} · {p.sector}
                    </div>
                  </div>
                </div>
              </button>
          );
        })}
        </div>
      </ScrollArea>
    </aside>
  );
}
