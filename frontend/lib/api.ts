import type { AuthResponse, PublicConfig, User } from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function apiUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function messageFromDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String((item as { msg: unknown }).msg) : String(item)))
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return "Request failed";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCookie("sf_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { ...init, method, headers, credentials: "include", cache: "no-store" });
  } catch (error) {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE}. Is the backend running? ${error instanceof Error ? error.message : ""}`,
      0,
    );
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : body;
    throw new ApiError(messageFromDetail(detail), response.status, detail);
  }
  return body as T;
}

export const auth = {
  me: () => api<AuthResponse>("/api/auth/me"),
  login: (email: string, password: string) =>
    api<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, display_name: string) =>
    api<AuthResponse>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password, display_name }) }),
  logout: () => api<{ message: string }>("/api/auth/logout", { method: "POST" }),
  updateProfile: (display_name: string) =>
    api<User>("/api/auth/profile", { method: "PATCH", body: JSON.stringify({ display_name }) }),
  changePassword: (current_password: string, new_password: string) =>
    api<{ message: string }>("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  deleteAccount: (password: string) =>
    api<{ message: string }>("/api/auth/account", { method: "DELETE", body: JSON.stringify({ password }) }),
};

export const meta = {
  config: () => api<PublicConfig>("/api/config"),
  health: () => api<Record<string, unknown>>("/api/health"),
};
