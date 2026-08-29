"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form";
import { Icons } from "@/components/ui/icons";
import { ATTACHMENT_KINDS } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function Composer({
  onSend, disabled, busy, requireConsent, consented, onConsentChange, placeholder, initialText,
  onAttach, uploading,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  busy?: boolean;
  requireConsent: boolean;
  consented: boolean;
  onConsentChange: (v: boolean) => void;
  placeholder?: string;
  /** Starting draft text. Read once at mount - the caller remounts this component (via a
   * `key`) to apply a new one. */
  initialText?: string;
  /** Attach a document without leaving the conversation. Omit to hide the attach control. */
  onAttach?: (file: File, kind: string) => void;
  uploading?: boolean;
}) {
  const [text, setText] = useState(initialText ?? "");
  const [attachOpen, setAttachOpen] = useState(false);
  // File first, kind second, deliberately unselected - picking a file no longer silently
  // uploads it under whatever kind happened to be first in the list.
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [attachKind, setAttachKind] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = text.trim().length > 0 && !disabled && !busy && (!requireConsent || consented);

  function focusAndSize(el: HTMLTextAreaElement | null) {
    ref.current = el;
    if (!el || !initialText) return;
    el.focus();
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }

  function submit() {
    if (!canSend) return;
    onSend(text);
    setText("");
    if (ref.current) ref.current.style.height = "auto";
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="space-y-3">
      {requireConsent ? (
        <label className="flex cursor-pointer items-start gap-3 rounded-md border border-line bg-sunken px-3.5 py-3 text-sm leading-5 text-fg-muted">
          <input type="checkbox" checked={consented} onChange={(e) => onConsentChange(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-brand" />
          <span>I understand this is a demo and agree to the processing of the information I share. A clinician reviews everything before any decision is made.</span>
        </label>
      ) : null}

      {onAttach && attachOpen ? (
        <div className="rounded-lg border border-line bg-sunken px-3.5 py-3">
          <input
            ref={fileRef} type="file" className="sr-only" accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.webp,.gif"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) { setPendingFile(f); setAttachKind(""); }
              e.target.value = "";
            }}
          />
          {!pendingFile ? (
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-fg-muted">Attach a report, lab result or other document.</p>
              <div className="flex shrink-0 gap-2">
                <Button type="button" size="sm" disabled={disabled} icon={<Icons.upload size={14} />}
                  onClick={() => fileRef.current?.click()}>
                  Choose file
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setAttachOpen(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2.5">
              <div className="flex items-center gap-2 text-sm">
                <Icons.file size={16} className="shrink-0 text-fg-muted" />
                <span className="min-w-0 flex-1 truncate font-medium">{pendingFile.name}</span>
                <Button type="button" size="sm" variant="ghost" onClick={() => { setPendingFile(null); setAttachKind(""); }}>
                  Change
                </Button>
              </div>
              <div>
                <label htmlFor="attach-kind" className="mb-1 block text-xs font-medium text-fg-muted">What kind of document is this?</label>
                <Select id="attach-kind" value={attachKind} onChange={(e) => setAttachKind(e.target.value)} disabled={disabled}>
                  <option value="" disabled>Select a document type…</option>
                  {ATTACHMENT_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
                </Select>
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" size="sm" variant="ghost" onClick={() => { setPendingFile(null); setAttachKind(""); setAttachOpen(false); }}>
                  Cancel
                </Button>
                <Button type="button" size="sm" loading={uploading} disabled={disabled || !attachKind}
                  onClick={() => { onAttach(pendingFile, attachKind); setPendingFile(null); setAttachKind(""); setAttachOpen(false); }}>
                  Attach
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : null}

      <div className={cn(
        "flex items-end gap-2 rounded-lg border border-line bg-surface p-2 shadow-card transition-colors focus-within:border-brand-ring focus-within:ring-2 focus-within:ring-brand-ring/25",
        disabled && "opacity-60",
      )}>
        {onAttach ? (
          <Button
            type="button" variant="ghost" onClick={() => setAttachOpen((v) => !v)} disabled={disabled}
            aria-label="Attach a document" aria-expanded={attachOpen} title="Attach a document"
            className="h-11 w-11 shrink-0 px-0" icon={<Icons.paperclip size={18} />}
          />
        ) : null}
        <label htmlFor="intake-composer" className="sr-only">Your message</label>
        <textarea
          id="intake-composer"
          ref={focusAndSize}
          rows={1}
          value={text}
          disabled={disabled}
          placeholder={placeholder ?? "Describe what brings you in today…"}
          onChange={(e) => {
            setText(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
          }}
          onKeyDown={onKey}
          className="max-h-44 min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-6 text-fg placeholder:text-fg-subtle focus:outline-none"
        />
        <Button type="button" onClick={submit} disabled={!canSend} loading={busy} aria-label="Send message" className="h-11 w-11 shrink-0 px-0" icon={<Icons.send size={18} />} />
      </div>
      <p className="px-1 text-xs text-fg-subtle">
        Enter to send · Shift+Enter for a new line{onAttach ? " · paperclip to attach a report" : ""}. If this is an emergency, call your local emergency number.
      </p>
    </div>
  );
}