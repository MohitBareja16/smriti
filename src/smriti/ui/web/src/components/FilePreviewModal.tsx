import { Download, ExternalLink, FileText } from "lucide-react";
import type { PreviewFile } from "../types";
import { ModalDialog } from "./ModalDialog";

interface FilePreviewModalProps {
  file: PreviewFile | null;
  onClose: () => void;
}

export function FilePreviewModal({ file, onClose }: FilePreviewModalProps) {
  const isIframeFriendly = Boolean(
    file && (file.ext === "pdf" || file.ext === "html" || file.url.toLowerCase().includes(".pdf"))
  );

  return (
    <ModalDialog
      open={Boolean(file)}
      onClose={onClose}
      wide
      title={file?.name || "Document Preview"}
      subtitle={file?.ext ? `${file.ext.toUpperCase()} document from your local Smriti archive` : undefined}
    >
      {file ? (
        <div className="flex h-full flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 bg-[#2a2a2a] px-3.5 py-2 text-xs">
            <span className="flex items-center gap-2 text-neutral-200">
              <FileText className="h-4 w-4 text-[#E9A23B]" />
              <span className="truncate font-mono">{file.name}</span>
            </span>
            <div className="flex items-center gap-2">
              <a
                href={file.url}
                download={file.name}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 font-semibold text-neutral-200 transition hover:bg-white/10"
              >
                <Download className="h-3.5 w-3.5" /> Download
              </a>
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#5B8FC7]/40 bg-[#5B8FC7]/15 px-3 py-1.5 font-semibold text-[#a8c7e8] transition hover:bg-[#5B8FC7]/25"
              >
                New Tab <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </div>

          {isIframeFriendly ? (
            <iframe
              title={file.name}
              src={file.url}
              className="min-h-[64vh] w-full flex-1 rounded-xl border border-white/10 bg-white"
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-8 text-center">
              <FileText className="h-10 w-10 text-indigo-400" />
              <p className="text-sm text-zinc-300">
                Inline browser preview isn&apos;t supported for <code>.{file.ext || "file"}</code> documents.
              </p>
              <a
                href={file.url}
                download={file.name}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
              >
                <Download className="h-4 w-4" /> Download {file.name}
              </a>
            </div>
          )}
        </div>
      ) : null}
    </ModalDialog>
  );
}
