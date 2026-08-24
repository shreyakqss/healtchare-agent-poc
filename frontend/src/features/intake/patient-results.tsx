import type { ReactNode } from "react";
import type { CaseDetail } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";
import { Icons } from "@/components/ui/icons";
import { Badge } from "@/components/ui/badge";

/**
 * The review gate, made visible. Fields are read BY NAME so a new backend key
 * can never leak to a patient. Never shown here: triage priority, the
 * pre-screening briefing, rule evidence, draft task internals.
 */
export function PatientResults({ detail }: { detail: CaseDetail }) {
  const approved = detail.review?.decision === "approve" || detail.review?.decision === "edit";

  if (detail.status === "REJECTED") {
    return (
      <Panel icon={<Icons.info size={18} />} title="Please contact the clinic">
        <p>The care team could not proceed with this request online. Please call the clinic so they can help you directly.</p>
      </Panel>
    );
  }
  if (!approved) {
    return (
      <Panel icon={<Icons.clock size={18} />} title="Being reviewed by the care team" tone="pending">
        <p>Your answers have been received. A clinician will look at them before anything is scheduled. Check back a little later.</p>
      </Panel>
    );
  }

  const routing = detail.routing;
  const completed = detail.status === "COMPLETED";
  const sections = detail.final_summary?.sections ?? {};
  const friendly = asString(sections.patient_friendly_summary);
  const prescription = asString(sections.prescription);
  const followUps = asStringList(sections.follow_up_instructions);
  const mode = asString(sections.consultation_mode) ?? detail.consultation_notes.at(-1)?.consultation_mode ?? null;
  const reference = detail.care_tasks[0]?.hms_reference ?? null;

  return (
    <div className="space-y-4">
      <Panel icon={<Icons.checkCircle size={18} />} title={completed ? "Your visit summary" : "Your plan has been approved"} tone="good">
        {routing ? (
          <dl className="grid gap-3 sm:grid-cols-2">
            <Item label="Department" value={routing.department_name} />
            <Item label="Doctor" value={routing.doctor_name ?? "To be assigned"} />
            <Item label="Appointment type" value={routing.appointment_type_label} />
            {routing.suggested_slot ? (
              <Item label="Proposed time" value={<>{formatDateTime(routing.suggested_slot.start)} <Badge className="ml-1">The clinic will confirm</Badge></>} />
            ) : null}
          </dl>
        ) : (
          <p>The care team has approved your request. They will contact you with the next step.</p>
        )}
      </Panel>

      {completed ? (
        <div className="space-y-4 rounded-lg border border-line bg-surface p-5 shadow-card">
          {friendly ? <p className="text-[15px] leading-7">{friendly}</p> : null}
          <dl className="grid gap-4">
            {mode ? <Item label="Consultation" value={mode === "virtual" ? "Video consultation" : "In person"} /> : null}
            {prescription ? <Item label="Prescription" value={<span className="whitespace-pre-wrap">{prescription}</span>} /> : null}
            {followUps.length ? (
              <Item label="Follow-up instructions" value={<ul className="list-disc space-y-1 pl-5">{followUps.map((f) => <li key={f}>{f}</li>)}</ul>} />
            ) : null}
            {reference ? <Item label="Appointment request reference" value={<span className="font-mono">{reference}</span>} /> : null}
          </dl>
        </div>
      ) : null}
    </div>
  );
}

function Panel({ icon, title, tone = "neutral", children }: { icon: ReactNode; title: string; tone?: "neutral" | "pending" | "good"; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-5 shadow-card">
      <div className="flex items-center gap-3">
        <span className={cn(
          "flex h-9 w-9 items-center justify-center rounded-full",
          tone === "neutral" && "bg-sunken text-fg-muted",
          tone === "pending" && "bg-info-soft text-info",
          tone === "good" && "bg-success-soft text-success",
        )} aria-hidden="true">{icon}</span>
        <h3 className="text-base font-semibold">{title}</h3>
      </div>
      <div className="mt-4 text-sm leading-6 text-fg-muted">{children}</div>
    </section>
  );
}

function Item({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-fg-subtle">{label}</dt>
      <dd className="mt-0.5 text-sm text-fg">{value}</dd>
    </div>
  );
}

function asString(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}
function asStringList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x.trim().length > 0) : [];
}