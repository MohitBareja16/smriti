import { useMemo, useState } from "react";
import {
  BookMarked,
  BookOpen,
  CalendarCheck,
  Check,
  FolderLock,
  MessageSquare,
  PanelLeftClose,
  Pencil,
  Search,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import type { HealthStatus, ThreadSummary } from "../types";
import { SmritiLogo } from "./SmritiLogo";

interface SidebarProps {
  open: boolean;
  threads: ThreadSummary[];
  activeThreadId: string | null;
  health: HealthStatus | null;
  onCloseMobile: () => void;
  onNewChat: () => void;
  onSelectThread: (id: string) => void;
  onRenameThread: (id: string, title: string) => Promise<void>;
  onDeleteThread: (id: string) => Promise<void>;
  onOpenVault: () => void;
  onOpenSamarth: () => void;
  onOpenLibrary: (tab: "pyqs" | "syllabus") => void;
}

function groupThreadsByDate(threads: ThreadSummary[]) {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
  const startYesterday = startToday - 86400;
  const startWeek = startToday - 7 * 86400;

  const groups: Array<{ label: string; items: ThreadSummary[] }> = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 Days", items: [] },
    { label: "Older", items: [] },
  ];

  for (const t of threads) {
    const ts = t.updated_at || t.created_at;
    if (ts >= startToday) groups[0].items.push(t);
    else if (ts >= startYesterday) groups[1].items.push(t);
    else if (ts >= startWeek) groups[2].items.push(t);
    else groups[3].items.push(t);
  }
  return groups.filter((g) => g.items.length > 0);
}

