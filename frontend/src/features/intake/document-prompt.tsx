"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Icons } from "@/components/ui/icons";
import { attachmentKindLabel } from "@/lib/constants";

/** The clinic's required documents, asked for inside the conversation. Each one is satisfied
 * by a file or by an explicit skip - the same gate the backend enforces on intake completion.
 * Renders nothing once every required kind is resolved. */
export function DocumentPrompt({ pendingKinds, onUpload, onSkip, onHide, busy, disabled }: {
  pendingKinds: string[];
  onUpload: (file: File, kind: string) => void;
  onSkip: (kind: string, reason?: string) => void;
  onHide: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  const [skipDraft, setSkipDraft] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  if (!pendingKinds.length) return null;

  return (
    <div className="rounded-lg border border-line bg-surface p-4 shadow-card">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand" aria-hidden="true">
          <Icons.paperclip size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium">Documents that would help your clinician</p>
            <Button type="button" size="sm" variant="ghost" onClick={onHide}>Hide</Button>
          </div>
          <p className="mt-0.5 text-xs leading-5 text-fg-muted">
            Attach what you have. If you don&apos;t have one, skip it - your intake still goes through.
          </p>

          <ul className="mt-3 space-y-2">
            {pendingKinds.map((kind) => (
              <li key={kind} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm">{attachmentKindLabel(kind)}</span>
                <input
                  ref={(el) => { inputRefs.current[kind] = el; }}
                  type="file" className="sr-only" accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.webp,.gif"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) onUpload(f, kind);
                    e.target.value = "";
                  }}
                />
                <Button type="button" size="sm" variant="secondary" loading={busy} disabled={disabled}
                  icon={<Icons.upload size={14} />} onClick={() => inputRefs.current[kind]?.click()}>
                  Upload
                </Button>
                <Button type="button" size="sm" variant="ghost" disabled={disabled}
                  onClick={() => { setSkipDraft(skipDraft === kind ? null : kind); setReason(""); }}>
                  Skip
                </Button>
                {skipDraft === kind ? (
                  <div className="flex w-full items-center gap-2 pt-1">
                    <Input className="h-9" placeholder="Optional reason (e.g. don't have it with me)"
                      value={reason} onChange={(e) => setReason(e.target.value)} />
                    <Button type="button" size="sm" loading={busy}
                      onClick={() => { onSkip(kind, reason); setSkipDraft(null); setReason(""); }}>
                      Confirm skip
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setSkipDraft(null)}>Cancel</Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
