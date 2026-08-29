export function cn(...parts: unknown[]): string {
  return parts.filter((p): p is string => typeof p === "string" && p.length > 0).join(" ");
}

export function formatDateTime(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = {}): string {
  if (!iso) return "–";
  const value = new Date(iso);
  return Number.isNaN(value.getTime()) ? "–" : value.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", ...opts });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const value = new Date(iso);
  return Number.isNaN(value.getTime()) ? "–" : value.toLocaleDateString(undefined, { dateStyle: "medium" });
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  const value = new Date(iso);
  return Number.isNaN(value.getTime()) ? "–" : value.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** "3 min ago" style, computed against a caller-supplied `now` (render purity). */
export function timeAgo(iso: string | null | undefined, now: number): string {
  if (!iso) return "–";
  const timestamp = new Date(iso).getTime();
  if (Number.isNaN(timestamp)) return "–";
  const diff = Math.max(0, now - timestamp);
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  return name
    .replace(/^Dr\.?\s+/i, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function shortId(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const PROGRESS_WIDTHS = [
  "w-0", "w-[5%]", "w-[10%]", "w-[15%]", "w-[20%]", "w-[25%]", "w-[30%]", "w-[35%]", "w-[40%]", "w-[45%]",
  "w-[50%]", "w-[55%]", "w-[60%]", "w-[65%]", "w-[70%]", "w-[75%]", "w-[80%]", "w-[85%]", "w-[90%]", "w-[95%]", "w-full",
];

export function progressWidth(value: number, max: number): string {
  const index = max > 0 ? Math.round(Math.min(1, Math.max(0, value / max)) * 20) : 0;
  return PROGRESS_WIDTHS[index];
}
