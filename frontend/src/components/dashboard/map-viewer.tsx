"use client";

import React from "react";
import { useDashboard } from "@/lib/store";
import { LayerToggle } from "./layer-toggle";
import { TimelineSlider } from "./timeline-slider";
import { Badge } from "@/components/ui/badge";
import { MapPin, Satellite } from "lucide-react";

export function MapViewer() {
  const { projects, selectedProjectId, activeLayer, currentMonth } = useDashboard();
  const project = projects.find((p) => p.id === selectedProjectId);

  return (
    <div className="relative flex-1 bg-background overflow-hidden">
      {/* Subtle grid background */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: "linear-gradient(var(--foreground) 1px, transparent 1px), linear-gradient(90deg, var(--foreground) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Layer controls */}
      <LayerToggle />

      {/* Coordinates badge — top left */}
      {project && (
        <div className="absolute top-3 left-3 z-20">
          <Badge variant="outline" className="text-[11px] font-[var(--font-mono)] gap-1.5 bg-card/80 backdrop-blur">
            <MapPin size={12} />
            {project.center.lat.toFixed(4)}°, {project.center.lng.toFixed(4)}°
          </Badge>
        </div>
      )}

      {/* CesiumJS placeholder */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center space-y-4">
          {/* Crosshair rings */}
          <div className="relative w-32 h-32 mx-auto">
            <div className="absolute inset-0 rounded-full border border-primary/20 animate-pulse" />
            <div className="absolute inset-4 rounded-full border border-primary/10" />
            <div className="absolute inset-0 flex items-center justify-center">
              <Satellite size={28} className="text-primary/40" />
            </div>
            {/* Crosshair lines */}
            <div className="absolute top-1/2 left-0 right-0 h-px bg-primary/10" />
            <div className="absolute left-1/2 top-0 bottom-0 w-px bg-primary/10" />
          </div>

          {project ? (
            <div className="space-y-1">
              <p className="text-base font-[var(--font-sans)] font-bold text-foreground">
                {project.name}
              </p>
              <p className="text-xs font-[var(--font-mono)] text-muted-foreground">
                {activeLayer.toUpperCase()} · {currentMonth}
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Select a project</p>
          )}

          <Badge variant="secondary" className="text-xs font-[var(--font-mono)]">
            CesiumJS viewer will render here
          </Badge>
        </div>
      </div>

      {/* Timeline */}
      <TimelineSlider />
    </div>
  );
}
