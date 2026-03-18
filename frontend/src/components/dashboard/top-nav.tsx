"use client";

import React from "react";
import { Search, Moon, Sun } from "lucide-react";
import { useDashboard } from "@/lib/store";
import { useTheme } from "next-themes";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";

export function TopNav() {
  const { projects, selectProject } = useDashboard();
  const { theme, setTheme } = useTheme();
  const [query, setQuery] = React.useState("");
  const [open, setOpen] = React.useState(false);

  const filtered = query.trim()
    ? projects.filter(
        (p) =>
          p.name.toLowerCase().includes(query.toLowerCase()) ||
          p.id.toLowerCase().includes(query.toLowerCase())
      )
    : [];

  return (
    <header className="flex items-center justify-between h-14 px-5 border-b border-border bg-card z-50 relative">
      {/* Logo */}
      <div className="font-[var(--font-sans)] font-extrabold text-base tracking-widest uppercase text-primary flex-shrink-0">
        ONEKA<span className="text-muted-foreground">.DASH</span>
      </div>

      {/* Search */}
      <div className="relative max-w-lg w-full mx-6">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none z-10" />
        <Input
          type="text"
          placeholder="Search project ID or name…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
          className="pl-9 h-9 text-sm font-[var(--font-mono)] bg-muted/40"
        />
        {open && filtered.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-1.5 border border-border bg-card rounded-lg shadow-xl z-50 overflow-hidden">
            <ScrollArea className="max-h-56">
              {filtered.map((p, i) => (
                <React.Fragment key={p.id}>
                  {i > 0 && <Separator />}
                  <button
                    className="w-full text-left px-3 py-2.5 text-sm hover:bg-muted transition-colors"
                    onMouseDown={() => {
                      selectProject(p.id);
                      setQuery("");
                      setOpen(false);
                    }}
                  >
                    <span className="text-muted-foreground font-[var(--font-mono)] text-xs">{p.id}</span>{" "}
                    <span className="text-foreground font-medium">{p.name}</span>
                  </button>
                </React.Fragment>
              ))}
            </ScrollArea>
          </div>
        )}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
          className="h-9 w-9"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </Button>
        <Avatar>
          <AvatarFallback className="bg-primary/20 text-xs font-bold text-primary">
            AU
          </AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
