import { useEffect, useState } from "react";
import { CalendarCheck, CalendarDays, KeyRound, Trash2 } from "lucide-react";
import { clearSamarthCredentials, createThread, fetchSamarthStatus, syncSamarth } from "../api";
import type { AttachmentItem, SamarthCredStatus, UiElementPayload } from "../types";
import { ModalDialog } from "./ModalDialog";

interface SamarthModalProps {
  open: boolean;
  threadId: string | null;
  onClose: () => void;
  onSynced: (result: {
    kind: "attendance" | "timetable";
    threadId: string;
    text: string;
    ui_element: UiElementPayload;
    attachments: AttachmentItem[];
  }) => void;
}

export function SamarthModal({ open, threadId, onClose, onSynced }: SamarthModalProps) {
  const [status, setStatus] = useState<SamarthCredStatus | null>(null);
  const [roll, setRoll] = useState("");
  const [password, setPassword] = useState("");
  const [saveCreds, setSaveCreds] = useState(true);
  const [busyKind, setBusyKind] = useState<"attendance" | "timetable" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    void fetchSamarthStatus()
      .then((s) => {
        setStatus(s);
        if (s.roll_number) setRoll(s.roll_number);
      })
      .catch(() => {});
  }, [open]);

  const handleSync = async (kind: "attendance" | "timetable") => {
    setBusyKind(kind);
    setError(null);
    try {
      const targetTid =
        threadId || (await createThread(`DCRUST ${kind === "attendance" ? "Attendance" : "Timetable"}`)).id;
      const res = await syncSamarth(kind, {
        roll_number: roll.trim() || undefined,
        password: password || undefined,
        save_creds: saveCreds,
        thread_id: targetTid,
      });
      onSynced({
        kind,
        threadId: targetTid,
        text: res.text,
        ui_element: res.ui_element,
        attachments: res.attachments,
      });
      setPassword("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Samarth sync failed");
    } finally {
      setBusyKind(null);
    }
  };

  const handleClear = async () => {
    await clearSamarthCredentials();
    setStatus({ saved: false, roll_number: null, vault_unlocked: status?.vault_unlocked ?? false });
    setPassword("");
  };

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="DCRUST eSamarth Sync"
      subtitle="Fetch live current-semester Attendance & Timetable/Calendar"
    >
      <div className="space-y-4 text-sm">
        {status?.saved ? (
          <div className="flex items-center justify-between rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-2.5 text-xs text-emerald-300">
            <span className="flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              Encrypted credentials saved for roll no <strong>{status.roll_number}</strong>
            </span>
            <button
              type="button"
              onClick={() => void handleClear()}
              className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 text-zinc-300 hover:text-rose-300"
            >
              <Trash2 className="h-3 w-3" /> Forget
            </button>
          </div>
        ) : null}

        <div className="space-y-3">
          <div>
            <label htmlFor="samarth-roll" className="mb-1 block text-xs font-semibold text-zinc-300">
              Roll Number / Enrolment
            </label>
            <input
              id="samarth-roll"
              type="text"
              autoFocus
              value={roll}
              onChange={(e) => setRoll(e.target.value)}
              placeholder="e.g. 23001001065"
              className="w-full rounded-xl border border-white/12 bg-[#141414] px-3.5 py-2.5 text-sm text-white placeholder-zinc-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="samarth-pass" className="mb-1 block text-xs font-semibold text-zinc-300">
              Portal Password {status?.saved ? "(leave blank to use saved)" : ""}
            </label>
            <input
              id="samarth-pass"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={status?.saved ? "••••••••••••" : "Enter Samarth password"}
              className="w-full rounded-xl border border-white/12 bg-[#141414] px-3.5 py-2.5 text-sm text-white placeholder-zinc-500 focus:border-indigo-500 focus:outline-none"
            />
          </div>

          {status?.vault_unlocked ? (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-300">
              <input
                type="checkbox"
                checked={saveCreds}
                onChange={(e) => setSaveCreds(e.target.checked)}
                className="h-4 w-4 rounded accent-indigo-500"
              />
              Encrypt and remember credentials in local Vault
            </label>
          ) : null}
        </div>

        {error ? (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-300">
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-2.5 pt-1 sm:grid-cols-2">
          <button
            type="button"
            disabled={busyKind !== null}
            onClick={() => void handleSync("attendance")}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/15 px-4 py-2.5 text-xs font-bold text-emerald-300 transition hover:bg-emerald-500/25 disabled:opacity-50"
          >
            <CalendarCheck className="h-4 w-4" />
            {busyKind === "attendance" ? "Syncing Attendance..." : "Check Attendance (75% Rule)"}
          </button>
          <button
            type="button"
            disabled={busyKind !== null}
            onClick={() => void handleSync("timetable")}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#5B8FC7]/40 bg-[#5B8FC7]/20 px-4 py-2.5 text-xs font-bold text-[#a8c7e8] transition hover:bg-[#5B8FC7]/30 disabled:opacity-50"
          >
            <CalendarDays className="h-4 w-4" />
            {busyKind === "timetable" ? "Syncing Timetable..." : "Check Timetable & Calendar"}
          </button>
        </div>
      </div>
    </ModalDialog>
  );
}
