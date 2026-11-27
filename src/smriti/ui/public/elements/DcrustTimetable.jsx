import { useState, useMemo } from "react";
import { Calendar, Table2, ChevronLeft, ChevronRight, Info } from "lucide-react";

const PALETTE = [
  { bg: "rgba(99, 102, 241, 0.14)", border: "rgba(99, 102, 241, 0.35)", title: "#a5b4fc", sub: "#818cf8", dot: "#6366f1" },
  { bg: "rgba(245, 158, 11, 0.14)", border: "rgba(245, 158, 11, 0.35)", title: "#fcd34d", sub: "#fbbf24", dot: "#f59e0b" },
  { bg: "rgba(14, 165, 233, 0.14)", border: "rgba(14, 165, 233, 0.35)", title: "#7dd3fc", sub: "#38bdf8", dot: "#0ea5e9" },
  { bg: "rgba(16, 185, 129, 0.14)", border: "rgba(16, 185, 129, 0.35)", title: "#6ee7b7", sub: "#34d399", dot: "#10b981" },
  { bg: "rgba(244, 63, 94, 0.14)", border: "rgba(244, 63, 94, 0.35)", title: "#fda4af", sub: "#fb7185", dot: "#f43f5e" },
  { bg: "rgba(168, 85, 247, 0.14)", border: "rgba(168, 85, 247, 0.35)", title: "#d8b4fe", sub: "#c084fc", dot: "#a855f7" },
];

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY_SHORT = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
const ROW_HEIGHT = 68;

const STATUS_DOT = {
  PRESENT: "#10b981",
  ABSENT: "#ef4444",
  LEAVE: "#f59e0b",
};

function mondayOf(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const dow = (dt.getUTCDay() + 6) % 7;
  dt.setUTCDate(dt.getUTCDate() - dow);
  return dt.toISOString().slice(0, 10);
}

function addDays(iso, delta) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + delta));
  return dt.toISOString().slice(0, 10);
}

function formatWeekRange(monIso, dayCount) {
  const endIso = addDays(monIso, dayCount - 1);
  const [y1, m1, d1] = monIso.split("-").map(Number);
  const [y2, m2, d2] = endIso.split("-").map(Number);
  if (m1 === m2 && y1 === y2) {
    return `${d1} – ${d2} ${MONTHS_SHORT[m2 - 1]} ${y2}`;
  }
  return `${d1} ${MONTHS_SHORT[m1 - 1]} – ${d2} ${MONTHS_SHORT[m2 - 1]} ${y2}`;
}

function fmtHourTick(h) {
  const h12 = h % 12 || 12;
  return `${h12} ${h < 12 ? "AM" : "PM"}`;
}

