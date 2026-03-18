"use client";

import React from "react";
import { useDashboard } from "@/lib/store";
import { SpendChart } from "./spend-chart";
import { FinancialSummaryCard } from "./financial-summary-card";
import { FileText, Receipt, ClipboardList, TriangleAlert } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

const docIcon = {
  contract: FileText,
  receipt: Receipt,
  report: ClipboardList,
} as const;

export function AuditorPanel() {
  const { projects, selectedProjectId, currentMonth } = useDashboard();
  const project = projects.find((p) => p.id === selectedProjectId);

  if (!project) {
    return (
      <aside className="w-[22rem] border-l border-border bg-card flex items-center justify-center">
        <div className="text-center space-y-2">
          <div className="text-3xl">📋</div>
          <p className="text-sm text-muted-foreground">Select a project to audit</p>
        </div>
      </aside>
    );
  }

  const monthData = project.financials.find((f) => f.month === currentMonth) ?? project.financials.at(-1)!;
  const hasFlag = monthData.reportedProgress - monthData.physicalProgress > 20;

  return (
    <aside className="w-[22rem] border-l border-border bg-card flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-border flex items-center justify-between">
        <h2 className="text-xs tracking-[0.2em] uppercase font-[var(--font-mono)] text-primary font-medium">
          <span className="opacity-50">{"//"}</span> Auditor&apos;s Panel
        </h2>
        {hasFlag && (
          <span className="flex items-center gap-1.5 text-[11px] text-destructive font-medium">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-destructive opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-destructive" />
            </span>
            Flag
          </span>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="px-5 py-4 space-y-5">
          {/* Financial Summary Card */}
          <FinancialSummaryCard project={project} monthData={monthData} />

          {/* Spend vs Progress Chart */}
          <div>
            <h3 className="text-xs tracking-[0.12em] uppercase font-[var(--font-mono)] text-muted-foreground mb-3 font-medium">
              Spend vs. Progress
            </h3>
            <SpendChart financials={project.financials} currentMonth={currentMonth} />
          </div>

          {/* Audit discrepancy highlight */}
          {hasFlag && (
            <Alert variant="destructive" className="border-destructive/30 bg-destructive/5">
              <TriangleAlert className="h-4 w-4" />
              <AlertTitle className="text-xs uppercase tracking-[0.12em] font-[var(--font-mono)] font-semibold">
                Audit Flag
              </AlertTitle>
              <AlertDescription className="text-sm leading-relaxed mt-1">
                Disbursement exceeds physical progress by{" "}
                <strong className="text-foreground">
                  {monthData.reportedProgress - monthData.physicalProgress}%
                </strong>
                . Reported: {monthData.reportedProgress}% · Observed: {monthData.physicalProgress}%.
              </AlertDescription>
            </Alert>
          )}

          <Separator />

          {/* Documents */}
          <div>
            <h3 className="text-xs tracking-[0.12em] uppercase font-[var(--font-mono)] text-muted-foreground mb-2 font-medium">
              Documents
            </h3>
            <div className="space-y-1">
              {project.documents.map((doc) => {
                const Icon = docIcon[doc.type];
                return (
                  <Button
                    key={doc.name}
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2.5 h-auto py-2 px-2.5"
                    render={<a href={doc.url} />}
                  >
                    <Icon size={14} className="text-muted-foreground shrink-0" />
                    <span className="font-[var(--font-mono)] text-xs">{doc.name}</span>
                  </Button>
                );
              })}
            </div>
          </div>
        </div>
      </ScrollArea>
    </aside>
  );
}
