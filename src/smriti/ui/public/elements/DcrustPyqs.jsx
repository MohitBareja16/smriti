import { BookOpen, CheckCircle2, ExternalLink, FileText, FolderOpen } from "lucide-react";

const STYLES = {
  iconBox: {
    backgroundColor: "rgba(99, 102, 241, 0.16)",
    borderColor: "rgba(99, 102, 241, 0.35)",
    color: "#818cf8",
  },
  countPill: {
    backgroundColor: "rgba(99, 102, 241, 0.2)",
    borderColor: "rgba(99, 102, 241, 0.4)",
    color: "#c7d2fe",
  },
  codeBadge: {
    backgroundColor: "rgba(99, 102, 241, 0.18)",
    borderColor: "rgba(99, 102, 241, 0.35)",
    color: "#a5b4fc",
  },
  savedBadge: {
    backgroundColor: "rgba(16, 185, 129, 0.14)",
    borderColor: "rgba(16, 185, 129, 0.35)",
    color: "#34d399",
  },
  mutedBadge: {
    backgroundColor: "rgba(148, 163, 184, 0.12)",
    borderColor: "rgba(148, 163, 184, 0.28)",
    color: "#94a3b8",
  },
  openBtn: {
    backgroundColor: "rgba(99, 102, 241, 0.16)",
    borderColor: "rgba(99, 102, 241, 0.35)",
    color: "#a5b4fc",
  },
};

export default function DcrustPyqs() {
  const groups = props.groups || [];
  const totalPapers = props.totalPapers || 0;

  return (
    <div className="w-full space-y-3 my-2 text-sm text-foreground">
      {/* Header Card */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-card/60 px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <div
            style={STYLES.iconBox}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border"
          >
            <BookOpen className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-extrabold tracking-tight text-foreground">
              DCRUST Previous Year Question Papers
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
              <span>
                Query: <span style={{ color: "#818cf8" }} className="font-semibold">{props.query}</span>
              </span>
              {props.pyqDir ? (
                <span className="inline-flex items-center gap-1 truncate text-muted-foreground">
                  <FolderOpen className="h-3 w-3 shrink-0" />
                  <span className="truncate">{props.pyqDir}</span>
                </span>
              ) : null}
            </div>
          </div>
        </div>
        <div
          style={STYLES.countPill}
          className="shrink-0 rounded-full border px-3 py-1 text-xs font-bold"
        >
          {totalPapers} paper{totalPapers === 1 ? "" : "s"} found
        </div>
      </div>

      {/* Matched Subjects */}
      {groups.map((grp, idx) => (
        <div
          key={grp.courseCode || idx}
          className="overflow-hidden rounded-xl border border-white/10 bg-card/50 shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-muted/30 px-4 py-2.5">
            <div className="flex flex-wrap items-center gap-2.5">
              <span
                style={STYLES.codeBadge}
                className="rounded-md border px-2 py-0.5 font-mono text-xs font-bold"
              >
                {grp.courseCode}
              </span>
              <span className="font-bold text-foreground">{grp.subjectName}</span>
            </div>
            <span className="text-xs font-semibold text-muted-foreground">
              {grp.count} paper{grp.count === 1 ? "" : "s"}
            </span>
          </div>

          <div className="divide-y divide-white/10">
            {(grp.papers || []).map((paper, pIdx) => (
              <div
                key={`${paper.session}-${paper.code}-${pIdx}`}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 transition hover:bg-white/[0.03]"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <FileText style={{ color: "#818cf8" }} className="h-4 w-4 shrink-0" />
                    <span className="font-semibold text-foreground">{paper.session}</span>
                    <span className="font-mono text-xs text-muted-foreground">{paper.code}</span>
                  </div>
                  {paper.localRelpath ? (
                    <div className="mt-0.5 truncate pl-6 font-mono text-[11px] text-muted-foreground">
                      {paper.localRelpath}
                    </div>
                  ) : null}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {paper.downloaded ? (
                    <span
                      style={STYLES.savedBadge}
                      className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                    >
                      <CheckCircle2 className="h-3 w-3" /> Saved ({paper.sizeKb} KB)
                    </span>
                  ) : (
                    <span
                      style={STYLES.mutedBadge}
                      className="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
                    >
                      {paper.status === "missing_remote" ? "Unavailable" : "Portal only"}
                    </span>
                  )}
                  <a
                    href={paper.remoteUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={STYLES.openBtn}
                    className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-semibold transition hover:opacity-85"
                  >
                    Open <ExternalLink className="h-3 w-3" />
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
