"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { IconButton } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";

export function Dialog({ open, onClose, title, description, children, footer, size = "md" }: {
  open: boolean; onClose: () => void; title: string; description?: ReactNode; children: ReactNode; footer?: ReactNode; size?: "md" | "lg" | "xl";
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = `${useId()}-title`;
  const descriptionId = `${titleId}-description`;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClose={onClose}
      onClick={(e) => { if (e.target === ref.current) onClose(); }}
      className={cn(
        "m-auto w-[calc(100%-2rem)] rounded-lg border border-line bg-surface p-0 text-fg shadow-pop backdrop:bg-black/50",
        size === "md" ? "max-w-lg" : size === "lg" ? "max-w-3xl" : "max-w-6xl",
      )}
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div>
          <h2 id={titleId} className="text-base font-semibold">{title}</h2>
          {description ? <p id={descriptionId} className="mt-0.5 text-sm text-fg-muted">{description}</p> : null}
        </div>
        <IconButton label="Close" size="sm" onClick={onClose} icon={<Icons.x size={16} />} />
      </div>
      <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
      {footer ? <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div> : null}
    </dialog>
  );
}
