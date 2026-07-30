import type { ApiMessage, EventApi } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

const defaultHeaders = {
  "ngrok-skip-browser-warning": "true",
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 400) throw new ApiError(400, "해당 사건 ID를 찾을 수 없습니다.");
    if (res.status === 422) throw new ApiError(422, "요청 값이 올바르지 않습니다.");
    if (res.status === 404) throw new ApiError(404, "해당 기록을 찾을 수 없습니다.");
    throw new ApiError(res.status, "알 수 없는 오류가 발생했습니다.");
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiError(0, "서버가 예상치 못한 응답을 반환했습니다. (JSON이 아님)");
  }

  return res.json();
}

export async function getMessages(): Promise<ApiMessage[]> {
  const res = await fetch(`${BASE_URL}/messages`, { headers: defaultHeaders });
  return handleResponse<ApiMessage[]>(res);
}

export async function getMessageDetail(messageId: string): Promise<ApiMessage> {
  const res = await fetch(`${BASE_URL}/messages/${messageId}`, { headers: defaultHeaders });
  return handleResponse<ApiMessage>(res);
}

export async function getEvents(params?: { sido?: string; limit?: number }): Promise<EventApi[]> {
  const search = new URLSearchParams();
  if (params?.sido) search.set("sido", params.sido);
  if (params?.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  const res = await fetch(`${BASE_URL}/events${qs ? `?${qs}` : ""}`, { headers: defaultHeaders });
  return handleResponse<EventApi[]>(res);
}

export async function getEventDetail(eventId: string): Promise<EventApi & { full_text?: string | null }> {
  const res = await fetch(`${BASE_URL}/events/${eventId}`, { headers: defaultHeaders });
  return handleResponse(res);
}

export interface MessageScorePayload {
  received_at: string;
  raw_text: string;
  detected_urls?: string[];
  url_risk_score: number;
  text_authenticity_score: number;
  device_id?: string;
}

export async function postMessage(payload: MessageScorePayload): Promise<ApiMessage> {
  const res = await fetch(`${BASE_URL}/messages`, {
    method: "POST",
    headers: { ...defaultHeaders, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<ApiMessage>(res);
}

export async function deleteMessage(messageId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/messages/${messageId}`, {
    method: "DELETE",
    headers: defaultHeaders,
  });
  return handleResponse<void>(res);
}

export async function reportMessage(messageId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/messages/${messageId}/report`, {
    method: "PATCH",
    headers: defaultHeaders,
  });
  return handleResponse<void>(res);
}