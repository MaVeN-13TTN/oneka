"use client";

import { useState, useEffect, useCallback } from "react";
import type { Project } from "./types";
import api from "./api";

interface UseProjectsResult {
  projects: Project[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useProjects(): UseProjectsResult {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async (signal?: AbortSignal) => {
    try {
      setIsLoading(true);
      setError(null);
      const { data } = await api.get<Project[]>("/projects", { signal });
      setProjects(data);
    } catch (err) {
      if (signal?.aborted) return;
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to fetch projects");
      }
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchProjects(controller.signal);
    return () => controller.abort();
  }, [fetchProjects]);

  const refetch = useCallback(() => {
    fetchProjects();
  }, [fetchProjects]);

  return { projects, isLoading, error, refetch };
}
