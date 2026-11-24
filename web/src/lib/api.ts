// Thin, typed wrapper around the local Shipshape API.

import type { Health, Report, ScanSummary } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("Can't reach the Shipshape server. Is `shipshape-api` running?", 0);
  }
  if (!response.ok) {
    let detail = `Request failed (HTTP ${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new ApiError(detail, response.status);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  health: () => request<Health>("/api/health"),
  scans: () => request<ScanSummary[]>("/api/scans"),
  scan: (id: string) => request<ScanSummary>(`/api/scans/${id}`),
  report: (id: string) => request<Report>(`/api/scans/${id}/report`),
  remove: (id: string) => request<void>(`/api/scans/${id}`, { method: "DELETE" }),
  scanPath: (path: string, explain: boolean, maxFindings: number) =>
    request<ScanSummary>("/api/scans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, explain, max_findings: maxFindings }),
    }),
  scanUpload: (file: File, explain: boolean, maxFindings: number) => {
    const form = new FormData();
    form.append("file", file);
    form.append("explain", String(explain));
    form.append("max_findings", String(maxFindings));
    return request<ScanSummary>("/api/scans/upload", { method: "POST", body: form });
  },
};
