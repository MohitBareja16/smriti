import { useMemo, useState } from "react";
import {
  BookMarked,
  BookOpen,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  Eye,
  FileText,
  FolderOpen,
  GraduationCap,
  Info,
  Sparkles,
  Table2,
} from "lucide-react";
import { indexLibraryFile } from "../api";
import type { PreviewFile, UiElementPayload } from "../types";

function rawPathFromUrl(localUrl?: string): string | null {
  if (!localUrl) return null;
  const idx = localUrl.indexOf("?");
  if (idx === -1) return null;
  return new URLSearchParams(localUrl.slice(idx + 1)).get("path");
}

function IndexRagAction({
  localUrl,
  title,
  course,
  initiallyIndexed,
  onIndexed,
  onAsk,
}: {
  localUrl?: string;
  title: string;
  course?: string;
  initiallyIndexed?: boolean;
  onIndexed?: () => void;
  onAsk?: (prompt: string) => void;
}) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "err">(
    initiallyIndexed ? "done" : "idle"
  );
  const rawPath = rawPathFromUrl(localUrl);
  if (!rawPath) return null;

  const handleIndex = async () => {
    if (state === "busy") return;
    setState("busy");
    try {
      await indexLibraryFile(rawPath, course, "library");
      setState("done");
      onIndexed?.();
    } catch {
      setState("err");
    }
  };

  if (state === "done") {
    return (
      <div className="flex items-center gap-1.5">
        <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/35 bg-emerald-500/15 px-2 py-1 text-xs font-semibold text-emerald-300">
          <CheckCircle2 className="h-3 w-3" /> Indexed
        </span>
        {onAsk ? (
          <button
            type="button"
            onClick={() => onAsk(`Summarize the key topics and important questions from ${title}`)}
            className="inline-flex items-center gap-1 rounded-lg border border-[#E9A23B]/45 bg-[#E9A23B]/15 px-2.5 py-1 text-xs font-semibold text-[#f6c56b] hover:bg-[#E9A23B]/25"
          >
            <Sparkles className="h-3 w-3" /> Ask AI
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => void handleIndex()}
      disabled={state === "busy"}
      className="inline-flex items-center gap-1 rounded-lg border border-[#E9A23B]/40 bg-[#E9A23B]/15 px-2.5 py-1 text-xs font-semibold text-[#f6c56b] transition hover:bg-[#E9A23B]/25 disabled:opacity-50"
    >
      <Sparkles className="h-3 w-3" />
      {state === "busy" ? "Indexing..." : state === "err" ? "Retry Index" : "Index AI"}
    </button>
  );
}

const LEVEL_COLORS: Record<string, { dot: string; text: string; bar: string }> = {
  success: { dot: "#30D158", text: "#4ade80", bar: "#22c55e" },
  warning: { dot: "#FFD60A", text: "#facc15", bar: "#eab308" },
  danger: { dot: "#FF453A", text: "#f87171", bar: "#ef4444" },
};

const TT_PALETTE = [
  { bg: "rgba(91, 143, 199, 0.16)", border: "rgba(91, 143, 199, 0.42)", title: "#a8c7e8", sub: "#7fb0e3", dot: "#5B8FC7" },
  { bg: "rgba(233, 162, 59, 0.16)", border: "rgba(233, 162, 59, 0.42)", title: "#f6c56b", sub: "#e9a23b", dot: "#E9A23B" },
  { bg: "rgba(16, 185, 129, 0.15)", border: "rgba(16, 185, 129, 0.38)", title: "#6ee7b7", sub: "#34d399", dot: "#10b981" },
  { bg: "rgba(225, 29, 72, 0.15)", border: "rgba(225, 29, 72, 0.38)", title: "#fda4af", sub: "#fb7185", dot: "#e11d48" },
  { bg: "rgba(14, 165, 233, 0.15)", border: "rgba(14, 165, 233, 0.38)", title: "#7dd3fc", sub: "#38bdf8", dot: "#0ea5e9" },
  { bg: "rgba(168, 85, 247, 0.15)", border: "rgba(168, 85, 247, 0.38)", title: "#d8b4fe", sub: "#c084fc", dot: "#a855f7" },
];

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY_SHORT = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
const ROW_HEIGHT = 64;
const STATUS_DOT: Record<string, string> = {
  PRESENT: "#10b981",
  ABSENT: "#ef4444",
  LEAVE: "#f59e0b",
};

function mondayOf(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const dow = (dt.getUTCDay() + 6) % 7;
  dt.setUTCDate(dt.getUTCDate() - dow);
  return dt.toISOString().slice(0, 10);
}

function addDays(iso: string, delta: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + delta));
  return dt.toISOString().slice(0, 10);
}

