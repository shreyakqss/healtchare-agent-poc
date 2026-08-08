"use client";

import { useState } from "react";
import type { HospitalDoc } from "@/lib/api";
import { Button, Tag, icons, inputClass } from "@/lib/ui";

/** Mutate a draft copy of the config. Callers never mutate in place. */
export type Update = (mutate: (draft: HospitalDoc) => void) => void;

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  mono,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  mono?: boolean;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="eyebrow">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={`${inputClass} mt-1.5 ${mono ? "font-mono" : ""} disabled:opacity-50`}
      />
      {hint && <span className="mt-1 block text-[11px] text-faint">{hint}</span>}
    </label>
  );
}

/**
 * A list of short strings edited as removable chips — how keyword sets and
 * symptom lists read in a rule, without exposing YAML sequence syntax.
 */
export function ChipInput({
  values,
  onChange,
  placeholder = "Add…",
  tone = "neutral",
}: {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  tone?: "neutral" | "accent" | "high" | "med" | "info";
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const value = draft.trim().toLowerCase();
    if (!value || values.includes(value)) {
      setDraft("");
      return;
    }
    onChange([...values, value]);
    setDraft("");
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded border border-line bg-ink px-2 py-1.5">
      {values.map((value) => (
        <Tag key={value} tone={tone} className="pr-1">
          {value}
          <button
            onClick={() => onChange(values.filter((v) => v !== value))}
            className="ml-0.5 rounded px-0.5 text-faint hover:text-high"
            aria-label={`Remove ${value}`}
          >
            ×
          </button>
        </Tag>
      ))}
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            commit();
          }
          if (event.key === "Backspace" && !draft && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={commit}
        placeholder={placeholder}
        className="min-w-[7rem] flex-1 bg-transparent py-0.5 text-sm text-text outline-none placeholder:text-faint"
      />
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`flex w-full items-center gap-3 rounded border px-3 py-2.5 text-left transition-colors ${
        checked ? "border-accent/40 bg-accent/6" : "border-line hover:border-faint"
      }`}
    >
      <span
        className={`grid size-4 shrink-0 place-items-center rounded border ${
          checked ? "border-accent bg-accent/20 text-accent" : "border-line text-transparent"
        }`}
      >
        <icons.check className="text-[11px]" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm text-text">{label}</span>
        {hint && <span className="block text-[11px] text-faint">{hint}</span>}
      </span>
    </button>
  );
}

/** Editable card used for departments, doctors, appointment types and rules. */
export function EditorCard({
  title,
  badge,
  onRemove,
  children,
}: {
  title: React.ReactNode;
  badge?: React.ReactNode;
  onRemove?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-line bg-surface/70">
      <div className="flex items-center gap-2 border-b border-line-soft px-4 py-2.5">
        <span className="min-w-0 truncate text-sm font-medium text-text">{title}</span>
        {badge}
        {onRemove && (
          <button
            onClick={onRemove}
            className="ml-auto shrink-0 rounded p-1 text-faint transition-colors hover:bg-high/10 hover:text-high"
            aria-label="Remove"
          >
            <icons.trash className="text-[14px]" />
          </button>
        )}
      </div>
      <div className="space-y-3 px-4 py-3.5">{children}</div>
    </div>
  );
}

export function AddButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <Button onClick={onClick} className="w-full justify-center border-dashed py-3">
      <icons.plus className="text-[15px]" />
      {label}
    </Button>
  );
}