export function Sidebar({
  open,
  threads,
  activeThreadId,
  health,
  onCloseMobile,
  onNewChat,
  onSelectThread,
  onRenameThread,
  onDeleteThread,
  onOpenVault,
  onOpenSamarth,
  onOpenLibrary,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return threads;
    return threads.filter((t) => t.title.toLowerCase().includes(q));
  }, [threads, query]);

  const grouped = useMemo(() => groupThreadsByDate(filtered), [filtered]);

  const startRename = (t: ThreadSummary) => {
    setEditingId(t.id);
    setDraftTitle(t.title);
  };

  const commitRename = async (id: string) => {
    const clean = draftTitle.trim();
    setEditingId(null);
    if (clean) {
      await onRenameThread(id, clean);
    }
  };

  if (!open) return null;

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-[264px] shrink-0 flex-col border-r border-white/[0.08] bg-[#171717] text-[#ececec] md:static">
      {/* Top Bar */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <div className="flex items-center gap-2.5 px-1">
          <SmritiLogo size={26} />
          <div className="leading-tight">
            <div className="text-sm font-semibold text-white">Smriti</div>
            <div className="text-[10px] text-neutral-400">DCRUST AI</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onNewChat}
            title="New chat"
            aria-label="New chat"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-300 transition hover:bg-white/[0.08] hover:text-white"
          >
            <SquarePen className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onCloseMobile}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-300 transition hover:bg-white/[0.08] hover:text-white"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center gap-2.5 rounded-lg border border-white/[0.09] bg-[#242424] px-3 py-2 text-xs font-medium text-neutral-100 transition hover:bg-[#2c2c2c]"
        >
          <SquarePen className="h-3.5 w-3.5 text-[#E9A23B]" />
          <span>New chat</span>
        </button>
      </div>

      {/* Quick Tools */}
      <div className="grid grid-cols-2 gap-1.5 px-3 pb-2.5 text-[11px]">
        <button
          type="button"
          onClick={() => {
            onOpenLibrary("pyqs");
            onCloseMobile();
          }}
          className="flex items-center gap-1.5 rounded-lg border border-white/[0.07] bg-[#212121] px-2.5 py-1.5 text-neutral-300 transition hover:bg-[#2a2a2a] hover:text-white"
        >
          <BookOpen className="h-3.5 w-3.5 text-[#E9A23B]" />
          <span className="truncate">PYQs ({health?.pyq_count?.toLocaleString() || "0"})</span>
        </button>
        <button
          type="button"
          onClick={() => {
            onOpenLibrary("syllabus");
            onCloseMobile();
          }}
          className="flex items-center gap-1.5 rounded-lg border border-white/[0.07] bg-[#212121] px-2.5 py-1.5 text-neutral-300 transition hover:bg-[#2a2a2a] hover:text-white"
        >
          <BookMarked className="h-3.5 w-3.5 text-[#5B8FC7]" />
          <span className="truncate">Syllabus ({health?.syllabus_count || "0"})</span>
        </button>
      </div>

      {/* Search Chats */}
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 h-3.5 w-3.5 text-neutral-500" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search recent chats..."
            aria-label="Search recent chats"
            className="w-full rounded-lg border border-white/[0.08] bg-[#212121] py-1.5 pr-2.5 pl-8 text-xs text-neutral-200 placeholder-neutral-500 focus:border-[#5B8FC7] focus:outline-none"
          />
        </div>
      </div>

      {/* Recent Chats List */}
      <div className="scroller min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {grouped.length === 0 ? (
          <div className="px-3 py-6 text-center text-xs text-neutral-500">
            {query ? "No matching chats." : "Your recent conversations will appear here."}
          </div>
        ) : (
          grouped.map((grp) => (
            <div key={grp.label} className="mt-3 first:mt-1">
              <div className="px-2.5 pb-1 text-[11px] font-medium text-neutral-500">{grp.label}</div>
              <div className="space-y-0.5">
                {grp.items.map((t) => {
                  const isActive = t.id === activeThreadId;
                  const isEditing = editingId === t.id;
                  return (
                    <div
                      key={t.id}
                      className={`group flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs transition ${
                        isActive ? "bg-[#2a2a2a] text-white" : "text-neutral-300 hover:bg-white/[0.05]"
                      }`}
                    >
                      <MessageSquare className="h-3.5 w-3.5 shrink-0 text-neutral-500" />
                      {isEditing ? (
                        <div className="flex min-w-0 flex-1 items-center gap-1">
                          <input
                            type="text"
                            autoFocus
                            value={draftTitle}
                            onChange={(e) => setDraftTitle(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") void commitRename(t.id);
                              if (e.key === "Escape") setEditingId(null);
                            }}
                            className="min-w-0 flex-1 rounded bg-[#333333] px-1.5 py-0.5 text-xs text-white focus:outline-none"
                          />
                          <button
                            type="button"
                            onClick={() => void commitRename(t.id)}
                            aria-label="Save title"
                            className="text-emerald-400 hover:text-emerald-300"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                            aria-label="Cancel rename"
                            className="text-neutral-400 hover:text-neutral-200"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => onSelectThread(t.id)}
                            className="min-w-0 flex-1 truncate text-left"
                          >
                            {t.title}
                          </button>
                          <div className="hidden shrink-0 items-center gap-0.5 group-hover:flex group-focus-within:flex">
                            <button
                              type="button"
                              onClick={() => startRename(t)}
                              aria-label="Rename chat"
                              className="rounded p-1 text-neutral-400 hover:bg-white/10 hover:text-white"
                            >
                              <Pencil className="h-3 w-3" />
                            </button>
                            <button
                              type="button"
                              onClick={() => void onDeleteThread(t.id)}
                              aria-label="Delete chat"
                              className="rounded p-1 text-neutral-400 hover:bg-rose-500/20 hover:text-rose-400"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Bottom Vault & Samarth Dock */}
      <div className="space-y-1 border-t border-white/[0.08] p-2.5 text-xs">
        <button
          type="button"
          onClick={onOpenVault}
          className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-neutral-300 transition hover:bg-white/[0.06] hover:text-white"
        >
          <span className="flex items-center gap-2 font-medium">
            <FolderLock className="h-4 w-4 text-[#5B8FC7]" />
            Document Vault
          </span>
          <span className="rounded bg-[#2b2b2b] px-2 py-0.5 font-mono text-[10px] font-semibold text-neutral-200">
            {health?.document_count ?? 0}
          </span>
        </button>

        <button
          type="button"
          onClick={onOpenSamarth}
          className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-neutral-300 transition hover:bg-white/[0.06] hover:text-white"
        >
          <span className="flex items-center gap-2 font-medium">
            <CalendarCheck className="h-4 w-4 text-[#E9A23B]" />
            DCRUST eSamarth
          </span>
          <span
            className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
              health?.samarth_saved ? "bg-emerald-500/15 text-emerald-300" : "bg-[#2b2b2b] text-neutral-400"
            }`}
          >
            {health?.samarth_saved ? "Connected" : "Login"}
          </span>
        </button>
      </div>
    </aside>
  );
}