function formatWeekRange(monIso: string, dayCount: number): string {
  const endIso = addDays(monIso, dayCount - 1);
  const [y1, m1, d1] = monIso.split("-").map(Number);
  const [y2, m2, d2] = endIso.split("-").map(Number);
  if (m1 === m2 && y1 === y2) return `${d1} – ${d2} ${MONTHS_SHORT[m2 - 1]} ${y2}`;
  return `${d1} ${MONTHS_SHORT[m1 - 1]} – ${d2} ${MONTHS_SHORT[m2 - 1]} ${y2}`;
}

function fmtHourTick(h: number): string {
  const h12 = h % 12 || 12;
  return `${h12} ${h < 12 ? "AM" : "PM"}`;
}

function AttendanceCard({ props, onPreview }: { props: Record<string, any>; onPreview: (f: PreviewFile) => void }) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const subjects: any[] = props.subjects || [];

  return (
    <div className="my-2 w-full space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#262626] px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">
            <GraduationCap className="h-5 w-5" />
          </div>
          <div>
            <div className="text-base font-bold text-white">{props.semesterLabel}</div>
            <div className="text-xs text-neutral-400">
              Roll No: <span className="font-semibold text-neutral-200">{props.rollNumber}</span> · {props.fetchedAt}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-extrabold text-emerald-400">{props.overallPercentage}</div>
          <div className="text-xs text-neutral-400">
            {props.totalAttended} / {props.totalClasses} classes
          </div>
        </div>
      </div>

      <div className="divide-y divide-white/10 overflow-hidden rounded-xl border border-white/10 bg-[#242424]">
        {subjects.map((subj, idx) => {
          const col = LEVEL_COLORS[subj.statusLevel] || LEVEL_COLORS.success;
          const isOpen = openIdx === idx;
          const pctWidth = Math.max(0, Math.min(100, Math.round(subj.percentage || 0)));
          return (
            <div key={subj.sectionCode || subj.courseCode || idx} className="p-4 transition hover:bg-white/[0.02]">
              <div
                role="button"
                tabIndex={0}
                onClick={() => setOpenIdx(isOpen ? null : idx)}
                onKeyDown={(e) => e.key === "Enter" && setOpenIdx(isOpen ? null : idx)}
                className="flex cursor-pointer items-start justify-between gap-4"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      style={{ backgroundColor: col.dot, boxShadow: `0 0 8px ${col.dot}` }}
                      className="h-2 w-2 shrink-0 rounded-full"
                    />
                    <span className="font-mono text-[11px] tracking-wide text-neutral-400">
                      {subj.sectionCode || subj.courseCode}
                    </span>
                  </div>
                  <div className="text-sm font-bold leading-snug text-white">{subj.displayName}</div>
                  <div style={{ color: col.text }} className="pt-0.5 text-xs font-semibold">
                    {subj.prediction}
                  </div>
                  <div className="space-y-0.5 pt-1 text-xs text-neutral-400">
                    <div>
                      Today&apos;s Schedule: <span className="font-semibold text-neutral-200">{subj.todaySchedule}</span>
                    </div>
                    {subj.lastMarked ? (
                      <div>
                        Last attendance marked on:{" "}
                        <span className="font-semibold text-neutral-200">{subj.lastMarked}</span>
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end">
                  <div style={{ color: col.text }} className="text-xl font-extrabold">
                    {subj.percentageStr}
                  </div>
                  <div className="text-xs font-semibold text-neutral-400">
                    {subj.attended} / {subj.total}
                  </div>
                  <div className="mt-2 flex items-center gap-1 text-xs text-neutral-400">
                    {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    <span>Logs</span>
                  </div>
                </div>
              </div>

              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                <div style={{ width: `${pctWidth}%`, backgroundColor: col.bar }} className="h-full rounded-full" />
              </div>

              {subj.pyqLinks && subj.pyqLinks.length > 0 ? (
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="flex items-center gap-1 font-semibold text-[#E9A23B]">
                    <FileText className="h-3 w-3" /> PYQs:
                  </span>
                  {subj.pyqLinks.slice(0, 6).map((lnk: any, k: number) =>
                    lnk.url?.startsWith("/api/") ? (
                      <button
                        key={k}
                        type="button"
                        onClick={() => onPreview({ name: `${lnk.label}.pdf`, url: lnk.url, ext: "pdf" })}
                        className="rounded border border-white/15 bg-[#2e2e2e] px-2 py-0.5 text-neutral-200 hover:border-[#5B8FC7]"
                      >
                        {lnk.label}
                      </button>
                    ) : (
                      <a
                        key={k}
                        href={lnk.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="rounded border border-white/15 bg-[#2e2e2e] px-2 py-0.5 text-neutral-300 hover:border-[#5B8FC7]"
                      >
                        {lnk.label}
                      </a>
                    )
                  )}
                </div>
              ) : null}

              {isOpen ? (
                <div className="scroller mt-3 max-h-60 divide-y divide-white/5 overflow-y-auto rounded-lg border border-white/10 bg-[#1a1a1a] text-xs">
                  {(subj.entries || []).length === 0 ? (
                    <div className="p-3 text-neutral-400">No individual lecture logs available.</div>
                  ) : (
                    subj.entries.map((row: any, rIdx: number) => (
                      <div key={rIdx} className="grid grid-cols-3 px-3 py-1.5">
                        <span className="text-neutral-200">{row.date}</span>
                        <span className="text-neutral-400">{row.timeSlot || "—"}</span>
                        <span
                          className={`text-right font-semibold ${
                            row.status === "PRESENT" ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {row.status === "PRESENT" ? "● PRESENT" : "○ ABSENT"}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TimetableCard({ props }: { props: Record<string, any> }) {
  const [tab, setTab] = useState<"table" | "calendar">("table");
  const hours: any[] = props.hours || [];
  const days: any[] = props.days || [];
  const subjects: any[] = props.subjects || [];
  const events: any[] = props.events || [];
  const gridStartHour: number = props.gridStartHour ?? (hours.length ? hours[0].hour : 9);
  const gridEndHour: number = props.gridEndHour ?? (hours.length ? hours[hours.length - 1].hour + 1 : 17);
  const calDayCount: number = props.calDayCount || 5;

  const { weeks, defaultWeekIdx } = useMemo(() => {
    const uniq = Array.from(new Set(events.map((e) => mondayOf(e.date)))).sort();
    if (!uniq.length) {
      return { weeks: [mondayOf(new Date().toISOString().slice(0, 10))], defaultWeekIdx: 0 };
    }
    const todayMon = mondayOf(new Date().toISOString().slice(0, 10));
    let idx = uniq.indexOf(todayMon);
    if (idx === -1) {
      idx = uniq.length - 1;
      if (uniq.length > 1) {
        const lastWeekCount = events.filter((e) => mondayOf(e.date) === uniq[idx]).length;
        if (lastWeekCount <= 4) idx = uniq.length - 2;
      }
    }
    return { weeks: uniq, defaultWeekIdx: idx };
  }, [events]);

  const [weekIdx, setWeekIdx] = useState(defaultWeekIdx);
  const activeMonday = weeks[Math.max(0, Math.min(weekIdx, weeks.length - 1))];

  const weekDates = useMemo(
    () =>
      Array.from({ length: calDayCount }, (_, i) => {
        const iso = addDays(activeMonday, i);
        return { iso, label: DAY_SHORT[i], dayNum: Number(iso.split("-")[2]) };
      }),
    [activeMonday, calDayCount]
  );

  const eventsByDate = useMemo(() => {
    const map: Record<string, any[]> = {};
    for (const ev of events) {
      if (!map[ev.date]) map[ev.date] = [];
      map[ev.date].push(ev);
    }
    return map;
  }, [events]);

  const totalHours = Math.max(1, gridEndHour - gridStartHour);
  const bodyHeight = totalHours * ROW_HEIGHT;
  const hourTicks = Array.from({ length: totalHours + 1 }, (_, i) => gridStartHour + i);

  return (
    <div className="my-2 w-full space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#262626] p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#5B8FC7]/35 bg-[#5B8FC7]/15 text-[#7ab0eb]">
            <Calendar className="h-5 w-5" />
          </div>
          <div>
            <div className="text-base font-bold text-white">Timetable</div>
            <div className="text-xs text-neutral-400">
              Roll No. <span className="font-semibold text-neutral-200">{props.rollNumber}</span>
            </div>
            <div className="text-xs font-semibold text-[#7ab0eb]">
              {props.semesterLabel}
              {props.sectionLabel ? ` · ${props.sectionLabel}` : ""}
            </div>
          </div>
        </div>
        <div className="text-xs text-neutral-400">{events.length} sessions indexed</div>
      </div>

      {props.notice ? (
        <div className="flex items-center gap-2.5 rounded-xl border border-[#5B8FC7]/30 bg-[#5B8FC7]/10 px-4 py-2.5 text-xs font-medium text-[#a8c7e8]">
          <Info className="h-4 w-4 shrink-0" />
          <span>{props.notice}</span>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-1 rounded-xl border border-white/10 bg-[#1c1c1c] p-1">
        <button
          type="button"
          onClick={() => setTab("table")}
          className={`flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold tracking-wide transition ${
            tab === "table" ? "border border-white/10 bg-[#2f2f2f] text-white" : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <Table2 className="h-4 w-4" /> TABLE
        </button>
        <button
          type="button"
          onClick={() => setTab("calendar")}
          className={`flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold tracking-wide transition ${
            tab === "calendar" ? "border border-white/10 bg-[#2f2f2f] text-white" : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <Calendar className="h-4 w-4" /> CALENDAR
        </button>
      </div>

      {tab === "table" ? (
        <div className="space-y-3">
          <div
            tabIndex={0}
            role="region"
            aria-label="Weekly timetable table"
            className="table-wrapper scroller rounded-xl border border-white/10 bg-[#242424]"
          >
            <table className="w-full min-w-[780px] border-collapse">
              <thead>
                <tr className="border-b border-white/10 bg-[#2a2a2a]">
                  <th className="w-20 px-3 py-3 text-center text-xs font-bold text-neutral-400">DAY</th>
                  {hours.map((h) => (
                    <th key={h.hour} className="border-l border-white/10 px-2 py-2.5 text-center">
                      <div className="text-xs font-bold text-neutral-100">{h.start}</div>
                      <div className="text-[11px] font-normal text-neutral-400">to {h.end}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {days.map((day) => {
                  const byStart: Record<number, any[]> = {};
                  for (const s of day.slots || []) {
                    if (!byStart[s.startHour]) byStart[s.startHour] = [];
                    byStart[s.startHour].push(s);
                  }
                  const cells = [];
                  let idx = 0;
                  while (idx < hours.length) {
                    const hr = hours[idx].hour;
                    const items = byStart[hr];
                    if (!items || !items.length) {
                      cells.push(<td key={`e-${day.weekday}-${hr}`} className="border-l border-white/5 p-1.5" />);
                      idx += 1;
                      continue;
                    }
                    const span = Math.max(1, Math.min(items[0].span || 1, hours.length - idx));
                    cells.push(
                      <td key={`s-${day.weekday}-${hr}`} colSpan={span} className="border-l border-white/5 p-1.5 align-middle">
                        <div className="space-y-1">
                          {items.map((s, k) => {
                            const pal = TT_PALETTE[(s.colorIndex || 0) % TT_PALETTE.length];
                            return (
                              <div
                                key={`${s.code}-${k}`}
                                style={{ backgroundColor: pal.bg, borderColor: pal.border }}
                                className="flex min-h-[64px] flex-col items-center justify-center rounded-lg border px-2 py-2 text-center"
                              >
                                <div style={{ color: pal.title }} className="text-xs font-bold leading-snug">
                                  {s.name}
                                </div>
                                <div style={{ color: pal.sub }} className="mt-1 text-[11px] font-semibold">
                                  {s.code} · {s.typeShort}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </td>
                    );
                    idx += span;
                  }

                  return (
                    <tr
                      key={day.weekday}
                      className={`border-b border-white/10 last:border-b-0 ${day.isToday ? "bg-[#5B8FC7]/10" : ""}`}
                    >
                      <td className="px-3 py-3 text-center">
                        <div className="text-xs font-extrabold tracking-wide text-neutral-100">{day.label}</div>
                        {day.isToday ? (
                          <span className="mt-1 inline-block rounded-full bg-[#5B8FC7] px-2 py-0.5 text-[10px] font-bold text-white">
                            TODAY
                          </span>
                        ) : null}
                      </td>
                      {day.slots && day.slots.length > 0 ? (
                        cells
                      ) : (
                        <td
                          colSpan={Math.max(1, hours.length)}
                          className="border-l border-white/5 py-5 text-center text-xs italic text-neutral-500"
                        >
                          No classes
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="rounded-xl border border-white/10 bg-[#242424] p-4">
            <div className="mb-3 text-[11px] font-extrabold tracking-widest text-neutral-400">SUBJECTS</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {subjects.map((subj) => {
                const pal = TT_PALETTE[(subj.colorIndex || 0) % TT_PALETTE.length];
                return (
                  <div key={subj.code} className="flex items-start gap-2.5">
                    <span style={{ backgroundColor: pal.dot }} className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" />
                    <div>
                      <div className="text-xs font-bold text-neutral-100">{subj.name}</div>
                      <div className="text-[11px] text-neutral-400">
                        {subj.code} · {subj.typeLabel}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-white/10 bg-[#242424]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={weekIdx <= 0}
                  onClick={() => setWeekIdx((w) => Math.max(0, w - 1))}
                  aria-label="Previous week"
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-white/5 text-neutral-200 hover:bg-white/10 disabled:opacity-35"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  disabled={weekIdx >= weeks.length - 1}
                  onClick={() => setWeekIdx((w) => Math.min(weeks.length - 1, w + 1))}
                  aria-label="Next week"
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-white/5 text-neutral-200 hover:bg-white/10 disabled:opacity-35"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <div>
                <div className="text-sm font-bold text-white">{formatWeekRange(activeMonday, calDayCount)}</div>
                <div className="text-[11px] text-neutral-400">
                  Week {weekIdx + 1} of {weeks.length}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setWeekIdx(defaultWeekIdx)}
              className="rounded-full border border-[#5B8FC7]/40 bg-[#5B8FC7]/15 px-4 py-1 text-[11px] font-bold tracking-wide text-[#a8c7e8] hover:bg-[#5B8FC7]/25"
            >
              TODAY
            </button>
          </div>

          <div tabIndex={0} role="region" aria-label="Weekly calendar" className="table-wrapper scroller">
            <div className="min-w-[780px]">
              <div
                style={{ gridTemplateColumns: `64px repeat(${calDayCount}, minmax(0, 1fr))` }}
                className="grid border-b border-white/10 bg-[#2a2a2a]"
              >
                <div />
                {weekDates.map((d) => (
                  <div key={d.iso} className="border-l border-white/10 py-2.5 text-center">
                    <div className="text-[11px] font-semibold text-neutral-400">{d.label}</div>
                    <div className="mt-0.5 text-sm font-extrabold text-white">{d.dayNum}</div>
                  </div>
                ))}
              </div>

              <div
                style={{
                  gridTemplateColumns: `64px repeat(${calDayCount}, minmax(0, 1fr))`,
                  height: `${bodyHeight}px`,
                }}
                className="relative grid"
              >
                <div className="relative select-none">
                  {hourTicks.map((hr, idx) => (
                    <div
                      key={hr}
                      style={{ top: `${idx * ROW_HEIGHT}px` }}
                      className="absolute right-2.5 -translate-y-1/2 text-[10px] font-semibold text-neutral-400"
                    >
                      {fmtHourTick(hr)}
                    </div>
                  ))}
                </div>

                {weekDates.map((d) => {
                  const dayEvs = eventsByDate[d.iso] || [];
                  return (
                    <div key={d.iso} className="relative border-l border-white/10">
                      {Array.from({ length: totalHours }).map((_, hIdx) => (
                        <div
                          key={hIdx}
                          style={{ top: `${hIdx * ROW_HEIGHT}px`, height: `${ROW_HEIGHT}px` }}
                          className="border-b border-white/5"
                        />
                      ))}

                      {dayEvs.length === 0 ? (
                        <div className="absolute inset-x-0 top-10 text-center text-xs italic text-neutral-500">
                          No classes
                        </div>
                      ) : (
                        dayEvs.map((ev, eIdx) => {
                          const startMin = ev.startMin ?? gridStartHour * 60;
                          const endMin = ev.endMin ?? startMin + 60;
                          const topPx = Math.max(2, ((startMin - gridStartHour * 60) / 60) * ROW_HEIGHT + 2);
                          const heightPx = Math.max(36, ((endMin - startMin) / 60) * ROW_HEIGHT - 4);
                          const pal = TT_PALETTE[(ev.colorIndex || 0) % TT_PALETTE.length];
                          const dotColor = STATUS_DOT[ev.status];
                          return (
                            <div
                              key={`${ev.code}-${eIdx}`}
                              title={`${ev.name} (${ev.code}) · ${ev.start} – ${ev.end} · ${ev.status}`}
                              style={{
                                top: `${topPx}px`,
                                height: `${heightPx}px`,
                                backgroundColor: pal.bg,
                                borderColor: pal.border,
                              }}
                              className="absolute inset-x-1.5 overflow-hidden rounded-lg border px-2.5 py-1.5 shadow-sm"
                            >
                              <div className="flex items-start justify-between gap-1.5">
                                <div style={{ color: pal.title }} className="text-xs font-bold leading-snug">
                                  {ev.name}
                                </div>
                                {dotColor ? (
                                  <span style={{ backgroundColor: dotColor }} className="mt-1 h-2 w-2 shrink-0 rounded-full" />
                                ) : null}
                              </div>
                              <div style={{ color: pal.sub }} className="mt-0.5 text-[11px] font-semibold">
                                {ev.code} · {ev.type}
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PyqsCard({
  props,
  onPreview,
  onIndexed,
  onAsk,
}: {
  props: Record<string, any>;
  onPreview: (f: PreviewFile) => void;
  onIndexed?: () => void;
  onAsk?: (prompt: string) => void;
}) {
  const groups: any[] = props.groups || [];
  const totalPapers = props.totalPapers || 0;

  return (
    <div className="my-2 w-full space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#262626] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#E9A23B]/35 bg-[#E9A23B]/15 text-[#E9A23B]">
            <BookOpen className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-bold text-white">DCRUST Previous Year Question Papers</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-neutral-400">
              <span>
                Query: <span className="font-semibold text-[#F6C56B]">{props.query}</span>
              </span>
              {props.pyqDir ? (
                <span className="inline-flex items-center gap-1 truncate">
                  <FolderOpen className="h-3 w-3 shrink-0" />
                  <span className="truncate">{props.pyqDir}</span>
                </span>
              ) : null}
            </div>
          </div>
        </div>
        <span className="rounded-full border border-white/10 bg-[#333333] px-3 py-1 text-xs font-bold text-neutral-200">
          {totalPapers} paper{totalPapers === 1 ? "" : "s"} found
        </span>
      </div>

      {groups.map((grp, idx) => (
        <div key={grp.courseCode || idx} className="overflow-hidden rounded-xl border border-white/10 bg-[#242424]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-[#2b2b2b] px-4 py-2.5">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="rounded-md border border-[#5B8FC7]/40 bg-[#5B8FC7]/15 px-2 py-0.5 font-mono text-xs font-bold text-[#a8c7e8]">
                {grp.courseCode}
              </span>
              <span className="font-bold text-white">{grp.subjectName}</span>
            </div>
            <span className="text-xs font-semibold text-neutral-400">
              {grp.count} paper{grp.count === 1 ? "" : "s"}
            </span>
          </div>

          <div className="divide-y divide-white/10">
            {(grp.papers || []).map((paper: any, pIdx: number) => (
              <div
                key={`${paper.session}-${paper.code}-${pIdx}`}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 transition hover:bg-white/[0.03]"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 shrink-0 text-[#E9A23B]" />
                    <span className="font-semibold text-neutral-100">{paper.session}</span>
                    <span className="font-mono text-xs text-neutral-400">{paper.code}</span>
                  </div>
                  {paper.localRelpath ? (
                    <div className="mt-0.5 truncate pl-6 font-mono text-[11px] text-neutral-400">{paper.localRelpath}</div>
                  ) : null}
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  {paper.downloaded ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
                      <CheckCircle2 className="h-3 w-3" /> Saved ({paper.sizeKb} KB)
                    </span>
                  ) : null}
                  {paper.localUrl ? (
                    <button
                      type="button"
                      onClick={() =>
                        onPreview({
                          name: `${grp.courseCode}_${paper.session}.pdf`,
                          url: paper.localUrl,
                          ext: "pdf",
                        })
                      }
                      className="inline-flex items-center gap-1 rounded-lg border border-[#5B8FC7]/40 bg-[#5B8FC7]/15 px-2.5 py-1 text-xs font-semibold text-[#a8c7e8] hover:bg-[#5B8FC7]/25"
                    >
                      <Eye className="h-3 w-3" /> View PDF
                    </button>
                  ) : null}
                  {paper.localUrl ? (
                    <IndexRagAction
                      localUrl={paper.localUrl}
                      title={`${grp.courseCode} ${grp.subjectName} (${paper.session})`}
                      course={grp.courseCode}
                      initiallyIndexed={Boolean(paper.indexed)}
                      onIndexed={onIndexed}
                      onAsk={onAsk}
                    />
                  ) : null}
                  <a
                    href={paper.remoteUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-[#2e2e2e] px-2.5 py-1 text-xs font-semibold text-neutral-200 hover:bg-[#383838]"
                  >
                    Portal <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function SyllabusCard({
  props,
  onPreview,
  onIndexed,
  onAsk,
}: {
  props: Record<string, any>;
  onPreview: (f: PreviewFile) => void;
  onIndexed?: () => void;
  onAsk?: (prompt: string) => void;
}) {
  const items: any[] = props.items || [];
  const filters = [props.branch, props.degree, props.year].filter(Boolean);

  return (
    <div className="my-2 w-full space-y-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#262626] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#5B8FC7]/35 bg-[#5B8FC7]/15 text-[#7ab0eb]">
            <BookMarked className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-bold text-white">DCRUST University Syllabus &amp; Schemes</div>
            <div className="mt-0.5 text-xs text-neutral-400">
              {filters.length ? `Filters: ${filters.join(" · ")}` : `Query: ${props.query}`}
            </div>
          </div>
        </div>
        <span className="rounded-full border border-white/10 bg-[#333333] px-3 py-1 text-xs font-bold text-neutral-200">
          {items.length} syllabus doc{items.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="divide-y divide-white/10 overflow-hidden rounded-xl border border-white/10 bg-[#242424]">
        {items.map((item, idx) => (
          <div
            key={`${item.remoteUrl}-${idx}`}
            className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition hover:bg-white/[0.03]"
          >
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-start gap-2">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-[#E9A23B]" />
                <div className="font-semibold leading-snug text-neutral-100">{item.title}</div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 pl-6 text-[11px]">
                <span className="rounded-full border border-[#5B8FC7]/35 bg-[#5B8FC7]/15 px-2 py-0.5 font-semibold text-[#a8c7e8]">
                  {item.branch}
                </span>
                <span className="rounded-full border border-[#E9A23B]/35 bg-[#E9A23B]/15 px-2 py-0.5 font-semibold text-[#f6c56b]">
                  {item.year}
                </span>
                {item.degree && item.degree !== "Other" ? (
                  <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-neutral-300">
                    {item.degree}
                  </span>
                ) : null}
                <span className="font-mono text-neutral-400">{item.fileType}</span>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {item.downloaded ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
                  <CheckCircle2 className="h-3 w-3" /> Saved ({item.sizeKb} KB)
                </span>
              ) : null}
              {item.localUrl ? (
                <button
                  type="button"
                  onClick={() =>
                    onPreview({
                      name: `${item.title}.${(item.fileType || "pdf").toLowerCase()}`,
                      url: item.localUrl,
                      ext: (item.fileType || "pdf").toLowerCase(),
                    })
                  }
                  className="inline-flex items-center gap-1 rounded-lg border border-[#5B8FC7]/40 bg-[#5B8FC7]/15 px-2.5 py-1 text-xs font-semibold text-[#a8c7e8] hover:bg-[#5B8FC7]/25"
                >
                  <Eye className="h-3 w-3" /> {item.fileType === "PDF" ? "View PDF" : `Open ${item.fileType}`}
                </button>
              ) : null}
              {item.localUrl ? (
                <IndexRagAction
                  localUrl={item.localUrl}
                  title={item.title}
                  course={item.branch}
                  initiallyIndexed={Boolean(item.indexed)}
                  onIndexed={onIndexed}
                  onAsk={onAsk}
                />
              ) : null}
              <a
                href={item.remoteUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-[#2e2e2e] px-2.5 py-1 text-xs font-semibold text-neutral-200 hover:bg-[#383838]"
              >
                Portal <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DcrustElementRenderer({
  element,
  onPreviewFile,
  onVaultChanged,
  onAskPrompt,
}: {
  element: UiElementPayload;
  onPreviewFile: (file: PreviewFile) => void;
  onVaultChanged?: () => void;
  onAskPrompt?: (prompt: string) => void;
}) {
  if (element.name === "DcrustAttendance") {
    return <AttendanceCard props={element.props} onPreview={onPreviewFile} />;
  }
  if (element.name === "DcrustTimetable") {
    return <TimetableCard props={element.props} />;
  }
  if (element.name === "DcrustPyqs") {
    return (
      <PyqsCard
        props={element.props}
        onPreview={onPreviewFile}
        onIndexed={onVaultChanged}
        onAsk={onAskPrompt}
      />
    );
  }
  if (element.name === "DcrustSyllabus") {
    return (
      <SyllabusCard
        props={element.props}
        onPreview={onPreviewFile}
        onIndexed={onVaultChanged}
        onAsk={onAskPrompt}
      />
    );
  }
  return null;
}
