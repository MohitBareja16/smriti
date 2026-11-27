export interface HealthStatus {
  status: string;
  demo_mode: boolean;
  vault_unlocked: boolean;
  llm_backend: string;
  llm_model: string;
  document_count: number;
  thread_count: number;
  pyq_count: number;
  syllabus_count: number;
  samarth_saved: boolean;
}

export interface ThreadSummary {
  id: string;
  title: string;
  message_count: number;
  created_at: number;
  updated_at: number;
}

export interface AttachmentItem {
  name: string;
  path: string;
  url: string;
  ext: string;
  sizeBytes: number;
}

export interface TraceStep {
  name: string;
  detail: string;
  ms: number;
  status?: "running" | "done";
}

export interface UiElementPayload {
  name: "DcrustAttendance" | "DcrustTimetable" | "DcrustPyqs" | "DcrustSyllabus" | string;
  props: Record<string, any>;
}

export interface ChatMessageMeta {
  path?: string;
  intent?: string;
  confidence?: number;
  llm_calls?: number;
  latency_ms?: number;
  trace_id?: string;
  citations?: string[];
  trace?: TraceStep[];
}

export interface ChatMessage {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  meta: ChatMessageMeta;
  ui_element?: UiElementPayload | null;
  attachments: AttachmentItem[];
  created_at: number;
  streaming?: boolean;
}

export interface ThreadDetail {
  thread: ThreadSummary;
  messages: ChatMessage[];
}

export interface VaultDocument {
  id: number;
  title: string;
  doc_type: string;
  kind: string;
  course: string | null;
  semester: number | null;
  sensitive: boolean;
  created_at: number;
}

export interface SamarthCredStatus {
  saved: boolean;
  roll_number: string | null;
  vault_unlocked: boolean;
}

export interface PreviewFile {
  name: string;
  url: string;
  ext?: string;
}

export interface ModelsInfo {
  backend: string;
  current: string;
  installed: string[];
  recommended: string[];
}
