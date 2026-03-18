"use client";

import { createContext, useContext } from "react";
import type { Project, SatelliteLayer } from "./types";

export interface DashboardState {
  projects: Project[];
  isLoading: boolean;
  error: string | null;
  selectedProjectId: string | null;
  /** ISO month string currently selected on the timeline */
  currentMonth: string;
  activeLayer: SatelliteLayer;
}

export interface DashboardActions {
  selectProject: (id: string | null) => void;
  setMonth: (month: string) => void;
  setLayer: (layer: SatelliteLayer) => void;
}

export type DashboardContextValue = DashboardState & DashboardActions;

export const DashboardContext = createContext<DashboardContextValue | null>(null);

export function useDashboard() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used inside DashboardProvider");
  return ctx;
}
