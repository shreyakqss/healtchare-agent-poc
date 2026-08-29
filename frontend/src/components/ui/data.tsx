import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn, initials, progressWidth } from "@/lib/utils";

export function Table({ className, regionLabel, ...rest }: HTMLAttributes<HTMLTableElement> & { regionLabel: string }) {
  return (
    <div className="w-full overflow-x-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" role="region" aria-label={regionLabel} tabIndex={0}>
      <table className={cn("w-full border-collapse text-sm", className)} {...rest} />
    </div>
  );
}
export function Th({ className, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={cn("bg-sunken px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-fg-subtle first:rounded-tl-lg last:rounded-tr-lg", className)} {...rest} />;
}
export function Td({ className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-t border-line px-4 py-3 align-middle", className)} {...rest} />;
}

/* ---------- Stat ---------- */

export function Stat({ label, value, hint, tone, icon }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "danger" | "warning" | "success" | "brand"; icon?: ReactNode }) {
  const toneCls = { danger: "text-danger", warning: "text-warning", success: "text-success", brand: "text-brand" };
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3.5 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-fg-muted">{label}</p>
        {icon ? <span className="text-fg-subtle">{icon}</span> : null}
      </div>
      <p className={cn("tabular mt-1 text-2xl font-semibold leading-8", tone ? toneCls[tone] : "text-fg")}>{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-fg-subtle">{hint}</p> : null}
    </div>
  );
}

/* ---------- Key / value list ---------- */

export function KeyValue({ items, className, columns = 1 }: { items: Array<{ label: string; value: ReactNode }>; className?: string; columns?: 1 | 2 | 3 }) {
  return (
    <dl className={cn("grid gap-x-6 gap-y-3", columns === 2 && "sm:grid-cols-2", columns === 3 && "sm:grid-cols-3", className)}>
      {items.map((it) => (
        <div key={it.label} className="min-w-0">
          <dt className="text-xs text-fg-subtle">{it.label}</dt>
          <dd className="mt-0.5 text-sm text-fg break-words">{it.value ?? "–"}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ---------- Avatar ---------- */

export function Avatar({ name, size = "md", className }: { name: string | null | undefined; size?: "sm" | "md" | "lg"; className?: string }) {
  const s = { sm: "h-7 w-7 text-[11px]", md: "h-9 w-9 text-xs", lg: "h-12 w-12 text-sm" }[size];
  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center rounded-full bg-brand-soft font-semibold text-brand", s, className)} aria-hidden="true">
      {initials(name)}
    </span>
  );
}

/* ---------- Horizontal bar list ---------- */

export function BarList({ items, total }: { items: Array<{ label: string; value: number; tone?: string }>; total?: number }) {
  const max = total ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.label}>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="truncate text-fg">{i.label}</span>
            <span className="tabular ml-3 text-fg-muted">{i.value}</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
            <div className={cn("h-full rounded-full", progressWidth(i.value, max), i.tone ?? "bg-brand")} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ---------- Steps ---------- */

export function Steps({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Progress">
      {steps.map((s, i) => {
        const state = i < current ? "done" : i === current ? "current" : "todo";
        return (
          <li key={s} className="flex items-center gap-2">
            <span className={cn(
              "flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold",
              state === "done" && "bg-brand text-brand-fg",
              state === "current" && "border-2 border-brand text-brand",
              state === "todo" && "border border-line-strong text-fg-subtle",
            )} aria-current={state === "current" ? "step" : undefined}>
              {state === "done" ? "✓" : i + 1}
            </span>
            <span className={cn("text-sm", state === "todo" ? "text-fg-subtle" : "text-fg")}>{s}</span>
            {i < steps.length - 1 ? <span className="mx-1 h-px w-6 bg-line" aria-hidden="true" /> : null}
          </li>
        );
      })}
    </ol>
  );
}
