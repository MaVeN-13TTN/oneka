"use client";

import React from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import type { FinancialDataPoint } from "@/lib/types";

interface Props {
  financials: FinancialDataPoint[];
  currentMonth: string;
}

function shortMonth(m: string) {
  const [, month] = m.split("-");
  const names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return names[Number(month) - 1] ?? m;
}

export function SpendChart({ financials, currentMonth }: Props) {
  const data = financials.map((f) => ({
    ...f,
    label: shortMonth(f.month),
    disbursedB: Number((f.disbursed / 1_000_000_000).toFixed(2)),
  }));

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 9, fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <YAxis
            yAxisId="money"
            tick={{ fontSize: 9, fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${v}B`}
          />
          <YAxis
            yAxisId="pct"
            orientation="right"
            domain={[0, 100]}
            tick={{ fontSize: 9, fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              fontSize: 10,
              fontFamily: "var(--font-mono)",
            }}
          />
          <Line
            yAxisId="money"
            type="monotone"
            dataKey="disbursedB"
            stroke="var(--oneka-amber)"
            strokeWidth={2}
            dot={false}
            name="Disbursed (B)"
          />
          <Line
            yAxisId="pct"
            type="monotone"
            dataKey="physicalProgress"
            stroke="var(--oneka-green)"
            strokeWidth={2}
            dot={false}
            name="Physical %"
          />
          <Line
            yAxisId="pct"
            type="monotone"
            dataKey="reportedProgress"
            stroke="var(--muted-foreground)"
            strokeWidth={1}
            strokeDasharray="4 2"
            dot={false}
            name="Reported %"
          />
          {currentMonth && (
            <ReferenceLine
              x={shortMonth(currentMonth)}
              yAxisId="pct"
              stroke="var(--oneka-green)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
