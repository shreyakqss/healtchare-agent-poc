"use client";

import { useId, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Tabs<T extends string>({ tabs, value, onChange, className, idPrefix }: {
  tabs: Array<{ id: T; label: ReactNode; count?: number }>; value: T; onChange: (id: T) => void; className?: string; idPrefix?: string;
}) {
  const generatedPrefix = useId();
  const prefix = idPrefix ?? generatedPrefix;

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next].id);
    event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  }

  return (
    <div role="tablist" className={cn("flex gap-1 border-b border-line", className)}>
      {tabs.map((t, index) => {
        const active = t.id === value;
        return (
          <button
            key={t.id} role="tab" type="button" aria-selected={active} tabIndex={active ? 0 : -1}
            id={`${prefix}-tab-${t.id}`} aria-controls={`${prefix}-panel-${t.id}`}
            onClick={() => onChange(t.id)} onKeyDown={(event) => moveFocus(event, index)}
            className={cn(
              "-mb-px flex h-10 items-center gap-2 border-b-2 px-3 text-sm font-medium transition-colors",
              active ? "border-brand text-fg" : "border-transparent text-fg-muted hover:text-fg",
            )}
          >
            {t.label}
            {t.count !== undefined ? (
              <span className={cn("tabular rounded-full px-1.5 text-[11px]", active ? "bg-brand-soft text-brand" : "bg-sunken text-fg-muted")}>{t.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
