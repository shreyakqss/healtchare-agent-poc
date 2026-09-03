"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { EventClickArg, EventContentArg, EventInput } from "@fullcalendar/core";
import type { CaseListItem, Priority } from "@/lib/api";
import { Button, Dialog, EmptyState, IconButton, Icons, PriorityBadge } from "@/components/ui";
import type { Me } from "@/features/doctor/use-doctor";
import { isMine } from "@/features/doctor/worklist";

const TIME_LABEL = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

type ViewKey = "dayGridMonth" | "timeGridWeek" | "timeGridDay";
const VIEWS: { key: ViewKey; label: string; icon: keyof typeof Icons }[] = [
  { key: "dayGridMonth", label: "Month", icon: "grid" },
  { key: "timeGridWeek", label: "Week", icon: "list" },
  { key: "timeGridDay", label: "Day", icon: "clock" },
];

// Real Tailwind classes, not inline colours (see CLAUDE.md: never interpolate a colour) -
// FullCalendar's own backgroundColor/borderColor props would mean setting inline style instead.
const PRIORITY_CLASS: Record<Priority, string> = {
  high: "!border-danger !bg-danger-soft",
  medium: "!border-warning !bg-warning-soft",
  low: "!border-success !bg-success-soft",
};

/** A real month/week/day calendar (FullCalendar) so a clinician can see past and future
 * appointments the same way they'd read Google Calendar/Teams, not just today. Every
 * appointment here is still an advisory, drafted request - the calendar is a time-ordered
 * view of the same cases the worklist used to show, nothing more. */
export function DoctorCalendar({ cases, me }: { cases: CaseListItem[]; me: Me }) {
  const calendarRef = useRef<FullCalendar | null>(null);
  const [openCase, setOpenCase] = useState<(CaseListItem & { appointment_start: string }) | null>(null);
  const [view, setView] = useState<ViewKey>("dayGridMonth");
  const [title, setTitle] = useState("");
  const scheduled = useMemo(
    () => cases.filter((c): c is CaseListItem & { appointment_start: string } => isMine(c, me) && !!c.appointment_start),
    [cases, me],
  );

  if (!scheduled.length) {
    return (
      <EmptyState
        icon={<Icons.calendar size={20} />}
        title="Nothing on the calendar yet"
        description="No appointments with a scheduled time for you right now."
      />
    );
  }

  const events: EventInput[] = scheduled.map((c) => ({
    id: c.case_id,
    title: c.demographics.name || "Unnamed patient",
    start: c.appointment_start,
    classNames: [PRIORITY_CLASS[c.priority ?? "low"], "!text-fg"],
    extendedProps: { caseId: c.case_id },
  }));

  function eventContent(arg: EventContentArg) {
    return (
      <div className="flex min-w-0 items-center gap-1 truncate px-1 text-[11px] leading-tight">
        <Icons.clock size={11} className="shrink-0" />
        <span className="font-semibold">{arg.timeText}</span>
        <span className="truncate">{arg.event.title}</span>
      </div>
    );
  }

  function onEventClick(arg: EventClickArg) {
    const found = scheduled.find((c) => c.case_id === arg.event.extendedProps.caseId);
    if (found) setOpenCase(found);
  }

  function go(action: "prev" | "next" | "today") {
    const api = calendarRef.current?.getApi();
    if (!api) return;
    api[action]();
    setTitle(api.view.title);
  }

  function changeView(key: ViewKey) {
    const api = calendarRef.current?.getApi();
    if (!api) return;
    api.changeView(key);
    setView(key);
    setTitle(api.view.title);
  }

  return (
    <div className="rounded-lg border border-line bg-surface p-3 shadow-card [&_.fc]:text-fg [&_.fc-daygrid-day-number]:text-fg-muted [&_.fc-col-header-cell-cushion]:text-fg-subtle [&_.fc-day-today]:bg-brand-soft/30 [&_th]:border-line [&_td]:border-line [&_.fc-scrollgrid]:border-line">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <IconButton label="Previous" size="sm" icon={<Icons.chevronLeft size={16} />} onClick={() => go("prev")} />
          <IconButton label="Next" size="sm" icon={<Icons.chevronRight size={16} />} onClick={() => go("next")} />
          <Button variant="secondary" size="sm" icon={<Icons.calendar size={15} />} onClick={() => go("today")}>Today</Button>
        </div>
        <p className="min-w-0 flex-1 truncate text-sm font-semibold">{title}</p>
        <div className="flex items-center gap-1 rounded-md border border-line bg-sunken p-0.5">
          {VIEWS.map(({ key, label, icon }) => {
            const Icon = Icons[icon];
            const active = view === key;
            return (
              <Button
                key={key}
                variant={active ? "primary" : "ghost"}
                size="sm"
                icon={<Icon size={15} />}
                onClick={() => changeView(key)}
                className={active ? "" : "text-fg-muted"}
                aria-pressed={active}
              >
                {label}
              </Button>
            );
          })}
        </div>
      </div>

      <FullCalendar
        ref={calendarRef}
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="dayGridMonth"
        headerToolbar={false}
        height="auto"
        events={events}
        eventContent={eventContent}
        eventClick={onEventClick}
        dayMaxEvents={3}
        datesSet={(arg) => setTitle(arg.view.title)}
      />

      <Dialog
        open={!!openCase}
        onClose={() => setOpenCase(null)}
        title={openCase?.demographics.name || "Unnamed patient"}
        description={openCase ? TIME_LABEL.format(new Date(openCase.appointment_start)) : undefined}
        footer={openCase ? (
          <Link href={`/cases/${openCase.case_id}`}>
            <Button size="lg" icon={<Icons.external size={16} />}>Open appointment</Button>
          </Link>
        ) : null}
      >
        {openCase ? (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-xs text-fg-subtle">Age</dt><dd className="font-medium">{openCase.demographics.age ?? "–"}</dd></div>
            <div><dt className="text-xs text-fg-subtle">Severity</dt><dd><PriorityBadge priority={openCase.priority} /></dd></div>
            <div className="col-span-2"><dt className="text-xs text-fg-subtle">Complaint</dt><dd className="font-medium">{openCase.chief_complaint ?? "–"}</dd></div>
          </dl>
        ) : null}
      </Dialog>
    </div>
  );
}
