/**
 * Shared presentation primitives.
 *
 * No "use client" — these are pure and render in both server and client trees.
 * Everything here is presentational; anything that needs state lives with the
 * page that owns it.
 */

import type { ReactNode, SVGProps } from "react";

/* --- surfaces ------------------------------------------------------------ */

/**
 * The one container in the app. Square-ish and hairline-bordered rather than a
 * floating rounded card, so a dense page reads as one console instead of a
 * scattering of tiles.
 */
export function Panel({
  title,
  eyebrow,
  actions,
  children,
  className = "",
  bodyClassName = "p-5",
}: {
  title?: ReactNode;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={`rounded-md border border-line bg-surface/80 backdrop-blur-sm ${className}`}
    >
      {(title || eyebrow || actions) && (
        <header className="flex items-center gap-3 border-b border-line-soft px-5 py-3">
          <div className="min-w-0">
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && (
              <h2 className="truncate text-sm font-semibold text-text">{title}</h2>
            )}
          </div>
          {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/** Page heading block — title, one line of context, optional right-hand slot. */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-text">
          {title}
        </h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm text-dim">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/* --- tags ---------------------------------------------------------------- */

const TONES = {
  neutral: "border-line bg-raised text-dim",
  accent: "border-accent/35 bg-accent/10 text-accent",
  info: "border-info/35 bg-info/10 text-info",
  high: "border-high/40 bg-high/12 text-high",
  med: "border-med/40 bg-med/12 text-med",
  low: "border-low/40 bg-low/12 text-low",
} as const;

export type Tone = keyof typeof TONES;

export function Tag({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2 py-0.5 text-[11px] font-medium ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export const priorityTone = (priority?: string | null): Tone =>
  priority === "high" ? "high" : priority === "medium" ? "med" : priority === "low" ? "low" : "neutral";

export function PriorityTag({ priority }: { priority?: string | null }) {
  if (!priority) return <span className="text-faint">—</span>;
  return (
    <Tag tone={priorityTone(priority)} className="uppercase tracking-wide">
      <Dot tone={priorityTone(priority)} />
      {priority}
    </Tag>
  );
}

/** Status → tone. Kept next to the lifecycle it describes, not spread around. */
export const STATUS_TONE: Record<string, Tone> = {
  CREATED: "neutral",
  INGESTING: "info",
  ANALYZING: "info",
  NEEDS_REVIEW: "med",
  APPROVED: "accent",
  COMPLETED: "low",
  REJECTED: "high",
  FAILED: "high",
};

export function StatusTag({ status }: { status: string }) {
  return (
    <Tag tone={STATUS_TONE[status] ?? "neutral"}>{status.replaceAll("_", " ")}</Tag>
  );
}

export function Dot({ tone = "neutral", live = false }: { tone?: Tone; live?: boolean }) {
  const fill = {
    neutral: "bg-faint",
    accent: "bg-accent",
    info: "bg-info",
    high: "bg-high",
    med: "bg-med",
    low: "bg-low",
  }[tone];
  return (
    <span
      className={`inline-block size-1.5 shrink-0 rounded-full ${fill} ${live ? "running-dot" : ""}`}
    />
  );
}

/* --- metrics ------------------------------------------------------------- */

/** One KPI. `trail` takes a sparkline or bar, `hint` a unit or qualifier. */
export function Metric({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}) {
  const accentBar = {
    neutral: "bg-line",
    accent: "bg-accent",
    info: "bg-info",
    high: "bg-high",
    med: "bg-med",
    low: "bg-low",
  }[tone];
  return (
    <div className="relative overflow-hidden rounded-md border border-line bg-surface/80 px-4 py-3.5">
      <span className={`absolute inset-y-0 left-0 w-0.5 ${accentBar}`} />
      <div className="flex items-start justify-between gap-2">
        <p className="eyebrow">{label}</p>
        {icon && <span className="text-faint">{icon}</span>}
      </div>
      <p className="nums mt-2 text-2xl font-semibold tracking-tight text-text">
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-faint">{hint}</p>}
    </div>
  );
}

/* --- charts (hand-rolled: no chart dependency for six bars and a donut) --- */

export type Slice = { label: string; value: number; tone?: Tone };

const TONE_VAR: Record<Tone, string> = {
  neutral: "var(--color-faint)",
  accent: "var(--color-accent)",
  info: "var(--color-info)",
  high: "var(--color-high)",
  med: "var(--color-med)",
  low: "var(--color-low)",
};

/** Horizontal bars — the honest default for a handful of labelled counts. */
export function BarList({ data, empty = "No data yet." }: { data: Slice[]; empty?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) return <p className="text-sm text-faint">{empty}</p>;
  return (
    <ul className="space-y-2.5">
      {data.map((d) => (
        <li key={d.label} className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1">
          <span className="truncate text-sm text-dim">{d.label}</span>
          <span className="nums text-sm font-medium text-text">{d.value}</span>
          <span className="col-span-2 h-1.5 overflow-hidden rounded-full bg-line-soft">
            <span
              className="block h-full rounded-full transition-[width] duration-500"
              style={{
                width: `${(d.value / max) * 100}%`,
                background: TONE_VAR[d.tone ?? "info"],
              }}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Donut for a small part-to-whole split (priority mix). */
export function Donut({
  data,
  size = 132,
  caption,
}: {
  data: Slice[];
  size?: number;
  caption?: string;
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const r = size / 2 - 9;
  const c = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className="flex items-center gap-5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-line-soft)"
          strokeWidth={13}
        />
        {total > 0 &&
          data.map((d) => {
            const length = (d.value / total) * c;
            const dash = (
              <circle
                key={d.label}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={TONE_VAR[d.tone ?? "info"]}
                strokeWidth={13}
                strokeDasharray={`${length} ${c - length}`}
                strokeDashoffset={-offset}
                transform={`rotate(-90 ${size / 2} ${size / 2})`}
              />
            );
            offset += length;
            return dash;
          })}
        <text
          x="50%"
          y="47%"
          textAnchor="middle"
          className="nums fill-text text-xl font-semibold"
        >
          {total}
        </text>
        <text
          x="50%"
          y="62%"
          textAnchor="middle"
          className="fill-faint text-[10px] uppercase tracking-widest"
        >
          {caption ?? "total"}
        </text>
      </svg>
      <ul className="space-y-2 text-sm">
        {data.map((d) => (
          <li key={d.label} className="flex items-center gap-2">
            <Dot tone={d.tone ?? "info"} />
            <span className="text-dim">{d.label}</span>
            <span className="nums ml-auto pl-4 font-medium text-text">{d.value}</span>
            <span className="nums w-10 text-right text-xs text-faint">
              {total ? Math.round((d.value / total) * 100) : 0}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Latency/volume sparkline. Flat line when there is one point — deliberate. */
export function Spark({
  values,
  width = 96,
  height = 26,
  tone = "info",
}: {
  values: number[];
  width?: number;
  height?: number;
  tone?: Tone;
}) {
  if (values.length === 0)
    return <span className="text-xs text-faint">—</span>;
  const max = Math.max(...values, 1);
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const points = values
    .map((v, i) => `${i * step},${height - (v / max) * (height - 3) - 1.5}`)
    .join(" ");
  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={TONE_VAR[tone]}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* --- controls ------------------------------------------------------------ */

const BUTTON_VARIANTS = {
  primary:
    "bg-accent text-on-accent hover:bg-accent/85 disabled:hover:bg-accent font-semibold",
  ghost: "border border-line text-dim hover:border-faint hover:text-text",
  danger: "border border-high/50 text-high hover:bg-high/10",
} as const;

export function Button({
  variant = "ghost",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BUTTON_VARIANTS;
}) {
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${BUTTON_VARIANTS[variant]} ${className}`}
    />
  );
}

export const inputClass =
  "w-full rounded border border-line bg-ink px-3 py-2 text-sm text-text placeholder:text-faint outline-none transition-colors focus:border-accent/60";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="eyebrow">{label}</span>
      {hint && <span className="mt-0.5 block text-xs text-faint">{hint}</span>}
      <span className="mt-1.5 block">{children}</span>
    </label>
  );
}

export function Banner({
  tone,
  children,
}: {
  tone: "error" | "ok" | "warn";
  children: ReactNode;
}) {
  const styles = {
    error: "border-high/45 bg-high/10 text-high",
    ok: "border-accent/40 bg-accent/10 text-accent",
    warn: "border-med/45 bg-med/10 text-med",
  }[tone];
  return (
    <div className={`rounded border px-4 py-2.5 text-sm ${styles}`}>{children}</div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="rounded border border-dashed border-line px-4 py-6 text-center text-sm text-faint">
      {children}
    </p>
  );
}

/**
 * Says the data on screen is invented because the backend is unreachable.
 *
 * Deliberately loud and never dismissible. Preview patients in a clinical UI
 * are indistinguishable from real ones at a glance, so the label has to be the
 * thing you cannot miss — see `lib/demo.ts`.
 */
export function DemoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded border border-med/50 bg-med/10 px-4 py-2.5">
      <span className="mt-0.5 shrink-0 rounded bg-med px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-on-accent">
        Preview
      </span>
      <p className="text-sm leading-6 text-med">{children}</p>
    </div>
  );
}

/* --- formatting ---------------------------------------------------------- */

/** Short case reference. Full UUIDs are unreadable in a queue. */
export const caseRef = (caseId: string) => `HC-${caseId.slice(0, 4).toUpperCase()}`;

export function humanTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** "4m ago" / "2h ago" — waiting time in a queue is relative, not absolute. */
export function since(iso: string, now = Date.now()) {
  const seconds = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

/** Durations here are real elapsed times, often sub-millisecond on seeded
 * rows — show the actual figure rather than rounding it away to "0.0s". */
export function duration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export const titleCase = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (ch) => ch.toUpperCase());

/* --- icons ---------------------------------------------------------------
 * Hand-rolled single-path icons. A dozen glyphs does not justify an icon
 * dependency, and these inherit currentColor and stroke width for free. */

function Icon({ d, ...props }: { d: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      width="1em"
      height="1em"
      aria-hidden
      {...props}
    >
      <path d={d} />
    </svg>
  );
}

export const icons = {
  pulse: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M2 12h4l3-8 4 16 3-8h6" {...p} />
  ),
  users: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M16 19v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8M22 19v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" {...p} />
  ),
  grid: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z" {...p} />
  ),
  building: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M3 21h18M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16M9 8h1M14 8h1M9 12h1M14 12h1M11 21v-4h2v4" {...p} />
  ),
  clock: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7v5l3 2" {...p} />
  ),
  check: (p: SVGProps<SVGSVGElement>) => <Icon d="m4 12 5 5L20 6" {...p} />,
  alert: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M12 8v5M12 17h.01M10.3 3.9 2.4 17a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0" {...p} />
  ),
  file: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5" {...p} />
  ),
  image: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M9 9.5a1 1 0 1 1-2 0 1 1 0 0 1 2 0" {...p} />
  ),
  send: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M21 3 10.5 13.5M21 3l-6.5 18-4-8-8-4z" {...p} />
  ),
  paperclip: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M21 11.5 12.5 20a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 1 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8" {...p} />
  ),
  play: (p: SVGProps<SVGSVGElement>) => <Icon d="M6 4v16l13-8z" {...p} />,
  stop: (p: SVGProps<SVGSVGElement>) => <Icon d="M6 6h12v12H6z" {...p} />,
  refresh: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5" {...p} />
  ),
  stethoscope: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M6 3v6a5 5 0 0 0 10 0V3M4 3h3M15 3h3M11 14v2a5 5 0 0 0 10 0v-2M21 12a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3" {...p} />
  ),
  route: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M6 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4M18 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4M8 18h6a4 4 0 0 0 0-8h-4a4 4 0 0 1 0-8h6" {...p} />
  ),
  shield: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" {...p} />
  ),
  chevron: (p: SVGProps<SVGSVGElement>) => <Icon d="m9 6 6 6-6 6" {...p} />,
  code: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="m8 6-6 6 6 6M16 6l6 6-6 6" {...p} />
  ),
  plus: (p: SVGProps<SVGSVGElement>) => <Icon d="M12 5v14M5 12h14" {...p} />,
  trash: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" {...p} />
  ),
  pill: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M10.5 20.5a5 5 0 0 1-7-7l7-7a5 5 0 0 1 7 7zM7 10l7 7" {...p} />
  ),
  heart: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M12 20s-7-4.4-7-9.4A4.6 4.6 0 0 1 12 7a4.6 4.6 0 0 1 7 3.6c0 5-7 9.4-7 9.4" {...p} />
  ),
  mic: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" {...p} />
  ),
  speaker: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M4 9v6h4l5 4V5L8 9zM16.5 8.5a5 5 0 0 1 0 7M19.5 5.5a9 9 0 0 1 0 13" {...p} />
  ),
  sun: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" {...p} />
  ),
  moon: (p: SVGProps<SVGSVGElement>) => (
    <Icon d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5" {...p} />
  ),
};