export default function DcrustTimetable() {
  const [tab, setTab] = useState("table");
  const hours = props.hours || [];
  const days = props.days || [];
  const subjects = props.subjects || [];
  const events = props.events || [];
  const gridStartHour = props.gridStartHour ?? (hours.length ? hours[0].hour : 9);
  const gridEndHour = props.gridEndHour ?? (hours.length ? hours[hours.length - 1].hour + 1 : 17);
  const calDayCount = props.calDayCount || 5;

  const { weeks, defaultWeekIdx } = useMemo(() => {
    const uniq = Array.from(new Set(events.map((e) => mondayOf(e.date)))).sort();
    if (!uniq.length) {
      return { weeks: [mondayOf(new Date().toISOString().slice(0, 10))], defaultWeekIdx: 0 };
    }
    const todayMon = mondayOf(new Date().toISOString().slice(0, 10));
    let idx = uniq.indexOf(todayMon);
    if (idx === -1) {
      // Pick the latest full week with marked attendance if the very last week is partial (e.g., 1 day)
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
    () => Array.from({ length: calDayCount }, (_, i) => {
      const iso = addDays(activeMonday, i);
      return { iso, label: DAY_SHORT[i], dayNum: Number(iso.split("-")[2]) };
    }),
    [activeMonday, calDayCount]
  );

  const eventsByDate = useMemo(() => {
    const map = {};
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
    <div className="w-full space-y-4 my-2 text-sm">
      {/* Header matching cse.dcrust.online/timetable */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-card/60 p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-400 border border-indigo-500/25">
            <Calendar className="h-5 w-5" />
          </div>
          <div>
            <div className="text-lg font-bold tracking-tight">Timetable</div>
            <div className="text-xs text-muted-foreground">
              Roll No. <span className="font-semibold text-foreground">{props.rollNumber}</span>
            </div>
            <div className="text-xs font-semibold text-indigo-400">
              {props.semesterLabel}
              {props.sectionLabel ? ` · ${props.sectionLabel}` : ""}
            </div>
          </div>
        </div>
        <div className="text-xs text-muted-foreground">{events.length} sessions indexed</div>
      </div>

      {/* Semester ended banner */}
      {props.notice ? (
        <div className="flex items-center gap-2.5 rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2.5 text-xs font-medium text-indigo-300">
          <Info className="h-4 w-4 shrink-0" />
          <span>{props.notice}</span>
        </div>
      ) : null}

      {/* Segmented Pill Toggle */}
      <div className="grid grid-cols-2 gap-1 rounded-xl border border-white/10 bg-muted/40 p-1">
        <button
          type="button"
          onClick={() => setTab("table")}
          className={`flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold tracking-wide transition ${
            tab === "table"
              ? "bg-background text-indigo-400 shadow-sm border border-white/10"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Table2 className="h-4 w-4" />
          TABLE
        </button>
        <button
          type="button"
          onClick={() => setTab("calendar")}
          className={`flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold tracking-wide transition ${
            tab === "calendar"
              ? "bg-background text-indigo-400 shadow-sm border border-white/10"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Calendar className="h-4 w-4" />
          CALENDAR
        </button>
      </div>

      {tab === "table" ? (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-xl border border-white/10 bg-card/50 shadow-sm">
            <table className="w-full border-collapse min-w-[820px]">
              <thead>
                <tr className="border-b border-white/10 bg-muted/30">
                  <th className="w-20 px-3 py-3 text-center text-xs font-bold text-muted-foreground">DAY</th>
                  {hours.map((h) => (
                    <th key={h.hour} className="border-l border-white/10 px-2 py-2.5 text-center">
                      <div className="text-xs font-bold text-foreground">{h.start}</div>
                      <div className="text-[11px] font-normal text-muted-foreground">to {h.end}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {days.map((day) => {
                  const byStart = {};
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
                            const pal = PALETTE[(s.colorIndex || 0) % PALETTE.length];
                            return (
                              <div
                                key={`${s.code}-${k}`}
                                style={{ backgroundColor: pal.bg, borderColor: pal.border }}
                                className="flex min-h-[66px] flex-col items-center justify-center rounded-lg border px-2 py-2 text-center"
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
                      className={`border-b border-white/10 last:border-b-0 ${day.isToday ? "bg-indigo-500/10" : ""}`}
                    >
                      <td className="px-3 py-3 text-center">
                        <div className="text-xs font-extrabold tracking-wide">{day.label}</div>
                        {day.isToday ? (
                          <span className="mt-1 inline-block rounded-full bg-indigo-500 px-2 py-0.5 text-[10px] font-bold text-white">
                            TODAY
                          </span>
                        ) : null}
                      </td>
                      {day.slots && day.slots.length > 0 ? (
                        cells
                      ) : (
                        <td
                          colSpan={Math.max(1, hours.length)}
                          className="border-l border-white/5 py-5 text-center text-xs italic text-muted-foreground"
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

          <div className="rounded-xl border border-white/10 bg-card/50 p-4 shadow-sm">
            <div className="mb-3 text-[11px] font-extrabold tracking-widest text-muted-foreground">SUBJECTS</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {subjects.map((subj) => {
                const pal = PALETTE[(subj.colorIndex || 0) % PALETTE.length];
                return (
                  <div key={subj.code} className="flex items-start gap-2.5">
                    <span style={{ backgroundColor: pal.dot }} className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" />
                    <div>
                      <div className="text-xs font-bold text-foreground">{subj.name}</div>
                      <div className="text-[11px] text-muted-foreground">
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
        <div className="overflow-hidden rounded-xl border border-white/10 bg-card/50 shadow-sm">
          {/* Weekly Calendar Navigation Header */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  disabled={weekIdx <= 0}
                  onClick={() => setWeekIdx((w) => Math.max(0, w - 1))}
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-muted/30 hover:bg-muted disabled:opacity-35"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  disabled={weekIdx >= weeks.length - 1}
                  onClick={() => setWeekIdx((w) => Math.min(weeks.length - 1, w + 1))}
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-muted/30 hover:bg-muted disabled:opacity-35"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <div>
                <div className="text-sm font-bold text-foreground">
                  {formatWeekRange(activeMonday, calDayCount)}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Week {weekIdx + 1} of {weeks.length}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setWeekIdx(defaultWeekIdx)}
              className="rounded-full border border-indigo-500/35 bg-indigo-500/10 px-4 py-1 text-[11px] font-bold tracking-wide text-indigo-400 hover:bg-indigo-500/20"
            >
              TODAY
            </button>
          </div>

          {/* Weekly Time-Grid */}
          <div className="overflow-x-auto">
            <div className="min-w-[820px]">
              {/* Day Columns Header */}
              <div
                style={{ gridTemplateColumns: `64px repeat(${calDayCount}, minmax(0, 1fr))` }}
                className="grid border-b border-white/10 bg-muted/20"
              >
                <div />
                {weekDates.map((d) => (
                  <div key={d.iso} className="border-l border-white/10 py-2.5 text-center">
                    <div className="text-[11px] font-semibold text-muted-foreground">{d.label}</div>
                    <div className="mt-0.5 text-sm font-extrabold text-foreground">{d.dayNum}</div>
                  </div>
                ))}
              </div>

              {/* Timeline Body */}
              <div
                style={{ gridTemplateColumns: `64px repeat(${calDayCount}, minmax(0, 1fr))`, height: `${bodyHeight}px` }}
                className="relative grid"
              >
                {/* Left Hour Labels */}
                <div className="relative select-none">
                  {hourTicks.map((hr, idx) => (
                    <div
                      key={hr}
                      style={{ top: `${idx * ROW_HEIGHT}px` }}
                      className="absolute right-2.5 -translate-y-1/2 text-[10px] font-semibold text-muted-foreground"
                    >
                      {fmtHourTick(hr)}
                    </div>
                  ))}
                </div>

                {/* Day Columns */}
                {weekDates.map((d) => {
                  const dayEvs = eventsByDate[d.iso] || [];
                  return (
                    <div key={d.iso} className="relative border-l border-white/10">
                      {/* Horizontal Hour Lines */}
                      {Array.from({ length: totalHours }).map((_, hIdx) => (
                        <div
                          key={hIdx}
                          style={{ top: `${hIdx * ROW_HEIGHT}px`, height: `${ROW_HEIGHT}px` }}
                          className="border-b border-white/5"
                        />
                      ))}

                      {dayEvs.length === 0 ? (
                        <div className="absolute inset-x-0 top-10 text-center text-xs italic text-muted-foreground">
                          No classes
                        </div>
                      ) : (
                        dayEvs.map((ev, eIdx) => {
                          const startMin = ev.startMin ?? gridStartHour * 60;
                          const endMin = ev.endMin ?? startMin + 60;
                          const topPx = Math.max(2, ((startMin - gridStartHour * 60) / 60) * ROW_HEIGHT + 2);
                          const heightPx = Math.max(36, ((endMin - startMin) / 60) * ROW_HEIGHT - 4);
                          const pal = PALETTE[(ev.colorIndex || 0) % PALETTE.length];
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
                              className="absolute inset-x-1.5 overflow-hidden rounded-lg border px-2.5 py-2 shadow-sm"
                            >
                              <div className="flex items-start justify-between gap-1.5">
                                <div style={{ color: pal.title }} className="text-xs font-bold leading-snug">
                                  {ev.name}
                                </div>
                                {dotColor ? (
                                  <span
                                    style={{ backgroundColor: dotColor }}
                                    className="mt-1 h-2 w-2 shrink-0 rounded-full"
                                  />
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
