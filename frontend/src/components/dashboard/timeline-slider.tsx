"use client";

import React from "react";
import { useDashboard } from "@/lib/store";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";

export function TimelineSlider() {
  const { projects, selectedProjectId, currentMonth, setMonth } = useDashboard();
  const project = projects.find((p) => p.id === selectedProjectId);
  const months = project?.financials.map((f) => f.month) ?? [];

  const idx = months.indexOf(currentMonth);
  const currentIdx = idx >= 0 ? idx : months.length - 1;

  if (months.length === 0) return null;

  return (
    <div className="absolute bottom-0 left-0 right-0 z-30 bg-card/90 backdrop-blur border-t border-border px-5 py-3">
      <div className="flex items-center gap-4">
        <span className="text-xs font-[var(--font-mono)] text-muted-foreground w-16 flex-shrink-0 tabular-nums">
          {months[0]}
        </span>
        <Slider
          min={0}
          max={months.length - 1}
          value={[currentIdx]}
          onValueChange={(val) => {
            const idx = Array.isArray(val) ? val[0] : val;
            if (idx !== undefined) setMonth(months[idx]);
          }}
          className="flex-1"
        />
        <span className="text-xs font-[var(--font-mono)] text-muted-foreground w-16 text-right flex-shrink-0 tabular-nums">
          {months[months.length - 1]}
        </span>
        <Badge variant="default" className="text-xs font-[var(--font-mono)] font-bold ml-1 tabular-nums">
          {months[currentIdx]}
        </Badge>
      </div>
    </div>
  );
}
