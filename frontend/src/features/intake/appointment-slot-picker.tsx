"use client";

import { useMemo, useState } from "react";
import { DayPicker } from "react-day-picker";
import { casesApi, type PatientCase, type PatientRouting, type Slot } from "@/lib/api";
import { cn, initials } from "@/lib/utils";
import { Icons } from "@/components/ui/icons";
import { Spinner } from "@/components/ui/button";
import { useToast } from "@/components/ui/feedback";

const TIME_LABEL = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === tomorrow.toDateString()) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function partOfDay(iso: string): "Morning" | "Afternoon" | "Evening" {
  const h = new Date(iso).getHours();
  if (h < 12) return "Morning";
  if (h < 17) return "Afternoon";
  return "Evening";
}

// Headless: no react-day-picker/style.css import, styled entirely through classNames below so
// it stays on this app's semantic Tailwind tokens rather than the library's own look.
const CALENDAR_CLASS_NAMES = {
  months: "flex",
  month: "space-y-3",
  month_caption: "flex items-center justify-center px-9 text-sm font-semibold",
  caption_label: "capitalize",
  nav: "flex items-center justify-between",
  button_previous: "flex h-7 w-7 items-center justify-center rounded-md text-fg-muted hover:bg-sunken disabled:pointer-events-none disabled:opacity-30",
  button_next: "flex h-7 w-7 items-center justify-center rounded-md text-fg-muted hover:bg-sunken disabled:pointer-events-none disabled:opacity-30",
  month_grid: "w-full border-collapse",
  weekdays: "flex",
  weekday: "w-9 text-center text-[11px] font-medium uppercase tracking-wide text-fg-subtle",
  weeks: "",
  week: "flex",
  day: "p-0.5 text-center",
  day_button: "flex h-8 w-8 items-center justify-center rounded-full text-sm transition-colors hover:bg-sunken",
  selected: "!bg-brand !text-brand-fg hover:!bg-brand",
  today: "font-bold text-brand",
  disabled: "text-fg-subtle/40 pointer-events-none hover:bg-transparent",
  outside: "text-fg-subtle/40",
};

/** A 2026-style booking widget: react-day-picker for the day (headless, our own Tailwind
 * tokens - see CALENDAR_CLASS_NAMES) over a grouped time grid, scoped to the slots the care
 * navigator already offered for this case (never a free HMS query from the browser). Picking a
 * different one only changes which slot goes into the appointment request - the clinic still
 * confirms it, same as the sequential default. */
export function AppointmentSlotPicker({ caseId, routing, locked, onUpdated }: {
  caseId: string;
  routing: PatientRouting;
  locked?: boolean;
  onUpdated?: (detail: PatientCase) => void;
}) {
  const toast = useToast();
  const options = useMemo(
    () => (routing.slot_options.length ? routing.slot_options : routing.suggested_slot ? [routing.suggested_slot] : []),
    [routing.slot_options, routing.suggested_slot],
  );
  const [selectedId, setSelectedId] = useState<string | null>(routing.selected_slot_id ?? options[0]?.id ?? null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const days = useMemo(() => {
    const byDay = new Map<string, Slot[]>();
    for (const slot of options) {
      const key = dateKey(new Date(slot.start));
      if (!byDay.has(key)) byDay.set(key, []);
      byDay.get(key)!.push(slot);
    }
    return byDay;
  }, [options]);
  const availableDates = useMemo(() => [...days.values()].map((slots) => new Date(slots[0].start)), [days]);

  const selectedSlot = options.find((s) => s.id === selectedId) ?? null;
  const [activeDate, setActiveDate] = useState<Date | undefined>(selectedSlot ? new Date(selectedSlot.start) : availableDates[0]);

  // Re-sync when a fresh routing prop lands (e.g. patient-results.tsx's "Check for updates"),
  // so a stale slot/date from before a clinic reassignment doesn't linger. Adjusted during
  // render (React's documented pattern for this), not an effect, so it applies before paint.
  const routingKey = `${routing.selected_slot_id ?? ""}:${options.map((s) => s.id).join(",")}`;
  const [syncedKey, setSyncedKey] = useState(routingKey);
  if (routingKey !== syncedKey) {
    setSyncedKey(routingKey);
    const next = routing.selected_slot_id ?? options[0]?.id ?? null;
    setSelectedId(next);
    const slot = options.find((s) => s.id === next) ?? null;
    setActiveDate(slot ? new Date(slot.start) : availableDates[0]);
  }

  const activeSlots = (activeDate && days.get(dateKey(activeDate))) ?? [];
  const grouped = ["Morning", "Afternoon", "Evening"] as const;

  if (!options.length) {
    return <p className="text-sm text-fg-subtle">No open slot found yet. The clinic will reach out to schedule.</p>;
  }

  async function pick(slot: Slot) {
    if (slot.id === selectedId || locked) return;
    setPendingId(slot.id);
    try {
      const updated = await casesApi.selectSlot(caseId, slot.id);
      setSelectedId(slot.id);
      onUpdated?.(updated);
      toast.push({ tone: "success", message: `Time changed to ${TIME_LABEL.format(new Date(slot.start))} ${dayLabel(slot.start)}.` });
    } catch (err) {
      toast.push({ tone: "danger", message: err instanceof Error ? err.message : "Could not change the time." });
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-soft text-sm font-semibold text-brand">
          {initials(routing.doctor_name)}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{routing.doctor_name ?? "A clinician will be assigned"}</p>
          <p className="truncate text-xs text-fg-muted">{routing.department_name} · {routing.appointment_type_label}</p>
        </div>
      </div>

      <div className="flex justify-center rounded-lg border border-line bg-surface py-2">
        <DayPicker
          mode="single"
          required={false}
          selected={activeDate}
          onSelect={(d) => d && setActiveDate(d)}
          defaultMonth={availableDates[0]}
          disabled={(date) => !days.has(dateKey(date))}
          classNames={CALENDAR_CLASS_NAMES}
          components={{
            Chevron: ({ orientation }) => (orientation === "left" ? <Icons.chevronRight size={16} className="rotate-180" /> : <Icons.chevronRight size={16} />),
          }}
        />
      </div>

      <div className="space-y-3">
        {grouped.map((part) => {
          const slots = activeSlots.filter((s) => partOfDay(s.start) === part);
          if (!slots.length) return null;
          return (
            <div key={part}>
              <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-fg-subtle">
                {part === "Morning" ? <Icons.sun size={12} /> : part === "Evening" ? <Icons.moon size={12} /> : <Icons.clock size={12} />}
                {part}
              </p>
              <div className="flex flex-wrap gap-2">
                {slots.map((slot) => {
                  const active = slot.id === selectedId;
                  const busy = pendingId === slot.id;
                  return (
                    <button
                      key={slot.id}
                      type="button"
                      disabled={locked || pendingId !== null}
                      onClick={() => void pick(slot)}
                      aria-pressed={active}
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors disabled:cursor-default",
                        active
                          ? "border-brand bg-brand text-brand-fg"
                          : "border-line bg-surface text-fg hover:border-brand-ring hover:bg-brand-soft disabled:hover:border-line disabled:hover:bg-surface",
                      )}
                    >
                      {busy ? <Spinner className="h-3.5 w-3.5" /> : active ? <Icons.check size={13} /> : null}
                      {TIME_LABEL.format(new Date(slot.start))}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-1.5 text-xs text-fg-subtle">
        <Icons.info size={13} className="shrink-0" />
        {locked ? "This time is set for your visit." : "This time is set on your clinician's calendar. Pick a different one anytime before your review."}
      </div>
    </div>
  );
}
