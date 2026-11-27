import type {
  AttachmentItem,
  HealthStatus,
  ModelsInfo,
  SamarthCredStatus,
  ThreadDetail,
  ThreadSummary,
  TraceStep,
  UiElementPayload,
  VaultDocument,
} from "./types";

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) msg = String(body.detail);
    } catch {
      // ignore non-json errors
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const fetchHealth = () => apiJson<HealthStatus>("/api/health");
export const fetchModels = () => apiJson<ModelsInfo>("/api/models");
export const selectModel = (model: string) =>
  apiJson<{ backend: string; current: string }>("/api/models/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
export const unlockVault = (passphrase: string) =>
  apiJson<{ vault_unlocked: boolean }>("/api/vault/unlock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passphrase }),
  });
export const indexLibraryFile = (path: string, course?: string, kind: "library" | "personal" = "library") =>
  apiJson<{ ok: boolean; doc_id: number; title: string; chunks: number; duplicate: boolean }>(
    "/api/library/index-file",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, course, kind }),
    }
  );
export const searchPyqCatalog = (q = "", limit = 24) =>
  apiJson<{
    catalog_ready: boolean;
    catalog_total_entries?: number;
    total_papers: number;
    ui_element: UiElementPayload;
  }>(`/api/pyqs/search?q=${encodeURIComponent(q)}&limit=${limit}`);
export const searchSyllabusCatalog = (q = "", branch = "", year = "", limit = 100) =>
  apiJson<{
    catalog_ready: boolean;
    catalog_total_entries?: number;
    total_matched: number;
    ui_element: UiElementPayload;
  }>(
    `/api/syllabus/search?q=${encodeURIComponent(q)}&branch=${encodeURIComponent(branch)}&year=${encodeURIComponent(year)}&limit=${limit}`
  );
export const fetchThreads = () => apiJson<ThreadSummary[]>("/api/threads");
export const createThread = (title?: string) =>
  apiJson<ThreadSummary>("/api/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
export const fetchThread = (id: string) => apiJson<ThreadDetail>(`/api/threads/${encodeURIComponent(id)}`);
export const renameThread = (id: string, title: string) =>
  apiJson<ThreadSummary>(`/api/threads/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
export const deleteThread = (id: string) =>
  apiJson<{ deleted: boolean }>(`/api/threads/${encodeURIComponent(id)}`, { method: "DELETE" });

export const fetchVaultDocs = () =>
  apiJson<{ demo_mode: boolean; vault_unlocked: boolean; documents: VaultDocument[] }>("/api/vault/documents");

export const uploadVaultFiles = async (files: FileList | File[]) => {
  const fd = new FormData();
  for (const f of Array.from(files)) {
    fd.append("files", f);
  }
  return apiJson<{ results: Array<{ name: string; ok: boolean; title?: string; error?: string; duplicate?: boolean }> }>(
    "/api/vault/upload",
    { method: "POST", body: fd }
  );
};

export const deleteVaultDoc = (id: number) =>
  apiJson<{ deleted: boolean }>(`/api/vault/documents/${id}`, { method: "DELETE" });

export const fetchSamarthStatus = () => apiJson<SamarthCredStatus>("/api/samarth/credentials");
export const clearSamarthCredentials = () =>
  apiJson<{ cleared: boolean }>("/api/samarth/credentials", { method: "DELETE" });

export const syncSamarth = (
  kind: "attendance" | "timetable",
  payload: { roll_number?: string; password?: string; save_creds?: boolean; thread_id?: string }
) =>
  apiJson<{
    kind: string;
    thread_id?: string;
    text: string;
    ui_element: UiElementPayload;
    attachments: AttachmentItem[];
  }>(`/api/samarth/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export interface StreamCallbacks {
  onThread?: (threadId: string) => void;
  onStepStart?: (step: { name: string; detail?: string }) => void;
  onStep?: (step: TraceStep) => void;
  onToken?: (delta: string) => void;
  onReset?: () => void;
  onDone?: (payload: {
    thread_id: string;
    thread_title: string;
    text: string;
    citations: string[];
    path: string;
    intent: string;
    confidence: number;
    llm_calls: number;
    llm_tokens: number;
    latency_ms: number;
    trace_id: string;
    trace: TraceStep[];
    ui_element?: UiElementPayload | null;
    attachments: AttachmentItem[];
  }) => void;
  onError?: (err: string) => void;
}

export async function streamChat(
  body: { question: string; thread_id?: string; mode?: "ours" | "agent" | "plain"; model?: string },
  cb: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (block: string) => {
    if (!block.trim()) return;
    let evName = "message";
    const dataLines: string[] = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) evName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    const data = JSON.parse(dataLines.join("\n"));
    if (evName === "thread") cb.onThread?.(data.thread_id);
    else if (evName === "step_start") cb.onStepStart?.(data);
    else if (evName === "step") cb.onStep?.(data);
    else if (evName === "token") cb.onToken?.(data.delta);
    else if (evName === "reset") cb.onReset?.();
    else if (evName === "done") cb.onDone?.(data);
    else if (evName === "error") cb.onError?.(data.detail || "Request failed");
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx = buffer.indexOf("\n\n");
    while (idx !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      dispatch(chunk);
      idx = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) dispatch(buffer);
}
