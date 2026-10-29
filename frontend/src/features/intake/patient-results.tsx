import type { ReactNode } from "react";
import { casesApi, type EmergencyAdvice, type PatientCase } from "@/lib/api";
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

  // Red flag: the emergency, first and alone - no booking is offered, so nothing competes with
  // "call an ambulance" (the pattern NHS 111 online and symptom checkers use).
  if (detail.emergency) {
    return <EmergencyNotice advice={detail.emergency} action={refreshAction} />;
  }

  if (detail.status === "REJECTED") {
    return (
      <Panel icon={<Icons.info size={18} />} title="Please contact the clinic">
        <p>The care team could not proceed with this request online. Please call the clinic so they can help you directly.</p>
      </Panel>
    );
  }
  if (!approved) {
    const booked = Boolean(detail.routing?.slot_confirmed);
    const passed = booked && Boolean(detail.routing?.slot_passed);
    return (
      <Panel icon={booked ? <Icons.checkCircle size={18} /> : <Icons.clock size={18} />}
        title={passed ? "Your appointment time has passed" : booked ? "Your appointment is booked" : "Choose your appointment"}
        tone={booked ? "good" : "pending"} action={refreshAction}>
        <p>
          {passed
            ? "This visit's appointment time is over. "
            : booked
            ? "Your doctor will go through your answers before the visit. "
            : "Pick a doctor and time below. It's booked as soon as you confirm. "}
          Your visit is saved under &ldquo;My visits&rdquo;, so you can close this page and come back any time.
        </p>
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
      <Panel icon={<Icons.checkCircle size={18} />} tone="good"
        title={completed ? "Your visit summary" : routing?.slot_passed ? "Your appointment time has passed" : "Your appointment is booked"}>
        {routing ? (
          <AppointmentSlotPicker caseId={detail.case_id} routing={routing} locked={completed} onUpdated={onUpdated} />
        ) : (
          <p>Your doctor has gone through your answers. The clinic will contact you if anything changes.</p>
        )}
      </Panel>

      {completed ? (
        <div className="space-y-4 overflow-hidden rounded-lg border border-line bg-surface p-5 shadow-card">
          {detail.has_letterhead ? (
            // eslint-disable-next-line @next/next/no-img-element -- the clinic's own uploaded letterhead, not a static import
            <img src={casesApi.letterheadUrl(detail.case_id)} alt="Clinic letterhead" className="-mx-5 -mt-5 mb-1 block w-[calc(100%+2.5rem)] max-w-none border-b border-line bg-white object-contain" />
          ) : null}
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

function EmergencyNotice({ advice, action }: { advice: EmergencyAdvice; action?: ReactNode }) {
  const tel = (n: string) => `tel:${n.replace(/[^\d+]/g, "")}`;
  return (
    <section role="alert" className="space-y-5 rounded-lg border-2 border-danger bg-danger-soft p-5 shadow-card">
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-danger text-danger-fg" aria-hidden="true">
          <Icons.alert size={22} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold uppercase tracking-widest text-danger">Emergency</p>
          <h3 className="text-xl font-semibold text-danger">Call an ambulance now</h3>
          <p className="mt-1 text-sm leading-6 text-fg">
            What you told us may be a medical emergency. Don&rsquo;t wait for an appointment.
          </p>
        </div>
        {action}
      </div>

      <a href={tel(advice.ambulance_number)}
        className="flex items-center justify-center gap-2 rounded-lg bg-danger px-4 py-4 text-lg font-bold text-danger-fg hover:opacity-90">
        <Icons.alert size={20} /> Call ambulance {advice.ambulance_number}
      </a>
      <p className="-mt-3 text-center text-sm text-fg-muted">
        Can&rsquo;t get through? Call <a href={tel(advice.emergency_number)} className="font-semibold text-danger underline">{advice.emergency_number}</a>.
      </p>

      <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-fg">
        <li>Don&rsquo;t drive yourself.</li>
        <li>If you can, have someone stay with you until help arrives.</li>
        <li>Keep your phone with you. Your answers have already been passed to the care team.</li>
      </ul>
    </section>
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
