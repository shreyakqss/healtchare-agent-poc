"use client";

import { useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { Icons } from "@/components/ui/icons";

export function ChipInput({ value, onChange, placeholder = "Add and press Enter", label, className }: {
  value: string[]; onChange: (next: string[]) => void; placeholder?: string; label: string; className?: string;
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const parts = draft.split(",").map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    const next = [...value];
    for (const p of parts) if (!next.includes(p)) next.push(p);
    onChange(next);
    setDraft("");
  }
  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(); }
    if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
  }

  return (
    <div className={cn("flex min-h-10 flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1.5 focus-within:border-brand-ring focus-within:ring-2 focus-within:ring-brand-ring/30", className)}>
      {value.map((v) => (
        <span key={v} className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-2 py-0.5 text-xs font-medium text-brand">
          {v}
          <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(value.filter((x) => x !== v))} className="rounded-full p-0.5 hover:bg-brand/10">
            <Icons.x size={12} />
          </button>
        </span>
      ))}
      <input
        aria-label={label} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={commit}
        placeholder={value.length ? "" : placeholder}
        className="min-w-28 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-fg-subtle"
      />
    </div>
  );
}