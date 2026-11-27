import { Icons } from "@/components/ui/icons";
import type { WeeklyHours } from "@/lib/api";

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_SHORT: Record<string, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };

/** "Mon – Fri" for a run of three or more consecutive days, else "Mon, Wed, Fri". */
export function daysLabel(days: string[]): string {
  const idx = days.map((d) => WEEK.indexOf(d));
  const consecutive = idx.every((v, i) => i === 0 || v === idx[i - 1] + 1);
  if (consecutive && days.length >= 3) return `${DAY_SHORT[days[0]]} – ${DAY_SHORT[days[days.length - 1]]}`;
  return days.map((d) => DAY_SHORT[d] ?? d).join(", ");
}

/** Clinic-local "16:00" -> "4 PM", "09:30" -> "9:30 AM". Formatted as wall-clock text, never
 * converted through the browser's timezone, because these are the clinic's hours. */
export function clockLabel(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h < 12 ? "AM" : "PM";
  const hour = h % 12 || 12;
  return m ? `${hour}:${String(m).padStart(2, "0")} ${suffix}` : `${hour} ${suffix}`;
}

export function DoctorHours({ hours }: { hours: WeeklyHours[] }) {
  return (
    <div className="shrink-0 rounded-lg border border-line bg-sunken px-3.5 py-2.5">
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-fg-subtle">
        <Icons.clock size={12} />
        Consulting hours
      </p>
      {/* One grid for every row, so day names, start times, dashes and end times each line up
          in their own column however many shifts or day groups there are. */}
      <dl className="grid grid-cols-[auto_1fr_auto_auto_auto] items-baseline gap-x-2 gap-y-1 text-xs tabular-nums">
        {hours.map((group) =>
          group.times.map(([start, end], i) => (
            <div key={`${group.days.join("-")}-${start}`} className="contents">
              {i === 0 ? <dt className="font-medium text-fg">{daysLabel(group.days)}</dt> : <dt className="sr-only">{daysLabel(group.days)}</dt>}
              <span aria-hidden className={i === 0 ? "" : "col-start-2"} />
              <dd className="text-right text-fg-muted">{clockLabel(start)}</dd>
              <span aria-hidden className="text-fg-subtle">–</span>
              <span className="text-fg-muted">{clockLabel(end)}</span>
            </div>
          )),
        )}
      </dl>
    </div>
  );
}
