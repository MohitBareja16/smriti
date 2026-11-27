import { BookMarked, CheckCircle2, ExternalLink, FileText, FolderOpen } from "lucide-react";

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
  branchBadge: {
    backgroundColor: "rgba(14, 165, 233, 0.16)",
    borderColor: "rgba(14, 165, 233, 0.35)",
    color: "#7dd3fc",
  },
  yearBadge: {
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

export default function DcrustSyllabus() {
  const items = props.items || [];
  const filters = [props.branch, props.degree, props.year].filter(Boolean);

  return (
    <div className="w-full space-y-3 my-2 text-sm text-foreground">
      {/* Header Card */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-card/60 px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <div
            style={STYLES.iconBox}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border"
          >
            <BookMarked className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-extrabold tracking-tight text-foreground">
              DCRUST University Syllabus &amp; Schemes
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
              {filters.length ? (
                <span>
                  Filters: <span style={{ color: "#818cf8" }} className="font-semibold">{filters.join(" · ")}</span>
                </span>
              ) : (
                <span>
                  Query: <span style={{ color: "#818cf8" }} className="font-semibold">{props.query}</span>
                </span>
              )}
              {props.syllabusDir ? (
                <span className="inline-flex items-center gap-1 truncate text-muted-foreground">
                  <FolderOpen className="h-3 w-3 shrink-0" />
                  <span className="truncate">{props.syllabusDir}</span>
                </span>
              ) : null}
            </div>
          </div>
        </div>
        <div
          style={STYLES.countPill}
          className="shrink-0 rounded-full border px-3 py-1 text-xs font-bold"
        >
          {items.length} syllabus doc{items.length === 1 ? "" : "s"}
        </div>
      </div>

      {/* Syllabus List Card */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-card/50 shadow-sm divide-y divide-white/10">
        {items.map((item, idx) => (
          <div
            key={`${item.remoteUrl}-${idx}`}
            className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition hover:bg-white/[0.03]"
          >
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-start gap-2">
                <FileText style={{ color: "#818cf8" }} className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="font-semibold leading-snug text-foreground">{item.title}</div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 pl-6 text-[11px]">
                <span style={STYLES.branchBadge} className="rounded-full border px-2 py-0.5 font-semibold">
                  {item.branch}
                </span>
                <span style={STYLES.yearBadge} className="rounded-full border px-2 py-0.5 font-semibold">
                  {item.year}
                </span>
                {item.degree && item.degree !== "Other" ? (
                  <span style={STYLES.mutedBadge} className="rounded-full border px-2 py-0.5 font-medium">
                    {item.degree}
                  </span>
                ) : null}
                {item.scheme ? (
                  <span style={STYLES.mutedBadge} className="rounded-full border px-2 py-0.5 font-medium">
                    {item.scheme}
                  </span>
                ) : null}
                <span className="font-mono text-muted-foreground">{item.fileType}</span>
              </div>
              {item.localRelpath ? (
                <div className="truncate pl-6 font-mono text-[11px] text-muted-foreground">
                  {item.localRelpath}
                </div>
              ) : null}
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {item.downloaded ? (
                <span
                  style={STYLES.savedBadge}
                  className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                >
                  <CheckCircle2 className="h-3 w-3" /> Saved ({item.sizeKb} KB)
                </span>
              ) : (
                <span
                  style={STYLES.mutedBadge}
                  className="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
                >
                  {item.status === "portal_only" ? "Drive / Portal" : "Portal link"}
                </span>
              )}
              <a
                href={item.remoteUrl}
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
  );
}
