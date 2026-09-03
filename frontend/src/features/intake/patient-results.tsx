import type { ReactNode } from "react";
import type { PatientCase } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { AppointmentSlotPicker } from "@/features/intake/appointment-slot-picker";

/** Render only the backend's patient-safe visit projection. `onUpdated` reports a slot change
 * back to whichever caller owns this case's state (patient-portal's active case, or the visits
 * list) - this component holds none of its own, so it never goes stale behind a fresh fetch.
 * `onRefresh`/`refreshing` add a "Check for updates" action to the header - one card, one
 * status message, the booking widget inline underneath it. */
export function PatientResults({ detail, onUpdated, onRefresh, refreshing }: {
  detail: PatientCase; onUpdated?: (detail: PatientCase) => void; onRefresh?: () => void; refreshing?: boolean;
}) {
  const approved = detail.review_decision === "approve" || detail.review_decision === "edit";
  const refreshAction = onRefresh ? (
    <Button size="sm" variant="secondary" loading={refreshing} icon={<Icons.refresh size={14} />} onClick={onRefresh}>
      Check for updates
    </Button>
  ) : null;

  if (detail.status === "REJECTED") {
    return (
      <Panel icon={<Icons.info size={18} />} title="Please contact the clinic">
        <p>The care team could not proceed with this request online. Please call the clinic so they can help you directly.</p>
      </Panel>
    );
  }
  if (!approved) {
    return (
      <Panel icon={<Icons.clock size={18} />} title="Your answers are with the care team" tone="pending" action={refreshAction}>
        <p>A clinician will review them shortly. Your visit is saved under &ldquo;My visits&rdquo;, so you can close this page and come back any time.</p>
        {detail.routing ? (
          <div className="mt-5 border-t border-line pt-5">
            <p className="mb-3 text-sm font-medium text-fg">Your appointment</p>
            <AppointmentSlotPicker caseId={detail.case_id} routing={detail.routing} onUpdated={onUpdated} />
          </div>
        ) : null}
      </Panel>
    );
  }

  const routing = detail.routing;
  const completed = detail.status === "COMPLETED";
  const sections = detail.final_summary ?? {};
  const friendly = asString(sections.patient_friendly_summary);
  const prescription = asString(sections.prescription);
  const testsOrdered = asString(sections.tests_ordered);
  const followUps = asStringList(sections.follow_up_instructions);
  const mode = asString(sections.consultation_mode) ?? detail.consultation_mode;
  const reference = detail.appointment_reference;

  return (
    <div className="space-y-4">
      <Panel icon={<Icons.checkCircle size={18} />} title={completed ? "Your visit summary" : "Your plan has been approved"} tone="good">
        {routing ? (
          <AppointmentSlotPicker caseId={detail.case_id} routing={routing} locked={completed} onUpdated={onUpdated} />
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
            {testsOrdered ? <Item label="Tests / investigations" value={<span className="whitespace-pre-wrap">{testsOrdered}</span>} /> : null}
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

function Panel({ icon, title, tone = "neutral", action, children }: {
  icon: ReactNode; title: string; tone?: "neutral" | "pending" | "good"; action?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-surface p-5 shadow-card">
      <div className="flex flex-wrap items-center gap-3">
        <span className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
          tone === "neutral" && "bg-sunken text-fg-muted",
          tone === "pending" && "bg-info-soft text-info",
          tone === "good" && "bg-success-soft text-success",
        )} aria-hidden="true">{icon}</span>
        <h3 className="min-w-0 flex-1 text-base font-semibold">{title}</h3>
        {action}
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
