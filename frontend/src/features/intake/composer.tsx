"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

export function Composer({
  onSend, disabled, busy, requireConsent, consented, onConsentChange, placeholder, initialText,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  busy?: boolean;
  requireConsent: boolean;
  consented: boolean;
  onConsentChange: (v: boolean) => void;
  placeholder?: string;
  /** Starting draft text, e.g. a picked sample patient's opening line. Read once at mount -
   * the caller remounts this component (via `key`) to apply a new one. */
  initialText?: string;
}) {
  const [text, setText] = useState(initialText ?? "");
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

      <div className={cn(
        "flex items-end gap-2 rounded-lg border border-line bg-surface p-2 shadow-card transition-colors focus-within:border-brand-ring focus-within:ring-2 focus-within:ring-brand-ring/25",
        disabled && "opacity-60",
      )}>
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
      <p className="px-1 text-xs text-fg-subtle">Enter to send · Shift+Enter for a new line. If this is an emergency, call your local emergency number.</p>
    </div>
  );
}