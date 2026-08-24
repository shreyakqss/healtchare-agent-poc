"use client";

import { useState } from "react";
import { hmsApi } from "@/lib/api";
import type { HMSPatient } from "@/lib/api";
import { SAMPLE_PATIENTS, type SamplePatient } from "@/features/intake/sample-patients";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { Avatar } from "@/components/ui/data";
import { cn } from "@/lib/utils";

export function SamplePatientPicker({
  onPrefill, onQuickStart, locked,
}: {
  /** Just fills the message box with their opening line - patient still reviews and sends it. */
  onPrefill: (opening: string, record: HMSPatient | null) => void;
  /** Skips the whole conversation - a complete case, already at pre-screening, in one call. */
  onQuickStart: (key: string) => Promise<void>;
  locked: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busyMrn, setBusyMrn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (locked) return null;

  async function prefill(p: SamplePatient) {
    setBusyMrn(p.mrn);
    setError(null);
    let record: HMSPatient | null = null;
    try {
      record = await hmsApi.patient(p.mrn);
    } catch {
      record = null; // hospital record system unreachable - still let them try the sample, just unlinked
    } finally {
      setBusyMrn(null);
    }
    onPrefill(p.openingLine, record);
    setOpen(false);
  }

  async function quickStart(p: SamplePatient) {
    setBusyMrn(p.mrn);
    setError(null);
    try {
      await onQuickStart(p.key);
      setOpen(false);
    } catch {
      setError("Could not fill that case right now. Try again, or type it yourself below.");
    } finally {
      setBusyMrn(null);
    }
  }

  return (
    <div className="rounded-md border border-dashed border-line-strong px-3.5 py-3">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center justify-between gap-3 text-left">
        <span className="flex items-center gap-2 text-sm font-medium">
          <Icons.sparkles size={16} className="text-fg-muted" /> Try a sample patient
          <span className="text-xs font-normal text-fg-muted">(for demo)</span>
        </span>
        <Icons.chevronDown size={16} className={cn("text-fg-muted transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div className="mt-3 space-y-3">
          <p className="text-xs leading-5 text-fg-muted">
            Fill instantly for a complete case with nothing left to type, or fill the message box and answer the
            rest of the questions yourself.
          </p>
          {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
          <ul className="space-y-2">
            {SAMPLE_PATIENTS.map((p) => {
              const busy = busyMrn === p.mrn;
              return (
                <li key={p.mrn} className="flex items-center gap-2.5 rounded-md border border-line px-3 py-2.5">
                  <Avatar name={p.name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-medium text-fg">{p.name}</span>
                      <span className="shrink-0 text-xs text-fg-muted">{p.age} · {p.sex}</span>
                    </div>
                    <p className="mt-0.5 text-xs leading-4 text-fg-muted">{p.headline}</p>
                    <Badge tone="neutral" className="mt-1.5">{p.tag}</Badge>
                  </div>
                  <div className="flex shrink-0 flex-col gap-1.5 sm:flex-row">
                    <Button size="sm" variant="secondary" disabled={busyMrn !== null} onClick={() => void prefill(p)}>
                      Fill message
                    </Button>
                    <Button size="sm" variant="primary" loading={busy} disabled={busyMrn !== null && !busy} onClick={() => void quickStart(p)}>
                      Fill instantly
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-fg-subtle">Synthetic people for trying the demo. Nobody real is represented.</p>
        </div>
      ) : null}
    </div>
  );
}

