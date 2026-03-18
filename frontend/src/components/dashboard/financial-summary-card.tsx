"use client";

import React from "react";
import type { Project, FinancialDataPoint } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function formatKES(n: number) {
  if (n >= 1_000_000_000) return `KES ${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `KES ${(n / 1_000_000).toFixed(0)}M`;
  return `KES ${n.toLocaleString()}`;
}

interface Props {
  project: Project;
  monthData: FinancialDataPoint;
}

function Row({ label, value, highlight, muted }: { label: string; value: string; highlight?: boolean; muted?: boolean }) {
  return (
    <div className="flex justify-between items-baseline py-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`text-xs font-[var(--font-mono)] tabular-nums ${highlight ? "text-primary font-semibold" : muted ? "text-muted-foreground" : "text-foreground font-medium"}`}>
        {value}
      </span>
    </div>
  );
}

export function FinancialSummaryCard({ project, monthData }: Props) {
  const gap = monthData.reportedProgress - monthData.physicalProgress;

  return (
    <Card size="sm">
      <CardHeader className="pb-1">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm font-[var(--font-sans)] font-bold leading-tight">
            {project.name}
          </CardTitle>
          <Badge variant="outline" className="text-[10px] flex-shrink-0">{project.id}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">{project.contractor}</p>
      </CardHeader>
      <CardContent className="space-y-3 pt-2">
        {/* Financial details */}
        <div className="rounded-md bg-muted/30 px-3 py-2">
          <Row label="Start Date" value={project.startDate} muted />
          <Row label="Total Allocation" value={formatKES(project.totalAllocation)} />
          <Row label="Disbursed" value={formatKES(monthData.disbursed)} />
        </div>

        {/* Progress comparison */}
        <div className="space-y-2">
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-muted-foreground">Reported</span>
              <span className="font-[var(--font-mono)] tabular-nums">{monthData.reportedProgress}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div className="h-full rounded-full bg-muted-foreground/40 transition-all" style={{ width: `${monthData.reportedProgress}%` }} />
            </div>
          </div>
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-muted-foreground">Observed (Satellite)</span>
              <span className="font-[var(--font-mono)] tabular-nums text-primary font-semibold">{monthData.physicalProgress}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${monthData.physicalProgress}%` }} />
            </div>
          </div>
          {gap > 10 && (
            <p className="text-[11px] text-destructive font-medium">
              ▲ {gap}% discrepancy between reported &amp; observed
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
