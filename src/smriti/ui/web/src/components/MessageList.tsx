import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  BookMarked,
  BookOpen,
  CalendarCheck,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Eye,
  FileText,
} from "lucide-react";
import type { ChatMessage, HealthStatus, PreviewFile } from "../types";
import { DcrustElementRenderer } from "./DcrustCards";
import { SmritiLogo } from "./SmritiLogo";

interface MessageListProps {
  messages: ChatMessage[];
  health: HealthStatus | null;
  onStarterClick: (prompt: string) => void;
  onPreviewFile: (file: PreviewFile) => void;
  onVaultChanged?: () => void;
  onOpenLibrary?: (tab: "pyqs" | "syllabus") => void;
}

const STARTERS = [
  {
    icon: CalendarDays,
    color: "text-[#5B8FC7]",
    title: "Samarth Timetable & Calendar",
    prompt: "Show my Samarth timetable and calendar",
  },
  {
    icon: CalendarCheck,
    color: "text-[#34d399]",
    title: "Samarth Attendance (75% Rule)",
    prompt: "Check my Samarth attendance",
  },
  {
    icon: BookOpen,
    color: "text-[#E9A23B]",
    title: "DCRUST PYQs (Subject Search)",
    prompt: "Show PYQs for CSE302C",
  },
  {
    icon: BookMarked,
    color: "text-[#7ab0eb]",
    title: "University Branch Syllabus",
    prompt: "Give me CSE 3rd year syllabus",
  },
];

const RUNNING_HINT: Record<string, string> = {
  "s1.guard.input": "Checking input guardrails…",
  "s1.context": "Resolving conversation context…",
  "s1.router": "Classifying intent (System 1)…",
  "s1.facts_lookup": "Looking up personal facts…",
  "s1.fetch_doc": "Finding matching document…",
  "s1.pyq_lookup": "Searching DCRUST PYQ catalog…",
  "s1.syllabus_lookup": "Searching DCRUST syllabus catalog…",
  escalate: "Escalating to System 2 agent…",
  "s2.context": "Contextualizing follow-up query…",
  "s2.plan": "Planning search queries…",
  "s2.broaden": "Broadening search filters…",
  "s1.guard.chunks": "Filtering retrieved chunks…",
  "s2.answer": "Synthesizing grounded answer…",
  "s1.guard.grounding": "Verifying citations & grounding…",
  "s2.retry": "Retrying wider search…",
  "s1.guard.pii": "Scanning output for PII…",
};

function runningHint(name: string): string {
  if (RUNNING_HINT[name]) return RUNNING_HINT[name];
  if (name.startsWith("s2.tool.")) return `Running ${name.slice(8)}…`;
  return "Running step…";
}

