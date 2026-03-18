"use client";

import React, { useState, useMemo, useEffect } from "react";
import { DashboardContext, type DashboardContextValue } from "@/lib/store";
import { useProjects } from "@/lib/use-projects";
import type { SatelliteLayer } from "@/lib/types";

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const { projects, isLoading, error } = useProjects();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [currentMonth, setCurrentMonth] = useState<string>("");
  const [activeLayer, setActiveLayer] = useState<SatelliteLayer>("sentinel-2");

  // Select the first project once data loads
  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
      setCurrentMonth(projects[0].financials.at(-1)?.month ?? "2025-01");
    }
  }, [projects, selectedProjectId]);

  const value = useMemo<DashboardContextValue>(
    () => ({
      projects,
      isLoading,
      error,
      selectedProjectId,
      currentMonth,
      activeLayer,
      selectProject: setSelectedProjectId,
      setMonth: setCurrentMonth,
      setLayer: setActiveLayer,
    }),
    [projects, isLoading, error, selectedProjectId, currentMonth, activeLayer]
  );

  return <DashboardContext value={value}>{children}</DashboardContext>;
}
