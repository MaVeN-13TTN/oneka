import api from "@/lib/api";
import type { Project } from "@/lib/types";

export async function getProjects(signal?: AbortSignal): Promise<Project[]> {
  const { data } = await api.get<Project[]>("/projects", { signal });
  return data;
}

export async function getProjectById(
  id: string,
  signal?: AbortSignal
): Promise<Project> {
  const { data } = await api.get<Project>(`/projects/${encodeURIComponent(id)}`, { signal });
  return data;
}

export async function getProjectFinancials(
  id: string,
  signal?: AbortSignal
): Promise<Project["financials"]> {
  const { data } = await api.get<Project["financials"]>(
    `/projects/${encodeURIComponent(id)}/financials`,
    { signal }
  );
  return data;
}

export async function getProjectDocuments(
  id: string,
  signal?: AbortSignal
): Promise<Project["documents"]> {
  const { data } = await api.get<Project["documents"]>(
    `/projects/${encodeURIComponent(id)}/documents`,
    { signal }
  );
  return data;
}
