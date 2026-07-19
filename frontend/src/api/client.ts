// Tenant-scoped dashboard API client.
// The bearer token encodes the tenant (server-side); the client never sends a tenant id,
// so it can only ever read its own tenant's data.

const TOKEN_KEY = "cg-token";

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem(TOKEN_KEY) ?? "";
  return { Authorization: `Bearer ${token}`, Accept: "application/json" };
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string): Promise<T> {
  const resp = await fetch(`/api/v1/dashboard${path}`, { headers: authHeaders() });
  if (resp.status === 401) throw new ApiError(401, "Not authenticated");
  if (resp.status === 403) throw new ApiError(403, "Insufficient role");
  if (!resp.ok) throw new ApiError(resp.status, `Request failed: ${resp.status}`);
  return (await resp.json()) as T;
}

// --- typed view models -----------------------------------------------------
export interface RepoOverview {
  repo: string;
  reviews: number;
  avg_overall: number;
  open_prs: number;
}
export interface CostAnalytics {
  total_cost_micros: number;
  total_tokens: number;
  reviews: number;
  by_repo: { repo: string; cost_micros: number }[];
}
export interface QualityPoint {
  ts: string;
  overall: number;
  pr: number;
}

export const getOverview = () => api<RepoOverview[]>("/overview");
export const getCost = () => api<CostAnalytics>("/cost");
export const getQualityTimeline = (repo: string) =>
  api<QualityPoint[]>(`/repos/${repo}/quality-timeline`);
