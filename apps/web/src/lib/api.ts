import type { Message, Session } from "../types/chat";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";

export async function listSessions() {
  return request<{ sessions: Session[] }>("/api/sessions");
}

export async function createSession(title = "New chat") {
  return request<{ session: Session }>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export async function deleteSession(sessionId: string) {
  return request<void>(`/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function listMessages(sessionId: string) {
  return request<{ messages: Message[] }>(`/api/sessions/${sessionId}/messages`);
}

export async function sendUserMessage(sessionId: string, content: string) {
  return request<{ message: Message; messages?: Message[] }>(
    `/api/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ role: "user", content }),
    },
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers,
  });

  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error ?? `Request failed with ${response.status}`);
  }
  return payload as T;
}
