"use client";

import React from "react";
import { useDashboard } from "@/lib/store";
import type { SatelliteLayer } from "@/lib/types";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const layers: { key: SatelliteLayer; label: string }[] = [
  { key: "sentinel-2", label: "S-2" },
  { key: "sentinel-1", label: "S-1" },
  { key: "terrain", label: "Terrain" },
];

export function LayerToggle() {
  const { activeLayer, setLayer } = useDashboard();

  return (
    <div className="absolute top-3 right-3 z-30">
      <Tabs
        value={activeLayer}
        onValueChange={(val) => setLayer(val as SatelliteLayer)}
      >
        <TabsList className="bg-card/90 backdrop-blur border border-border shadow-lg">
          {layers.map((l) => (
            <TabsTrigger
              key={l.key}
              value={l.key}
              className="text-xs font-[var(--font-mono)] tracking-wider uppercase px-3 py-1.5"
            >
              {l.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
    </div>
  );
}
