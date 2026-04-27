import type {
  AuditListResponse,
  ChatResponse,
  DemoUserSummary,
  DemoUsersResponse,
  HealthResponse,
  LocalModelsResponse,
  RequestDetail,
  RequestListResponse,
  SwitchLocalModelResponse,
} from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  demoUserId?: string,
): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  headers.set("Content-Type", "application/json");
  if (demoUserId) {
    headers.set("X-Demo-User-Id", demoUserId);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health", { method: "GET" });
}

export async function fetchDemoUsers(): Promise<DemoUsersResponse> {
  return apiFetch<DemoUsersResponse>("/demo/users", { method: "GET" });
}

export async function fetchLocalModels(): Promise<LocalModelsResponse> {
  return apiFetch<LocalModelsResponse>("/demo/local-models", { method: "GET" });
}

export async function switchDemoUser(userId: string): Promise<DemoUserSummary> {
  const payload = await apiFetch<{ active_user: DemoUserSummary }>("/demo/switch-user", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
  return payload.active_user;
}

export async function switchLocalModel(model: string): Promise<SwitchLocalModelResponse> {
  return apiFetch<SwitchLocalModelResponse>("/demo/switch-model", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

export async function sendChat(message: string, demoUserId: string): Promise<ChatResponse> {
  return apiFetch<ChatResponse>(
    "/chat",
    {
      method: "POST",
      body: JSON.stringify({ message }),
    },
    demoUserId,
  );
}

export async function fetchRequests(): Promise<RequestListResponse> {
  return apiFetch<RequestListResponse>("/requests", { method: "GET" });
}

export async function fetchRequest(requestId: string): Promise<RequestDetail> {
  return apiFetch<RequestDetail>(`/requests/${requestId}`, { method: "GET" });
}

export async function fetchAudit(): Promise<AuditListResponse> {
  return apiFetch<AuditListResponse>("/audit", { method: "GET" });
}
