import axios from "axios";

// 开发环境：使用 Vite 代理 /api -> 后端（见 vite.config.js），避免未启动后端时出现 net::ERR_CONNECTION_REFUSED
// 生产构建：可设环境变量 VITE_API_BASE，例如 https://your-domain.com
const baseURL =
  import.meta.env.VITE_API_BASE ||
  (import.meta.env.DEV ? "/api" : "http://127.0.0.1:8000");

const api = axios.create({
  baseURL,
  timeout: 60000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** 与 axios 一致的 API 根，用于 fetch 流式请求 */
export function resolveApiUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  if (baseURL.endsWith("/")) return `${baseURL.slice(0, -1)}${p}`;
  return `${baseURL}${p}`;
}

/**
 * SSE 专用 URL。开发环境默认直连后端，避免 Vite /api 代理缓冲导致整段一次性到达。
 * 可选：VITE_STREAM_API_BASE（如与主 API 不同机或端口）
 */
export function resolveSseUrl(path) {
  const p = path.startsWith("/") ? path : `/${path}`;
  const streamBase = import.meta.env.VITE_STREAM_API_BASE?.replace(/\/$/, "");
  if (streamBase) return `${streamBase}${p}`;
  if (import.meta.env.DEV && !import.meta.env.VITE_API_BASE) {
    return `http://127.0.0.1:8000${p}`;
  }
  return resolveApiUrl(path);
}

/**
 * POST 并消费 text/event-stream（后端 data: JSON 行）
 * @param {string} path 如 /chat/ask/stream
 * @param {object} body
 * @param {{ onEvent: (ev: object) => void, signal?: AbortSignal }} opts
 */
export async function postSse(path, body, { onEvent, signal }) {
  const token = localStorage.getItem("token");
  const res = await fetch(resolveSseUrl(path), {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`;
    try {
      const j = await res.json();
      const d = j?.detail;
      if (typeof d === "string") msg = d;
      else if (d?.message) msg = d.message;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error("无法读取流式响应");
  const decoder = new TextDecoder();
  let carry = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    carry += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = carry.indexOf("\n\n")) >= 0) {
      const block = carry.slice(0, sep).trim();
      carry = carry.slice(sep + 2);
      if (!block) continue;
      const lines = block.split("\n");
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (!raw) continue;
        try {
          onEvent(JSON.parse(raw));
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  }
}

export const login = (payload) => api.post("/auth/login", payload);
export const register = (payload) => api.post("/auth/register", payload);
export const me = () => api.get("/auth/me");
export const createSession = (title) => api.post("/sessions", null, { params: { title } });
export const fetchSessions = (page = 1, size = 50) => api.get("/sessions", { params: { page, size } });
export const deleteSession = (id) => api.delete(`/sessions/${id}`);
export const fetchHistory = (sessionId) => api.get(`/chat/history/${sessionId}`);
export const uploadDocs = (formData) => api.post("/documents/upload", formData);
export const fetchDocs = (page = 1, size = 50) => api.get("/documents", { params: { page, size } });
export const deleteDocument = (id) => api.delete(`/documents/${id}`);
export const askQuestion = (sessionId, question) => api.post("/chat/ask", { session_id: sessionId, question });
export const editQuestion = (messageId, question) => api.post("/chat/edit", { message_id: messageId, question });
export const fetchLogs = (page = 1, size = 20) => api.get("/logs", { params: { page, size } });
