import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { FileUp, KeyRound, Lock, ShieldCheck, Trash2 } from "lucide-react";
import { deleteVaultDoc, fetchVaultDocs, unlockVault, uploadVaultFiles } from "../api";
import type { VaultDocument } from "../types";
import { ModalDialog } from "./ModalDialog";

interface VaultModalProps {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}

export function VaultModal({ open, onClose, onChanged }: VaultModalProps) {
  const [docs, setDocs] = useState<VaultDocument[]>([]);
  const [demoMode, setDemoMode] = useState(false);
  const [unlocked, setUnlocked] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await fetchVaultDocs();
      setDocs(data.documents);
      setDemoMode(data.demo_mode);
      setUnlocked(data.vault_unlocked);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Failed to load vault");
    }
  };

  useEffect(() => {
    if (open) {
      setStatus(null);
      void load();
    }
  }, [open]);

  const handleUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setBusy(true);
    setStatus(null);
    try {
      const res = await uploadVaultFiles(files);
      const summary = res.results
        .map((r) =>
          r.ok
            ? r.duplicate
              ? `${r.name}: already indexed`
              : `${r.title || r.name}: added`
            : `${r.name}: ${r.error}`
        )
        .join(" · ");
      setStatus(summary);
      await load();
      onChanged();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  const handleDelete = async (id: number) => {
    setBusy(true);
    try {
      await deleteVaultDoc(id);
      await load();
      onChanged();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const handleUnlock = async (e: FormEvent) => {
    e.preventDefault();
    if (!passphrase) return;
    setBusy(true);
    setStatus(null);
    try {
      await unlockVault(passphrase);
      setPassphrase("");
      setStatus("Vault unlocked for this session.");
      await load();
      onChanged();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Unlock failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="Local Document Vault"
      subtitle={`${docs.length} indexed · ${unlocked ? "Vault unlocked (AES-256-GCM)" : "Vault locked"}`}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <div className="flex items-center gap-3 text-xs text-zinc-300">
            {unlocked ? (
              <ShieldCheck className="h-5 w-5 text-emerald-400 shrink-0" />
            ) : (
              <Lock className="h-5 w-5 text-amber-400 shrink-0" />
            )}
            <div>
              <div className="font-semibold text-white">
                {demoMode ? "Demo mode (read-only)" : "Add PDF, DOCX, Markdown, or TXT documents"}
              </div>
              <div className="text-zinc-400">
                Personal documents (marksheets, datesheets, certificates) are encrypted automatically.
              </div>
            </div>
          </div>

          {!demoMode ? (
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[#5B8FC7] px-3.5 py-2 text-xs font-semibold text-[#0e1a26] transition hover:bg-[#7ab0eb]">
              <FileUp className="h-4 w-4" />
              <span>{busy ? "Uploading..." : "Upload files"}</span>
              <input
                type="file"
                multiple
                accept=".pdf,.docx,.md,.txt"
                onChange={handleUpload}
                disabled={busy}
                className="sr-only"
              />
            </label>
          ) : null}
        </div>

        {!unlocked && !demoMode ? (
          <form
            onSubmit={(e) => void handleUnlock(e)}
            className="flex flex-wrap items-center gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs"
          >
            <KeyRound className="h-4 w-4 shrink-0 text-amber-300" />
            <input
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              placeholder="Enter vault passphrase to unlock encrypted personal files"
              className="min-w-[200px] flex-1 rounded-lg border border-white/15 bg-[#1b1b1b] px-3 py-1.5 text-white placeholder-neutral-500 focus:border-[#E9A23B] focus:outline-none"
            />
            <button
              type="submit"
              disabled={busy || !passphrase}
              className="rounded-lg bg-[#E9A23B] px-3 py-1.5 font-semibold text-[#1a1207] transition hover:bg-[#f2b354] disabled:opacity-50"
            >
              Unlock Vault
            </button>
          </form>
        ) : null}

        {status ? (
          <div className="rounded-lg border border-[#5B8FC7]/35 bg-[#5B8FC7]/10 px-3.5 py-2 text-xs text-[#a8c7e8]">
            {status}
          </div>
        ) : null}

        <div className="divide-y divide-white/10 overflow-hidden rounded-xl border border-white/10 bg-[#171717]">
          {docs.length === 0 ? (
            <div className="p-6 text-center text-xs text-zinc-400">
              Your vault is empty. Upload study notes, PYQs, or marksheets to index them locally.
            </div>
          ) : (
            docs.map((doc) => (
              <div key={doc.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-xs">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-zinc-100">{doc.title}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
                    <span className="capitalize">{doc.doc_type.replace(/_/g, " ")}</span>
                    <span>·</span>
                    <span className={doc.sensitive ? "text-emerald-400" : "text-zinc-400"}>
                      {doc.sensitive ? "Encrypted personal" : "Library"}
                    </span>
                    {doc.course ? <span>· {doc.course}</span> : null}
                  </div>
                </div>
                {!demoMode ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleDelete(doc.id)}
                    aria-label={`Delete ${doc.title}`}
                    className="rounded-lg p-1.5 text-zinc-400 transition hover:bg-rose-500/15 hover:text-rose-400"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
            ))
          )}
        </div>
      </div>
    </ModalDialog>
  );
}
