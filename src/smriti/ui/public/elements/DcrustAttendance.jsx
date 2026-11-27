import { useState } from "react";
import { ChevronDown, ChevronUp, FileText, GraduationCap } from "lucide-react";

const LEVEL_COLORS = {
  success: { dot: "#30D158", text: "#4ade80", bar: "#22c55e" },
  warning: { dot: "#FFD60A", text: "#facc15", bar: "#eab308" },
  danger: { dot: "#FF453A", text: "#f87171", bar: "#ef4444" },
};

export default function DcrustAttendance() {
  const [openIdx, setOpenIdx] = useState(null);
  const subjects = props.subjects || [];

  return (
    <div className="w-full space-y-3 my-2 text-sm">
      {/* Header matching a10dance.com */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-card/60 px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
            <GraduationCap className="h-5 w-5" />
          </div>
          <div>
            <div className="text-base font-extrabold tracking-tight">{props.semesterLabel}</div>
            <div className="text-xs text-muted-foreground">
              Roll No: <span className="font-semibold text-foreground">{props.rollNumber}</span> · {props.fetchedAt}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-extrabold text-emerald-400">{props.overallPercentage}</div>
          <div className="text-xs text-muted-foreground">
            {props.totalAttended} / {props.totalClasses} classes
          </div>
        </div>
      </div>

      {/* Subject Cards */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-card/50 shadow-sm divide-y divide-white/10">
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
                      className="h-2 w-2 rounded-full shrink-0"
                    />
                    <span className="font-mono text-[11px] tracking-wide text-muted-foreground">
                      {subj.sectionCode || subj.courseCode}
                    </span>
                  </div>
                  <div className="text-sm font-bold leading-snug">{subj.displayName}</div>
                  <div style={{ color: col.text }} className="text-xs font-semibold pt-0.5">
                    {subj.prediction}
                  </div>
                  <div className="text-xs text-muted-foreground space-y-0.5 pt-1">
                    <div>
                      Today&apos;s Schedule: <span className="font-semibold text-foreground">{subj.todaySchedule}</span>
                    </div>
                    {subj.lastMarked ? (
                      <div>
                        Last attendance marked on: <span className="font-semibold text-foreground">{subj.lastMarked}</span>
                      </div>
                    ) : null}
                  </div>
                </div>

                <div className="flex flex-col items-end shrink-0">
                  <div style={{ color: col.text }} className="text-xl font-extrabold">
                    {subj.percentageStr}
                  </div>
                  <div className="text-xs font-semibold text-muted-foreground">
                    {subj.attended} / {subj.total}
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground flex items-center gap-1">
                    {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    <span>Logs</span>
                  </div>
                </div>
              </div>

              {/* Progress bar */}
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                <div style={{ width: `${pctWidth}%`, backgroundColor: col.bar }} className="h-full rounded-full" />
              </div>

              {/* Local / Portal PYQ Links */}
              {subj.pyqLinks && subj.pyqLinks.length > 0 ? (
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="flex items-center gap-1 text-indigo-400 font-semibold">
                    <FileText className="h-3 w-3" /> PYQs:
                  </span>
                  {subj.pyqLinks.map((lnk, k) => (
                    <span
                      key={k}
                      className="rounded border border-white/15 bg-white/5 px-2 py-0.5 text-muted-foreground"
                    >
                      {lnk.label}
                    </span>
                  ))}
                </div>
              ) : null}

              {/* Expandable Lecture History */}
              {isOpen ? (
                <div className="mt-3 max-h-60 overflow-y-auto rounded-lg border border-white/10 bg-black/20 divide-y divide-white/5 text-xs">
                  {(subj.entries || []).length === 0 ? (
                    <div className="p-3 text-muted-foreground">No individual lecture logs available.</div>
                  ) : (
                    subj.entries.map((row, rIdx) => (
                      <div key={rIdx} className="grid grid-cols-3 px-3 py-1.5">
                        <span>{row.date}</span>
                        <span className="text-muted-foreground">{row.timeSlot || "—"}</span>
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
