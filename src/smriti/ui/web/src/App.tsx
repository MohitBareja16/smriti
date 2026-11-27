import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  ArrowUp,
  CalendarCheck,
  FolderLock,
  PanelLeftOpen,
  Paperclip,
  Square,
} from "lucide-react";
import {
  deleteThread,
  fetchHealth,
  fetchModels,
  fetchThread,
  fetchThreads,
  renameThread,
  selectModel,
  streamChat,
} from "./api";
import { FilePreviewModal } from "./components/FilePreviewModal";
import { LibraryExplorerPage } from "./components/LibraryExplorerPage";
import { MessageList } from "./components/MessageList";
import { SamarthModal } from "./components/SamarthModal";
import { Sidebar } from "./components/Sidebar";
import { VaultModal } from "./components/VaultModal";
import type { ChatMessage, HealthStatus, ModelsInfo, PreviewFile, ThreadSummary } from "./types";

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [models, setModels] = useState<ModelsInfo | null>(null);
  const [activeView, setActiveView] = useState<"chat" | "pyqs" | "syllabus">("chat");
  const [mode, setMode] = useState<"ours" | "agent" | "plain">("ours");
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);

  const [vaultOpen, setVaultOpen] = useState(false);
  const [samarthOpen, setSamarthOpen] = useState(false);
  const [previewFile, setPreviewFile] = useState<PreviewFile | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const refreshSidebar = useCallback(async () => {
    try {
      const [h, t, m] = await Promise.all([fetchHealth(), fetchThreads(), fetchModels()]);
      setHealth(h);
      setThreads(t);
      setModels(m);
    } catch {
      // ignore initial transient errors
    }
  }, []);

  useEffect(() => {
    void refreshSidebar();
  }, [refreshSidebar]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el && autoScrollRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, streaming]);

  const handleNewChat = () => {
    abortRef.current?.abort();
    setStreaming(false);
    setActiveThreadId(null);
    setMessages([]);
    setActiveView("chat");
    textareaRef.current?.focus();
  };

  const handleSelectThread = async (id: string) => {
    abortRef.current?.abort();
    setStreaming(false);
    setActiveThreadId(id);
    setActiveView("chat");
    try {
      const detail = await fetchThread(id);
      setMessages(detail.messages);
    } catch {
      // ignore
    }
  };

  const handleRenameThread = async (id: string, title: string) => {
    await renameThread(id, title);
    await refreshSidebar();
  };

  const handleDeleteThread = async (id: string) => {
    await deleteThread(id);
    if (activeThreadId === id) {
      setActiveThreadId(null);
      setMessages([]);
    }
    await refreshSidebar();
  };

  const normalizeSlashCommand = (raw: string): string | "OPEN_VAULT" | "OPEN_SAMARTH" => {
    const trimmed = raw.trim();
    const low = trimmed.toLowerCase();
    if (low === "/vault" || low === "vault") return "OPEN_VAULT";
    if (low === "/attendance" || low === "/samarth" || low === "/timetable" || low === "/calendar") {
      return low.includes("timetable") || low.includes("calendar")
        ? "Show my Samarth timetable and calendar"
        : "Check my Samarth attendance";
    }
    if (low.startsWith("/pyq")) {
      const rest = trimmed.slice(4).trim();
      return rest ? `Show PYQs for ${rest}` : "Show PYQs for CSE302C";
    }
    if (low.startsWith("/syllabus")) {
      const rest = trimmed.slice(9).trim();
      return rest ? `Show syllabus for ${rest}` : "Give me CSE 3rd year syllabus";
    }
    return trimmed;
  };

  const sendMessage = async (overrideText?: string) => {
    const raw = overrideText ?? input;
    const normalized = normalizeSlashCommand(raw);
    if (normalized === "OPEN_VAULT") {
      setInput("");
      setVaultOpen(true);
      return;
    }
    if (normalized === "OPEN_SAMARTH") {
      setInput("");
      setSamarthOpen(true);
      return;
    }
    if (!normalized || streaming) return;
    setActiveView("chat");

    if (!overrideText) setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const now = Date.now() / 1000;
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: normalized,
      meta: {},
      attachments: [],
      created_at: now,
    };
    const assistantId = `a-${Date.now()}`;
    const assistantPlaceholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      meta: { trace: [] },
      attachments: [],
      created_at: now,
      streaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);
    autoScrollRef.current = true;
    setStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let resolvedTid = activeThreadId || undefined;

    try {
      await streamChat(
        {
          question: normalized,
          thread_id: resolvedTid,
          mode,
          model: models?.backend === "ollama" ? models.current : undefined,
        },
        {
          onThread: (tid) => {
            resolvedTid = tid;
            setActiveThreadId(tid);
          },
          onStepStart: (step) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      meta: {
                        ...m.meta,
                        trace: [
                          ...(m.meta.trace || []),
                          { name: step.name, detail: step.detail || "", ms: 0, status: "running" as const },
                        ],
                      },
                    }
                  : m
              )
            );
          },
          onStep: (step) => {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                const existing = [...(m.meta.trace || [])];
                let idx = -1;
                for (let i = existing.length - 1; i >= 0; i -= 1) {
                  if (existing[i].name === step.name && existing[i].status === "running") {
                    idx = i;
                    break;
                  }
                }
                const finished = { ...step, status: "done" as const };
                if (idx !== -1) existing[idx] = finished;
                else existing.push(finished);
                return { ...m, meta: { ...m.meta, trace: existing } };
              })
            );
          },
          onReset: () => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: "" } : m))
            );
          },
          onToken: (delta) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + delta } : m))
            );
          },
          onDone: (payload) => {
            setActiveThreadId(payload.thread_id);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: payload.text,
                      streaming: false,
                      ui_element: payload.ui_element,
                      attachments: payload.attachments || [],
                      meta: {
                        path: payload.path,
                        intent: payload.intent,
                        confidence: payload.confidence,
                        llm_calls: payload.llm_calls,
                        latency_ms: payload.latency_ms,
                        trace_id: payload.trace_id,
                        citations: payload.citations,
                        trace: payload.trace,
                      },
                    }
                  : m
              )
            );
          },
          onError: (err) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: `⚠️ ${err}`, streaming: false } : m
              )
            );
          },
        },
        ctrl.signal
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `⚠️ ${err instanceof Error ? err.message : "Request failed"}`, streaming: false }
              : m
          )
        );
      } else {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m))
        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      await refreshSidebar();
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  };

  const activeThread = threads.find((t) => t.id === activeThreadId);

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-[#212121] text-[#ececec]">
      <Sidebar
        open={sidebarOpen}
        threads={threads}
        activeThreadId={activeThreadId}
        health={health}
        onCloseMobile={() => setSidebarOpen(false)}
        onNewChat={handleNewChat}
        onSelectThread={(id) => void handleSelectThread(id)}
        onRenameThread={handleRenameThread}
        onDeleteThread={handleDeleteThread}
        onOpenVault={() => setVaultOpen(true)}
        onOpenSamarth={() => setSamarthOpen(true)}
        onOpenLibrary={(tab) => setActiveView(tab)}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        {/* Top Minimal Header */}
        <header className="flex h-13 shrink-0 items-center justify-between border-b border-white/[0.06] px-4">
          <div className="flex min-w-0 items-center gap-2">
            {!sidebarOpen ? (
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open sidebar"
                className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-300 hover:bg-white/10 hover:text-white"
              >
                <PanelLeftOpen className="h-4 w-4" />
              </button>
            ) : null}
            <span className="truncate text-sm font-semibold text-zinc-200">
              {activeThread?.title || "Smriti"}
            </span>
            {health ? (
              <div className="hidden items-center gap-1.5 sm:flex">
                <select
                  aria-label="Reasoning mode"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as "ours" | "agent" | "plain")}
                  className="rounded-lg border border-white/10 bg-[#2a2a2a] px-2 py-1 text-[11px] text-zinc-300 focus:border-[#5B8FC7] focus:outline-none"
                >
                  <option value="ours">S1 + S2 (Fast + Agent)</option>
                  <option value="agent">System 2 Always</option>
                  <option value="plain">Plain RAG</option>
                </select>
                {models?.backend === "ollama" ? (
                  <select
                    aria-label="Ollama model"
                    value={models.current}
                    onChange={(e) => {
                      const next = e.target.value;
                      void selectModel(next).then(() => refreshSidebar());
                    }}
                    className="rounded-lg border border-white/10 bg-[#2a2a2a] px-2 py-1 text-[11px] text-zinc-300 focus:border-[#5B8FC7] focus:outline-none"
                  >
                    {Array.from(
                      new Set([
                        models.current,
                        ...(models.installed || []),
                        ...(models.recommended || []),
                      ])
                    ).map((m) => (
                      <option key={m} value={m}>
                        {m}
                        {models.installed.includes(m) ? "" : " (not pulled)"}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[11px] text-zinc-400">
                    extractive offline
                  </span>
                )}
              </div>
            ) : null}
          </div>

          <div className="flex items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() => setSamarthOpen(true)}
              className="hidden items-center gap-1.5 rounded-lg border border-white/10 bg-[#2a2a2a] px-2.5 py-1.5 font-medium text-neutral-200 hover:bg-[#333333] sm:inline-flex"
            >
              <CalendarCheck className="h-3.5 w-3.5 text-[#E9A23B]" />
              Samarth
            </button>
            <button
              type="button"
              onClick={() => setVaultOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-[#2a2a2a] px-2.5 py-1.5 font-medium text-neutral-200 hover:bg-[#333333]"
            >
              <FolderLock className="h-3.5 w-3.5 text-[#5B8FC7]" />
              <span>Vault ({health?.document_count ?? 0})</span>
            </button>
          </div>
        </header>

        {/* Scrollable Conversation or Explorer Area */}
        <div
          ref={scrollerRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}
          className="scroller min-h-0 flex-1 overflow-y-auto"
        >
          {activeView === "chat" ? (
            <MessageList
              messages={messages}
              health={health}
              onStarterClick={(p) => void sendMessage(p)}
              onPreviewFile={(f) => setPreviewFile(f)}
              onVaultChanged={() => void refreshSidebar()}
              onOpenLibrary={(tab) => setActiveView(tab)}
            />
          ) : (
            <LibraryExplorerPage
              tab={activeView}
              health={health}
              onTabChange={(tab) => setActiveView(tab)}
              onBackToChat={() => setActiveView("chat")}
              onPreviewFile={(f) => setPreviewFile(f)}
              onAskInChat={(p) => {
                setActiveView("chat");
                void sendMessage(p);
              }}
              onVaultChanged={() => void refreshSidebar()}
            />
          )}
        </div>

        {/* Bottom ChatGPT Composer matching original Smriti palette */}
        {activeView === "chat" ? (
          <div className="shrink-0 px-4 pt-2 pb-4">
          <div className="mx-auto w-full max-w-3xl">
            <div className="flex items-end gap-2 rounded-3xl border border-white/[0.08] bg-[#2f2f2f] px-3.5 py-2.5 shadow-lg focus-within:border-white/20">
              <button
                type="button"
                onClick={() => setVaultOpen(true)}
                title="Add documents to Vault"
                aria-label="Add documents to Vault"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-neutral-300 transition hover:bg-white/10 hover:text-white"
              >
                <Paperclip className="h-4 w-4" />
              </button>

              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
                }}
                onKeyDown={handleKeyDown}
                placeholder="Type your message here... (or /pyq, /syllabus, /attendance, /timetable)"
                className="max-h-[180px] min-h-[36px] flex-1 resize-none bg-transparent py-1.5 text-[15px] text-white placeholder-neutral-400 focus:outline-none"
              />

              {streaming ? (
                <button
                  type="button"
                  onClick={() => abortRef.current?.abort()}
                  aria-label="Stop generating"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#e11d48] text-white transition hover:bg-[#be123c]"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  disabled={!input.trim()}
                  onClick={() => void sendMessage()}
                  aria-label="Send message"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#e11d48] text-white transition hover:bg-[#f43f5e] disabled:bg-[#3f3f3f] disabled:text-neutral-500"
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              )}
            </div>
            <div className="mt-1.5 text-center text-[11px] text-neutral-500">
              Private local-first RAG · Personal credentials &amp; documents never leave your machine.
            </div>
          </div>
        </div>
        ) : null}
      </main>

      <VaultModal
        open={vaultOpen}
        onClose={() => setVaultOpen(false)}
        onChanged={() => void refreshSidebar()}
      />

      <SamarthModal
        open={samarthOpen}
        threadId={activeThreadId}
        onClose={() => setSamarthOpen(false)}
        onSynced={async (res) => {
          const now = Date.now() / 1000;
          setActiveThreadId(res.threadId);
          setMessages((prev) => [
            ...prev,
            {
              id: `su-${now}`,
              role: "user",
              content: `Sync Samarth ${res.kind}`,
              meta: {},
              attachments: [],
              created_at: now,
            },
            {
              id: `sa-${now}`,
              role: "assistant",
              content: res.text,
              meta: { path: "S1", intent: "fact_lookup", confidence: 1.0, llm_calls: 0 },
              ui_element: res.ui_element,
              attachments: res.attachments,
              created_at: now,
            },
          ]);
          await refreshSidebar();
        }}
      />

      <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
    </div>
  );
}
