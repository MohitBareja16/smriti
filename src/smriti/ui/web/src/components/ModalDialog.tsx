import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

interface ModalDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  wide?: boolean;
  children: ReactNode;
}

/**
 * Accessible modal dialog built on the native HTML <dialog> top layer.
 * Follows modern-web-guidance: showModal(), closedby="any" + pointer fallback, and overscroll containment.
 */
export function ModalDialog({ open, onClose, title, subtitle, wide = false, children }: ModalDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  // Progressive fallback for browsers without native <dialog closedby="any"> (e.g. Safari)
  useEffect(() => {
    const el = ref.current;
    if (!el || "closedBy" in HTMLDialogElement.prototype) return;

    const outside = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };

    let pressedOutside = false;
    const onDown = (e: PointerEvent) => {
      pressedOutside = outside(e);
    };
    const onUp = (e: PointerEvent) => {
      if (pressedOutside && outside(e)) {
        el.close();
      }
      pressedOutside = false;
    };

    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
    };
  }, []);

  const handleClose = () => {
    const el = ref.current;
    if (el) el.returnValue = "";
    onClose();
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={handleClose}
      {...({ closedby: "any" } as Record<string, string>)}
      className={`m-auto w-[calc(100%-2rem)] ${
        wide ? "max-w-5xl h-[86vh]" : "max-w-2xl max-h-[85vh]"
      } rounded-2xl border border-white/12 bg-[#212121] p-0 text-[#ececec] shadow-2xl open:flex open:flex-col`}
    >
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-5 py-3.5 shrink-0">
        <div className="min-w-0">
          <h1 id={titleId} className="truncate text-base font-bold text-white">
            {title}
          </h1>
          {subtitle ? <p className="truncate text-xs text-zinc-400">{subtitle}</p> : null}
        </div>
        <button
          type="button"
          onClick={() => ref.current?.close()}
          aria-label="Close dialog"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-300 transition hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="scroller min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
    </dialog>
  );
}
