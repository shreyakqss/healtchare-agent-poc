"use client";

import { useState } from "react";
import type { PreviousVisit, VisitType } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, Icons } from "@/components/ui";

/** What the visit is about, chosen before intake starts: a new problem, or a follow-up of one of
 * the patient's completed visits. A follow-up goes to the same department with the doctor who saw
 * them last listed first, and the assistant asks about how that problem has gone since. */
export function VisitStart({ followUpOptions, registered, busy, disabled, onStart }: {
  followUpOptions: PreviousVisit[];
  registered: boolean;
  busy: boolean;
  disabled?: boolean;
  onStart: (visitType: VisitType, followUpOf: string | null) => void;
}) {
  const [type, setType] = useState<VisitType>("new");
  const [picked, setPicked] = useState<string | null>(followUpOptions[0]?.case_id ?? null);
  const canFollowUp = followUpOptions.length > 0;
  const ready = type === "new" || (canFollowUp && picked !== null);

  return (
    <Card>
      <CardHeader
        title="What is this visit about?"
        description={registered
          ? "Your details are on file from your profile, so we go straight to your visit."
          : "First visit? After this you'll register once, and your details are kept in your profile."}
      />
      <CardBody className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Visit type">
          <Choice
            selected={type === "new"} onSelect={() => setType("new")} icon={<Icons.plus size={18} />}
            title="New health concern" text="Something you haven't seen us about before."
          />
          <Choice
            selected={type === "follow_up"} onSelect={() => setType("follow_up")} icon={<Icons.refresh size={18} />}
            disabled={!canFollowUp}
            title="Follow-up visit"
            text={canFollowUp ? "About a problem from one of your previous visits." : "Available once you have a completed visit."}
          />
        </div>

        {type === "follow_up" && canFollowUp ? (
          <fieldset className="space-y-2">
            <legend className="mb-2 text-sm font-medium">Which visit is this a follow-up to?</legend>
            {followUpOptions.map((v) => (
              <label
                key={v.case_id}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-md border px-3.5 py-3 text-sm transition-colors",
                  picked === v.case_id ? "border-brand bg-brand-soft" : "border-line bg-surface hover:bg-sunken",
                )}
              >
                <input
                  type="radio" name="follow-up-of" className="mt-1 h-4 w-4 shrink-0 accent-brand"
                  checked={picked === v.case_id} onChange={() => setPicked(v.case_id)} disabled={disabled}
                />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{firstLine(v.diagnosis) ?? v.complaint ?? "Visit"}</span>
                  <span className="mt-0.5 block text-xs text-fg-muted">
                    {formatDate(v.visit_at)}
                    {v.doctor_name ? ` · ${v.doctor_name}` : ""}
                    {v.department_name ? ` · ${v.department_name}` : ""}
                  </span>
                  {v.complaint && v.diagnosis ? (
                    <span className="mt-1 block text-xs text-fg-muted">You came in with: {v.complaint}</span>
                  ) : null}
                </span>
              </label>
            ))}
            <p className="flex items-start gap-2 pt-1 text-xs text-fg-muted">
              <Icons.info size={14} className="mt-0.5 shrink-0" />
              The doctor you saw last is offered first when you book. You can still pick any doctor in that department.
            </p>
          </fieldset>
        ) : null}

        <div className="flex justify-end">
          <Button
            onClick={() => onStart(type, type === "follow_up" ? picked : null)}
            loading={busy} disabled={disabled || !ready} icon={<Icons.arrowRight size={16} />}
          >
            {type === "follow_up" ? "Start follow-up" : "Start visit"}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function firstLine(text: string | null): string | null {
  return text?.split("\n").map((l) => l.trim()).find(Boolean) ?? null;
}

function Choice({ selected, onSelect, icon, title, text, disabled }: {
  selected: boolean; onSelect: () => void; icon: React.ReactNode; title: string; text: string; disabled?: boolean;
}) {
  return (
    <button
      type="button" role="radio" aria-checked={selected} onClick={onSelect} disabled={disabled}
      className={cn(
        "flex items-start gap-3 rounded-lg border p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        selected ? "border-brand bg-brand-soft" : "border-line bg-surface hover:bg-sunken",
      )}
    >
      <span className={cn("mt-0.5 shrink-0", selected ? "text-brand" : "text-fg-muted")}>{icon}</span>
      <span>
        <span className="flex items-center gap-2 text-sm font-semibold">
          {title}
          {selected ? <Badge tone="brand">Selected</Badge> : null}
        </span>
        <span className="mt-0.5 block text-xs text-fg-muted">{text}</span>
      </span>
    </button>
  );
}
