import { useEffect, useState } from "react";
import {
  ArrowLeft,
  BookMarked,
  BookOpen,
  CheckCircle2,
  ExternalLink,
  Eye,
  FileText,
  Loader2,
  Search,
  Sparkles,
} from "lucide-react";
import { indexLibraryFile, searchPyqCatalog, searchSyllabusCatalog } from "../api";
import type { HealthStatus, PreviewFile } from "../types";

interface LibraryExplorerPageProps {
  tab: "pyqs" | "syllabus";
  health: HealthStatus | null;
  onTabChange: (tab: "pyqs" | "syllabus") => void;
  onBackToChat: () => void;
  onPreviewFile: (file: PreviewFile) => void;
  onAskInChat: (prompt: string) => void;
  onVaultChanged: () => void;
}

const SYLLABUS_BRANCHES = [
  { id: "", label: "All Branches" },
  { id: "cse_it", label: "CSE / IT" },
  { id: "ece", label: "ECE" },
  { id: "ee", label: "EE" },
  { id: "mech_aero", label: "ME / Aero" },
  { id: "civil", label: "Civil" },
  { id: "biotech", label: "Biotech" },
  { id: "chemical", label: "Chemical" },
  { id: "common_1st", label: "1st Year Common" },
];

const SYLLABUS_YEARS = [
  { id: "", label: "All Years" },
  { id: "1st", label: "1st Year" },
  { id: "2nd", label: "2nd Year" },
  { id: "3rd", label: "3rd Year" },
  { id: "4th", label: "4th Year" },
];

function rawPathFromUrl(localUrl?: string): string | null {
  if (!localUrl) return null;
  const idx = localUrl.indexOf("?");
  if (idx === -1) return null;
  return new URLSearchParams(localUrl.slice(idx + 1)).get("path");
}

