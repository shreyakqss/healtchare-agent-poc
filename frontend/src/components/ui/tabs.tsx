"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Tabs<T extends string>({ tabs, value, onChange, className }: {
  tabs: Array<{ id: T; label: ReactNode; count?: number }>; value: T; onChange: (id: T) => void; className?: string;
}) {
  return (
    <div role="tablist" className={cn("flex gap-1 border-b border-line", className)}>
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id} role="tab" type="button" aria-selected={active} onClick={() => onChange(t.id)}
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