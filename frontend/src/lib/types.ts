// ── Domain types for Oneka dashboard ──

import type { Feature } from "geojson";

export type AuditStatus = "green" | "yellow" | "red";

export interface FinancialDataPoint {
  /** ISO month string, e.g. "2025-01" */
  month: string;
  /** Cumulative budget disbursed in KES */
  disbursed: number;
  /** Estimated physical completion 0–100 */
  physicalProgress: number;
  /** Progress reported by the contractor 0–100 */
  reportedProgress: number;
}

export interface ProjectDocument {
  name: string;
  type: "contract" | "receipt" | "report";
  url: string;
}

export interface Project {
  id: string;
  name: string;
  county: string;
  sector: "roads" | "dams" | "buildings" | "water" | "energy" | "bridges";
  contractor: string;
  startDate: string;
  totalAllocation: number;
  /** GeoJSON Feature for the project boundary */
  boundary: Feature | null;
  /** Centre point for the map camera */
  center: { lat: number; lng: number };
  status: AuditStatus;
  financials: FinancialDataPoint[];
  documents: ProjectDocument[];
}

export type SatelliteLayer = "sentinel-2" | "sentinel-1" | "terrain";