function AssistantTurn({
  msg,
  onPreviewFile,
  onVaultChanged,
  onAskPrompt,
}: {
  msg: ChatMessage;
  onPreviewFile: (file: PreviewFile) => void;
  onVaultChanged?: () => void;
  onAskPrompt?: (prompt: string) => void;
}) {
  const [userTraceToggle, setUserTraceToggle] = useState<boolean | null>(null);
  const [copied, setCopied] = useState(false);

  const trace = msg.meta?.trace || [];
  const path = msg.meta?.path;
  const citations = msg.meta?.citations || [];
  const isStreaming = Boolean(msg.streaming);
  const traceOpen = userTraceToggle !== null ? userTraceToggle : isStreaming;
  const activeStep = [...trace].reverse().find((s) => s.status === "running");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // ignore clipboard errors
    }
  };

  const pathLabel =
    path === "S1"
      ? "⚡ System 1 (fast, no LLM)"
      : path === "S2"
        ? "🧠 System 2 (agent)"
        : path === "BLOCKED"
          ? "🛡 Guardrail blocked"
          : null;

  return (
    <div className="flex gap-3.5 py-5">
      <div className="mt-0.5 shrink-0">
        <SmritiLogo size={26} />
      </div>

      <div className="min-w-0 flex-1 space-y-3">
        {trace.length > 0 || isStreaming ? (
          <div>
            <button
              type="button"
              onClick={() => setUserTraceToggle(!traceOpen)}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-400 transition hover:text-neutral-200"
            >
              {isStreaming ? (
                <span className="h-2 w-2 animate-pulse rounded-full bg-[#e11d48]" aria-hidden="true" />
              ) : null}
              <span>
                {isStreaming
                  ? activeStep
                    ? `Thinking · ${runningHint(activeStep.name)}`
                    : trace.length > 0
                      ? `Thinking · ${trace.length} step${trace.length === 1 ? "" : "s"}…`
                      : "Thinking…"
                  : `Used Thinking · ${path === "S1" ? "System 1" : "System 1 → System 2"} · ${trace.length} step${
                      trace.length === 1 ? "" : "s"
                    }`}
              </span>
              {traceOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>

            {traceOpen && trace.length > 0 ? (
              <div
                tabIndex={0}
                role="region"
                aria-label="Execution trace"
                className="table-wrapper scroller mt-2 rounded-xl border border-white/10 border-l-2 border-l-[#e11d48] bg-[#262626] p-3 text-xs"
              >
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-[11px] text-neutral-400">
                      <th className="py-1.5 pr-4 font-medium">Step</th>
                      <th className="py-1.5 pr-4 font-medium">Decision / detail</th>
                      <th className="py-1.5 text-right font-medium">ms</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {trace.map((st, idx) => {
                      const running = st.status === "running";
                      return (
                        <tr key={`${st.name}-${idx}`}>
                          <td className="py-2 pr-4">
                            <span className="inline-flex items-center gap-1.5 rounded bg-[#383838] px-2 py-0.5 font-mono text-[11px] text-neutral-200">
                              {running ? (
                                <span
                                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#E9A23B]"
                                  aria-hidden="true"
                                />
                              ) : null}
                              {st.name}
                            </span>
                          </td>
                          <td className="py-2 pr-4 text-neutral-200">
                            {running ? (
                              <span className="italic text-neutral-400">{runningHint(st.name)}</span>
                            ) : (
                              st.detail
                            )}
                          </td>
                          <td className="py-2 text-right font-mono text-neutral-400">
                            {running ? "…" : st.ms.toFixed(0)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}

        {msg.ui_element ? (
          <DcrustElementRenderer
            element={msg.ui_element}
            onPreviewFile={onPreviewFile}
            onVaultChanged={onVaultChanged}
            onAskPrompt={onAskPrompt}
          />
        ) : null}

        {!msg.ui_element && msg.content ? (
          <div className="smriti-prose text-[15px] text-[#ececec]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            {msg.streaming ? (
              <span className="ml-1 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-[#E9A23B] align-middle" />
            ) : null}
          </div>
        ) : msg.ui_element && msg.streaming ? (
          <span className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-[#E9A23B]" />
        ) : null}

        {msg.attachments && msg.attachments.length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {msg.attachments.map((att, idx) => (
              <button
                key={`${att.path}-${idx}`}
                type="button"
                onClick={() => onPreviewFile({ name: att.name, url: att.url, ext: att.ext })}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-[#2a2a2a] px-2.5 py-1.5 text-xs font-medium text-neutral-200 transition hover:bg-[#333333]"
              >
                <FileText className="h-3.5 w-3.5 text-[#E9A23B]" />
                <span className="max-w-[210px] truncate">{att.name}</span>
                <Eye className="h-3 w-3 text-neutral-400" />
              </button>
            ))}
          </div>
        ) : null}

        {citations.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5 text-xs text-neutral-300">
            <span className="font-semibold text-neutral-200">Sources:</span>
            <span>{citations.join("; ")}</span>
          </div>
        ) : null}

        {!msg.streaming && msg.content ? (
          <div className="border-t border-white/[0.08] pt-2.5 text-xs text-neutral-400">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                {pathLabel ? <span className="text-neutral-200">{pathLabel}</span> : null}
                {msg.meta?.intent ? (
                  <span>
                    · intent{" "}
                    <code className="rounded bg-[#343434] px-1.5 py-0.5 font-mono text-[11px] text-neutral-200">
                      {msg.meta.intent}
                    </code>
                  </span>
                ) : null}
                {typeof msg.meta?.confidence === "number" ? (
                  <span>· confidence {msg.meta.confidence.toFixed(2)}</span>
                ) : null}
                {typeof msg.meta?.llm_calls === "number" ? <span>· LLM calls {msg.meta.llm_calls}</span> : null}
                {typeof msg.meta?.latency_ms === "number" ? <span>· {msg.meta.latency_ms.toFixed(0)} ms</span> : null}
                {msg.meta?.trace_id ? (
                  <span>
                    · trace{" "}
                    <code className="rounded bg-[#343434] px-1.5 py-0.5 font-mono text-[11px] text-neutral-200">
                      {msg.meta.trace_id.slice(0, 12)}
                    </code>
                  </span>
                ) : null}
              </div>

              <button
                type="button"
                onClick={() => void handleCopy()}
                aria-label="Copy answer"
                className="inline-flex items-center gap-1 rounded p-1 text-neutral-400 transition hover:bg-white/10 hover:text-neutral-200"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function MessageList({
  messages,
  health,
  onStarterClick,
  onPreviewFile,
  onVaultChanged,
  onOpenLibrary,
}: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-4 py-10">
        <div className="mb-4">
          <SmritiLogo size={52} />
        </div>
        <h2 className="text-center text-2xl font-semibold tracking-tight text-white">
          Smriti · Private Academic Memory
        </h2>
        <p className="mt-1.5 max-w-lg text-center text-xs text-neutral-400">
          {health ? (
            <>
              <span className="text-neutral-200">{health.document_count}</span> vault docs ·{" "}
              <span className="text-neutral-200">{health.pyq_count.toLocaleString()}</span> PYQs ·{" "}
              <span className="text-neutral-200">{health.syllabus_count}</span> syllabi · System 1 + LangGraph System 2
            </>
          ) : (
            "Loading workspace..."
          )}
        </p>

        <div className="mt-7 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2">
          {STARTERS.map((s) => {
            const Icon = s.icon;
            const handleClick = () => {
              if (onOpenLibrary && s.title.includes("PYQs")) {
                onOpenLibrary("pyqs");
              } else if (onOpenLibrary && s.title.includes("Syllabus")) {
                onOpenLibrary("syllabus");
              } else {
                onStarterClick(s.prompt);
              }
            };
            return (
              <button
                key={s.title}
                type="button"
                onClick={handleClick}
                className="flex items-start gap-3 rounded-xl border border-white/[0.08] bg-[#2a2a2a] p-3.5 text-left transition hover:border-white/20 hover:bg-[#313131]"
              >
                <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${s.color}`} />
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-neutral-100">{s.title}</div>
                  <div className="mt-0.5 truncate text-[11px] text-neutral-400">
                    {s.title.includes("PYQs") || s.title.includes("Syllabus")
                      ? "Browse, search & index PDFs"
                      : s.prompt}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-4">
      {messages.map((m) =>
        m.role === "user" ? (
          <div key={m.id} className="flex justify-end py-3">
            <div className="max-w-[82%] whitespace-pre-wrap rounded-3xl bg-[#2f2f2f] px-4 py-2.5 text-[15px] leading-relaxed text-[#ececec]">
              {m.content}
            </div>
          </div>
        ) : (
          <AssistantTurn
            key={m.id}
            msg={m}
            onPreviewFile={onPreviewFile}
            onVaultChanged={onVaultChanged}
            onAskPrompt={onStarterClick}
          />
        )
      )}
    </div>
  );
}