export function LibraryExplorerPage({
  tab,
  health,
  onTabChange,
  onBackToChat,
  onPreviewFile,
  onAskInChat,
  onVaultChanged,
}: LibraryExplorerPageProps) {
  const [pyqQuery, setPyqQuery] = useState("");
  const [pyqGroups, setPyqGroups] = useState<any[]>([]);
  const [pyqTotal, setPyqTotal] = useState(0);
  const [pyqReady, setPyqReady] = useState(true);
  const [pyqLoading, setPyqLoading] = useState(false);

  const [sylQuery, setSylQuery] = useState("");
  const [sylBranch, setSylBranch] = useState("");
  const [sylYear, setSylYear] = useState("");
  const [sylItems, setSylItems] = useState<any[]>([]);
  const [sylReady, setSylReady] = useState(true);
  const [sylLoading, setSylLoading] = useState(false);

  const [indexingMap, setIndexingMap] = useState<Record<string, "busy" | "done" | "err">>({});
  const [indexErr, setIndexErr] = useState<string | null>(null);
  const [batchStatus, setBatchStatus] = useState<Record<string, string>>({});
  const [unitBySubject, setUnitBySubject] = useState<Record<string, string>>({});

  useEffect(() => {
    if (tab !== "pyqs") return;
    let cancelled = false;
    setPyqLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await searchPyqCatalog(pyqQuery, 24);
        if (cancelled) return;
        setPyqReady(res.catalog_ready);
        setPyqGroups(res.ui_element?.props?.groups || []);
        setPyqTotal(res.total_papers || 0);
      } catch {
        if (!cancelled) setPyqGroups([]);
      } finally {
        if (!cancelled) setPyqLoading(false);
      }
    }, pyqQuery ? 220 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tab, pyqQuery]);

  useEffect(() => {
    if (tab !== "syllabus") return;
    let cancelled = false;
    setSylLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await searchSyllabusCatalog(sylQuery, sylBranch, sylYear, 120);
        if (cancelled) return;
        setSylReady(res.catalog_ready);
        setSylItems(res.ui_element?.props?.items || []);
      } catch {
        if (!cancelled) setSylItems([]);
      } finally {
        if (!cancelled) setSylLoading(false);
      }
    }, sylQuery ? 220 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [tab, sylQuery, sylBranch, sylYear]);

  const indexSingleFile = async (localUrl: string, course?: string) => {
    const raw = rawPathFromUrl(localUrl);
    if (!raw) return;
    setIndexErr(null);
    setIndexingMap((prev) => ({ ...prev, [raw]: "busy" }));
    try {
      await indexLibraryFile(raw, course, "library");
      setIndexingMap((prev) => ({ ...prev, [raw]: "done" }));
      onVaultChanged();
    } catch (err) {
      setIndexingMap((prev) => ({ ...prev, [raw]: "err" }));
      setIndexErr(err instanceof Error ? err.message : "Failed to index PDF");
    }
  };

  const indexWholeSubject = async (grp: any) => {
    const papers = (grp.papers || []).filter((p: any) => p.localUrl);
    if (!papers.length) return;
    setIndexErr(null);
    let doneCount = 0;
    for (const p of papers) {
      const raw = rawPathFromUrl(p.localUrl);
      if (!raw) continue;
      if (p.indexed || indexingMap[raw] === "done") {
        doneCount += 1;
        continue;
      }
      doneCount += 1;
      setBatchStatus((prev) => ({ ...prev, [grp.courseCode]: `Indexing ${doneCount}/${papers.length}...` }));
      await indexSingleFile(p.localUrl, grp.courseCode);
    }
    setBatchStatus((prev) => ({ ...prev, [grp.courseCode]: `All ${papers.length} indexed` }));
    onVaultChanged();
  };

  const isIndexed = (itemOrPaper: any) => {
    const raw = rawPathFromUrl(itemOrPaper.localUrl);
    if (raw && indexingMap[raw] === "done") return true;
    return Boolean(itemOrPaper.indexed);
  };

  const getIndexState = (itemOrPaper: any) => {
    const raw = rawPathFromUrl(itemOrPaper.localUrl);
    if (raw && indexingMap[raw]) return indexingMap[raw];
    return itemOrPaper.indexed ? "done" : "idle";
  };

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 px-4 py-6">
      {/* Top Explorer Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBackToChat}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-[#2a2a2a] px-3 py-1.5 text-xs font-medium text-neutral-200 transition hover:bg-[#343434] hover:text-white"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Chat
        </button>

        <div className="inline-flex rounded-xl border border-white/10 bg-[#1a1a1a] p-1 text-xs">
          <button
            type="button"
            onClick={() => onTabChange("pyqs")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${
              tab === "pyqs" ? "bg-[#2f2f2f] text-[#f6c56b]" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <BookOpen className="h-3.5 w-3.5 text-[#E9A23B]" />
            PYQs ({health?.pyq_count?.toLocaleString() || "0"})
          </button>
          <button
            type="button"
            onClick={() => onTabChange("syllabus")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition ${
              tab === "syllabus" ? "bg-[#2f2f2f] text-[#a8c7e8]" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <BookMarked className="h-3.5 w-3.5 text-[#5B8FC7]" />
            Syllabus ({health?.syllabus_count || "0"})
          </button>
        </div>
      </div>

      {indexErr ? (
        <div className="rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-2.5 text-xs text-rose-300">
          {indexErr}
        </div>
      ) : null}

      {tab === "pyqs" ? (
        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-[#262626] p-4">
            <h1 className="text-base font-bold text-white">DCRUST Previous Year Question Papers Explorer</h1>
            <p className="mt-0.5 text-xs text-neutral-400">
              Search any subject code or name, index papers directly into your local AI memory, or analyze Unit-wise PYQ trends.
            </p>
            <div className="relative mt-3">
              <Search className="pointer-events-none absolute top-3 left-3.5 h-4 w-4 text-neutral-400" />
              <input
                type="search"
                autoFocus
                value={pyqQuery}
                onChange={(e) => setPyqQuery(e.target.value)}
                placeholder="Search PYQs by subject code or name (e.g. CSE423C, CSE302C, Green Computing, Compiler Design)..."
                aria-label="Search PYQs"
                className="w-full rounded-xl border border-white/10 bg-[#1a1a1a] py-2.5 pr-4 pl-10 text-sm text-white placeholder-neutral-500 focus:border-[#E9A23B] focus:outline-none"
              />
            </div>
            <div className="mt-2 flex items-center justify-between text-[11px] text-neutral-400">
              <span>
                {pyqLoading
                  ? "Searching PYQ catalog..."
                  : pyqQuery
                    ? `Showing ${pyqGroups.length} subject(s) · ${pyqTotal} paper(s)`
                    : `Showing top ${pyqGroups.length} downloaded subjects · search to filter all ${(health?.pyq_count || 0).toLocaleString()} papers`}
              </span>
            </div>
          </div>

          {!pyqReady ? (
            <div className="rounded-xl border border-white/10 bg-[#242424] p-6 text-center text-xs text-neutral-400">
              No local DCRUST PYQ catalog found. Run <code className="text-neutral-200">smriti pyq sync</code> to download papers.
            </div>
          ) : pyqGroups.length === 0 && !pyqLoading ? (
            <div className="rounded-xl border border-white/10 bg-[#242424] p-6 text-center text-xs text-neutral-400">
              No subjects matched <span className="font-semibold text-neutral-200">{pyqQuery}</span>. Try another subject code or keyword.
            </div>
          ) : (
            <div className="space-y-3">
              {pyqGroups.map((grp, idx) => (
                <div key={`${grp.courseCode}-${idx}`} className="overflow-hidden rounded-xl border border-white/10 bg-[#242424]">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-[#2b2b2b] px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="rounded-md border border-[#5B8FC7]/40 bg-[#5B8FC7]/15 px-2 py-0.5 font-mono text-xs font-bold text-[#a8c7e8]">
                        {grp.courseCode}
                      </span>
                      <span className="text-sm font-bold text-white">{grp.subjectName}</span>
                      <span className="text-xs text-neutral-400">
                        · {grp.count} paper{grp.count === 1 ? "" : "s"}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {batchStatus[grp.courseCode] ? (
                        <span className="text-[11px] text-emerald-300">{batchStatus[grp.courseCode]}</span>
                      ) : null}
                      {(grp.papers || []).some((p: any) => p.localUrl && !isIndexed(p)) ? (
                        <button
                          type="button"
                          onClick={() => void indexWholeSubject(grp)}
                          className="inline-flex items-center gap-1 rounded-lg border border-[#E9A23B]/40 bg-[#E9A23B]/15 px-2.5 py-1 text-xs font-semibold text-[#f6c56b] hover:bg-[#E9A23B]/25"
                        >
                          <Sparkles className="h-3 w-3" /> Index All
                        </button>
                      ) : null}
                      {(() => {
                        const selectedUnit = unitBySubject[grp.courseCode] || "1";
                        const unitLabel = selectedUnit === "all" ? "All Units" : `Unit ${selectedUnit}`;
                        const prompt =
                          selectedUnit === "all"
                            ? `Analyze the PYQ of ${grp.courseCode} and give me all the PYQs in order of most frequently asked`
                            : `Analyze the PYQ of ${grp.courseCode} and give me all the PYQs asked from unit ${selectedUnit} in order of most frequently asked`;
                        return (
                          <div className="inline-flex items-center overflow-hidden rounded-lg border border-[#5B8FC7]/40 bg-[#5B8FC7]/15">
                            <select
                              aria-label={`Select unit for ${grp.courseCode}`}
                              value={selectedUnit}
                              onChange={(e) =>
                                setUnitBySubject((prev) => ({ ...prev, [grp.courseCode]: e.target.value }))
                              }
                              className="bg-transparent px-2 py-1 text-xs font-semibold text-[#a8c7e8] outline-none hover:bg-[#5B8FC7]/20"
                            >
                              <option value="1" className="bg-[#242424] text-neutral-100">Unit 1</option>
                              <option value="2" className="bg-[#242424] text-neutral-100">Unit 2</option>
                              <option value="3" className="bg-[#242424] text-neutral-100">Unit 3</option>
                              <option value="4" className="bg-[#242424] text-neutral-100">Unit 4</option>
                              <option value="all" className="bg-[#242424] text-neutral-100">All Units</option>
                            </select>
                            <button
                              type="button"
                              onClick={() => onAskInChat(prompt)}
                              className="inline-flex items-center gap-1 border-l border-[#5B8FC7]/35 px-2.5 py-1 text-xs font-semibold text-[#a8c7e8] hover:bg-[#5B8FC7]/25"
                            >
                              <Sparkles className="h-3 w-3" /> Analyze {unitLabel}
                            </button>
                          </div>
                        );
                      })()}
                    </div>
                  </div>

                  <div className="divide-y divide-white/10">
                    {(grp.papers || []).map((paper: any, pIdx: number) => {
                      const st = getIndexState(paper);
                      return (
                        <div
                          key={`${paper.session}-${paper.code}-${pIdx}`}
                          className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 transition hover:bg-white/[0.03]"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <FileText className="h-4 w-4 shrink-0 text-[#E9A23B]" />
                              <span className="text-sm font-semibold text-neutral-100">{paper.session}</span>
                              <span className="font-mono text-xs text-neutral-400">{paper.code}</span>
                              {paper.downloaded ? (
                                <span className="text-[11px] text-neutral-400">({paper.sizeKb} KB)</span>
                              ) : null}
                            </div>
                          </div>

                          <div className="flex shrink-0 flex-wrap items-center gap-2">
                            {paper.localUrl ? (
                              <button
                                type="button"
                                onClick={() =>
                                  onPreviewFile({
                                    name: `${grp.courseCode}_${paper.session}.pdf`,
                                    url: paper.localUrl,
                                    ext: "pdf",
                                  })
                                }
                                className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-[#2e2e2e] px-2.5 py-1 text-xs font-semibold text-neutral-200 hover:bg-[#383838]"
                              >
                                <Eye className="h-3 w-3" /> View PDF
                              </button>
                            ) : null}

                            {paper.localUrl ? (
                              st === "done" ? (
                                <>
                                  <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/35 bg-emerald-500/15 px-2 py-1 text-xs font-semibold text-emerald-300">
                                    <CheckCircle2 className="h-3 w-3" /> Indexed
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      onAskInChat(
                                        `Summarize the key topics and important questions from ${grp.courseCode} ${grp.subjectName} (${paper.session})`
                                      )
                                    }
                                    className="inline-flex items-center gap-1 rounded-lg border border-[#E9A23B]/40 bg-[#E9A23B]/15 px-2.5 py-1 text-xs font-semibold text-[#f6c56b] hover:bg-[#E9A23B]/25"
                                  >
                                    <Sparkles className="h-3 w-3" /> Ask AI
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  disabled={st === "busy"}
                                  onClick={() => void indexSingleFile(paper.localUrl, grp.courseCode)}
                                  className="inline-flex items-center gap-1 rounded-lg border border-[#E9A23B]/40 bg-[#E9A23B]/15 px-2.5 py-1 text-xs font-semibold text-[#f6c56b] hover:bg-[#E9A23B]/25 disabled:opacity-50"
                                >
                                  {st === "busy" ? (
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                  ) : (
                                    <Sparkles className="h-3 w-3" />
                                  )}
                                  {st === "busy" ? "Indexing..." : st === "err" ? "Retry Index" : "Index AI"}
                                </button>
                              )
                            ) : null}

                            <a
                              href={paper.remoteUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-[#2e2e2e] px-2.5 py-1 text-xs font-semibold text-neutral-300 hover:bg-[#383838]"
                            >
                              Portal <ExternalLink className="h-3 w-3" />
                            </a>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-[#262626] p-4">
            <h1 className="text-base font-bold text-white">DCRUST University Syllabus &amp; Schemes Explorer</h1>
            <p className="mt-0.5 text-xs text-neutral-400">
              Filter by branch or year, view schemes/syllabi, or index them for instant RAG Q&amp;A.
            </p>
            <div className="relative mt-3">
              <Search className="pointer-events-none absolute top-3 left-3.5 h-4 w-4 text-neutral-400" />
              <input
                type="search"
                autoFocus
                value={sylQuery}
                onChange={(e) => setSylQuery(e.target.value)}
                placeholder="Filter syllabus by title, scheme, degree, or keyword..."
                aria-label="Search Syllabus"
                className="w-full rounded-xl border border-white/10 bg-[#1a1a1a] py-2.5 pr-4 pl-10 text-sm text-white placeholder-neutral-500 focus:border-[#5B8FC7] focus:outline-none"
              />
            </div>

            <div className="mt-3 flex flex-wrap gap-1.5">
              {SYLLABUS_BRANCHES.map((b) => (
                <button
                  key={b.id || "all-b"}
                  type="button"
                  onClick={() => setSylBranch(b.id)}
                  className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                    sylBranch === b.id
                      ? "border-[#5B8FC7]/50 bg-[#5B8FC7]/20 text-[#a8c7e8]"
                      : "border-white/10 bg-[#1f1f1f] text-neutral-400 hover:text-neutral-200"
                  }`}
                >
                  {b.label}
                </button>
              ))}
            </div>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1.5">
                {SYLLABUS_YEARS.map((y) => (
                  <button
                    key={y.id || "all-y"}
                    type="button"
                    onClick={() => setSylYear(y.id)}
                    className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                      sylYear === y.id
                        ? "border-[#E9A23B]/50 bg-[#E9A23B]/20 text-[#f6c56b]"
                        : "border-white/10 bg-[#1f1f1f] text-neutral-400 hover:text-neutral-200"
                    }`}
                  >
                    {y.label}
                  </button>
                ))}
              </div>
              <span className="text-[11px] text-neutral-400">
                {sylLoading ? "Loading syllabus..." : `${sylItems.length} document(s)`}
              </span>
            </div>
          </div>

          {!sylReady ? (
            <div className="rounded-xl border border-white/10 bg-[#242424] p-6 text-center text-xs text-neutral-400">
              No local syllabus catalog found. Run <code className="text-neutral-200">smriti syllabus sync</code> to download schemes.
            </div>
          ) : sylItems.length === 0 && !sylLoading ? (
            <div className="rounded-xl border border-white/10 bg-[#242424] p-6 text-center text-xs text-neutral-400">
              No syllabus files match your current filters.
            </div>
          ) : (
            <div className="divide-y divide-white/10 overflow-hidden rounded-xl border border-white/10 bg-[#242424]">
              {sylItems.map((item, idx) => {
                const st = getIndexState(item);
                return (
                  <div
                    key={`${item.remoteUrl}-${idx}`}
                    className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition hover:bg-white/[0.03]"
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-start gap-2">
                        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-[#E9A23B]" />
                        <div className="text-sm font-semibold text-neutral-100">{item.title}</div>
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
                        {item.downloaded ? <span className="text-neutral-400">· {item.sizeKb} KB</span> : null}
                      </div>
                    </div>

                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      {item.localUrl ? (
                        <button
                          type="button"
                          onClick={() =>
                            onPreviewFile({
                              name: `${item.title}.${(item.fileType || "pdf").toLowerCase()}`,
                              url: item.localUrl,
                              ext: (item.fileType || "pdf").toLowerCase(),
                            })
                          }
                          className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-[#2e2e2e] px-2.5 py-1 text-xs font-semibold text-neutral-200 hover:bg-[#383838]"
                        >
                          <Eye className="h-3 w-3" /> View
                        </button>
                      ) : null}

                      {item.localUrl ? (
                        st === "done" ? (
                          <>
                            <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-500/35 bg-emerald-500/15 px-2 py-1 text-xs font-semibold text-emerald-300">
                              <CheckCircle2 className="h-3 w-3" /> Indexed
                            </span>
                            <button
                              type="button"
                              onClick={() => onAskInChat(`Summarize the subjects and syllabus in ${item.title}`)}
                              className="inline-flex items-center gap-1 rounded-lg border border-[#E9A23B]/40 bg-[#E9A23B]/15 px-2.5 py-1 text-xs font-semibold text-[#f6c56b] hover:bg-[#E9A23B]/25"
                            >
                              <Sparkles className="h-3 w-3" /> Ask AI
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            disabled={st === "busy"}
                            onClick={() => void indexSingleFile(item.localUrl, item.branch)}
                            className="inline-flex items-center gap-1 rounded-lg border border-[#E9A23B]/40 bg-[#E9A23B]/15 px-2.5 py-1 text-xs font-semibold text-[#f6c56b] hover:bg-[#E9A23B]/25 disabled:opacity-50"
                          >
                            {st === "busy" ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Sparkles className="h-3 w-3" />
                            )}
                            {st === "busy" ? "Indexing..." : st === "err" ? "Retry Index" : "Index AI"}
                          </button>
                        )
                      ) : null}

                      <a
                        href={item.remoteUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-[#2e2e2e] px-2.5 py-1 text-xs font-semibold text-neutral-300 hover:bg-[#383838]"
                      >
                        Portal <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
