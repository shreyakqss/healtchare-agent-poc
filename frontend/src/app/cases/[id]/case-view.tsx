"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ApiError,
  PRIORITY_STYLES,
  STATUS_STYLES,
  api,
  type AuditEvent,
  type CaseDetail,
} from "@/lib/api";

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
        <h2 className="text-sm font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-zinc-500">{subtitle}</p>}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v) => typeof v === "string") : [];
}

export default function CaseView({
  caseId,
  initialDetail,
  initialAudit,
}: {
  caseId: string;
  initialDetail: CaseDetail;
  initialAudit: AuditEvent[];
}) {
  // Seeded from the server render — no fetch-on-mount effect. Reloads happen
  // in event handlers after a mutation.
  const [detail, setDetail] = useState(initialDetail);
  const [audit, setAudit] = useState(initialAudit);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [reviewerRole, setReviewerRole] = useState("clinician");
  const [editField, setEditField] = useState("");
  const [editValue, setEditValue] = useState("");
  const [doctorId, setDoctorId] = useState(
    initialDetail.routing?.doctor_id ?? "",
  );
  const [notes, setNotes] = useState("");
  const [followUp, setFollowUp] = useState("");

  async function reload() {
    const [caseDetail, auditTrail] = await Promise.all([
      api.getCase(caseId),
      api.audit(caseId),
    ]);
    setDetail(caseDetail);
    setAudit(auditTrail);
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const summarySections = (detail.prescreening_summary?.sections ??
    {}) as Record<string, unknown>;
  const finalSections = (detail.final_summary?.sections ?? {}) as Record<
    string,
    unknown
  >;
  const approved =
    detail.review?.decision === "approve" || detail.review?.decision === "edit";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link href="/dashboard" className="text-sm underline">
            ← Back to dashboard
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {(summarySections.chief_complaint as string) ?? "Patient case"}
          </h1>
          <p className="mt-1 text-xs text-zinc-500">Case {detail.case_id}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded px-2.5 py-1 text-xs font-medium ${
              STATUS_STYLES[detail.status] ?? "bg-zinc-100 dark:bg-zinc-800"
            }`}
          >
            {detail.status.replaceAll("_", " ")}
          </span>
          {detail.triage && (
            <span
              className={`rounded px-2.5 py-1 text-xs font-medium ring-1 ${
                PRIORITY_STYLES[detail.triage.priority] ?? ""
              }`}
            >
              {detail.triage.priority} priority
            </span>
          )}
        </div>
      </div>

      {error && (
        <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      {detail.triage?.warnings.map((warning, index) => (
        <p
          key={index}
          className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
        >
          <strong>Warning: </strong>
          {warning.message ?? warning.type}
        </p>
      ))}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Patient-reported facts"
          subtitle="Original statements. Reviewer edits are stored separately and never overwrite these."
        >
          {detail.facts.length === 0 ? (
            <p className="text-sm text-zinc-500">Nothing recorded yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {detail.facts.map((fact) => (
                <li key={fact.id} className="flex gap-2">
                  <span className="shrink-0 rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                    {fact.kind}
                  </span>
                  <span>{fact.value}</span>
                  <span className="ml-auto shrink-0 text-xs text-zinc-400">
                    turn {fact.source_turn}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {detail.allergies_medications.length > 0 && (
            <>
              <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Allergies &amp; medications
              </h3>
              <ul className="mt-2 space-y-1 text-sm">
                {detail.allergies_medications.map((entry) => (
                  <li key={entry.id}>
                    <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs dark:bg-zinc-800">
                      {entry.kind}
                    </span>{" "}
                    {entry.name}
                    {entry.reaction_or_dose && (
                      <span className="text-zinc-500"> — {entry.reaction_or_dose}</span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          {detail.missing_fields.length > 0 && (
            <p className="mt-5 rounded bg-amber-50 p-2.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              Missing information: {detail.missing_fields.join(", ")}
            </p>
          )}
        </Panel>

        <Panel
          title="Administrative priority"
          subtitle="Decided by configured rules, not by a language model."
        >
          {!detail.triage ? (
            <p className="text-sm text-zinc-500">
              Pre-screening has not run for this case yet.
            </p>
          ) : (
            <>
              <p className="text-sm">
                Priority <strong>{detail.triage.priority}</strong> from rule
                {detail.triage.rule_codes.length > 1 ? "s" : ""}{" "}
                <code className="rounded bg-zinc-100 px-1 text-xs dark:bg-zinc-800">
                  {detail.triage.rule_codes.join(", ")}
                </code>
              </p>
              <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Evidence
              </h3>
              <ul className="mt-2 space-y-1.5 text-sm">
                {detail.triage.evidence.map((item, index) => (
                  <li key={index} className="text-zinc-700 dark:text-zinc-300">
                    <span className="text-xs text-zinc-500">
                      [{item.rule_code} · {item.matched_on}]
                    </span>{" "}
                    {item.text}
                    {item.days !== undefined && (
                      <span className="text-zinc-500">
                        {" "}
                        ({item.days} days ≥ {item.threshold_days})
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        <Panel title="Recommendation" subtitle="Advisory only — staff may override.">
          {!detail.routing ? (
            <p className="text-sm text-zinc-500">No recommendation yet.</p>
          ) : (
            <dl className="space-y-2 text-sm">
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-zinc-500">Department</dt>
                <dd>{detail.routing.specialty}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-zinc-500">Doctor</dt>
                <dd>{detail.routing.doctor_name ?? "Unassigned"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-zinc-500">Appointment</dt>
                <dd>{detail.routing.appointment_type}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-32 shrink-0 text-zinc-500">Rationale</dt>
                <dd className="text-zinc-600 dark:text-zinc-400">
                  {detail.routing.rationale}
                </dd>
              </div>
            </dl>
          )}
        </Panel>

        <Panel
          title="Medical records"
          subtitle="Stored for you to open. Images are never interpreted by the system."
        >
          {detail.attachments.length === 0 ? (
            <p className="text-sm text-zinc-500">No attachments.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {detail.attachments.map((attachment) => (
                <li key={attachment.id} className="flex items-center gap-2">
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs dark:bg-zinc-800">
                    {attachment.kind}
                  </span>
                  <a
                    href={api.attachmentUrl(detail.case_id, attachment.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="underline underline-offset-2"
                  >
                    {attachment.filename}
                  </a>
                  <span className="ml-auto text-xs text-zinc-400">
                    {attachment.has_extracted_text
                      ? "text extracted"
                      : "not interpreted"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel
        title="Clinician summary"
        subtitle="Generated from patient-reported facts. Not a diagnosis."
      >
        {!detail.prescreening_summary ? (
          <p className="text-sm text-zinc-500">Not generated yet.</p>
        ) : (
          <div className="space-y-3 text-sm">
            <p>{summarySections.context_for_clinician as string}</p>
            {(
              [
                ["Reported symptoms", "reported_symptoms"],
                ["Relevant history", "relevant_history"],
                ["Medications", "medications"],
                ["Allergies", "allergies"],
              ] as const
            ).map(([label, key]) => {
              const values = asStringList(summarySections[key]);
              if (values.length === 0) return null;
              return (
                <p key={key}>
                  <span className="text-zinc-500">{label}: </span>
                  {values.join(", ")}
                </p>
              );
            })}
            {detail.prescreening_summary.missing_information.length > 0 && (
              <p className="rounded bg-amber-50 p-2.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                Missing: {detail.prescreening_summary.missing_information.join(", ")}
              </p>
            )}
          </div>
        )}
      </Panel>

      {/* --- clinician actions ------------------------------------------- */}

      <Panel
        title="Clinician review"
        subtitle="Nothing is released to the patient until this is recorded."
      >
        {detail.review ? (
          <p className="text-sm">
            Recorded as <strong>{detail.review.decision}</strong> by{" "}
            {detail.review.reviewer_role} on{" "}
            {new Date(detail.review.created_at).toLocaleString()}.
            {Object.keys(detail.review.edits).length > 0 && (
              <span className="block mt-2 text-zinc-600 dark:text-zinc-400">
                Edits (kept separate from patient statements):{" "}
                <code className="rounded bg-zinc-100 px-1 text-xs dark:bg-zinc-800">
                  {JSON.stringify(detail.review.edits)}
                </code>
              </span>
            )}
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <input
                value={reviewerRole}
                onChange={(event) => setReviewerRole(event.target.value)}
                placeholder="reviewer role"
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              />
              <input
                value={editField}
                onChange={(event) => setEditField(event.target.value)}
                placeholder="field to correct (optional)"
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              />
              <input
                value={editValue}
                onChange={(event) => setEditValue(event.target.value)}
                placeholder="corrected value"
                className="flex-1 rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              />
            </div>
            <div className="flex gap-2">
              <button
                disabled={busy}
                onClick={() =>
                  void run(() => api.review(caseId, "approve", reviewerRole))
                }
                className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                disabled={busy || !editField.trim()}
                onClick={() =>
                  void run(() =>
                    api.review(caseId, "edit", reviewerRole, {
                      [editField.trim()]: editValue,
                    }),
                  )
                }
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
              >
                Approve with edit
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void run(() => api.review(caseId, "reject", reviewerRole))
                }
                className="rounded-md border border-red-400 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:text-red-300 dark:hover:bg-red-950"
              >
                Reject
              </button>
            </div>
          </div>
        )}
      </Panel>

      {approved && (
        <Panel
          title="Consultation notes"
          subtitle="Written by the clinician. The final summary reads these; it never rewrites them."
        >
          <ul className="mb-4 space-y-2 text-sm">
            {detail.consultation_notes.map((note) => (
              <li
                key={note.id}
                className="rounded border border-zinc-200 p-3 dark:border-zinc-800"
              >
                <p className="text-xs text-zinc-500">
                  {note.doctor_id} · {new Date(note.created_at).toLocaleString()}
                </p>
                <p className="mt-1">{note.notes}</p>
                {note.follow_up_instructions && (
                  <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                    Follow-up: {note.follow_up_instructions}
                  </p>
                )}
              </li>
            ))}
          </ul>

          <div className="space-y-2">
            <input
              value={doctorId}
              onChange={(event) => setDoctorId(event.target.value)}
              placeholder="doctor id (e.g. dr_mehta)"
              className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            />
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Consultation notes…"
              rows={3}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            />
            <input
              value={followUp}
              onChange={(event) => setFollowUp(event.target.value)}
              placeholder="Follow-up instructions (optional)"
              className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            />
            <div className="flex gap-2">
              <button
                disabled={busy || !notes.trim() || !doctorId.trim()}
                onClick={() =>
                  void run(async () => {
                    await api.addConsultationNote(caseId, {
                      doctor_id: doctorId.trim(),
                      notes: notes.trim(),
                      follow_up_instructions: followUp.trim() || null,
                    });
                    setNotes("");
                    setFollowUp("");
                  })
                }
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
              >
                Save notes
              </button>
              <button
                disabled={busy || detail.consultation_notes.length === 0}
                onClick={() => void run(() => api.finalize(caseId))}
                className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                Finalise visit summary
              </button>
            </div>
          </div>
        </Panel>
      )}

      {detail.final_summary && (
        <Panel title="Final visit summary" subtitle="Released after clinician approval.">
          <div className="space-y-2 text-sm">
            <p>
              <span className="text-zinc-500">Visit reason: </span>
              {finalSections.visit_reason as string}
            </p>
            <p>{finalSections.consultation_overview as string}</p>
            <p>
              <span className="text-zinc-500">Notes: </span>
              {finalSections.doctor_notes_summary as string}
            </p>
            {asStringList(finalSections.follow_up_instructions).length > 0 && (
              <div>
                <span className="text-zinc-500">Follow-up:</span>
                <ul className="mt-1 list-inside list-disc">
                  {asStringList(finalSections.follow_up_instructions).map(
                    (instruction, index) => (
                      <li key={index}>{instruction}</li>
                    ),
                  )}
                </ul>
              </div>
            )}
            <p className="mt-3 rounded bg-zinc-100 p-2.5 text-xs dark:bg-zinc-800">
              A draft scheduling task was created. Draft only — nothing has been
              booked.
            </p>
          </div>
        </Panel>
      )}

      <Panel title="Consent &amp; audit timeline" subtitle={`${audit.length} events`}>
        <ol className="space-y-2 text-sm">
          {audit.map((event) => (
            <li key={event.id} className="flex gap-3">
              <span className="w-40 shrink-0 text-xs text-zinc-500">
                {new Date(event.created_at).toLocaleString()}
              </span>
              <span className="w-56 shrink-0 font-medium">{event.action}</span>
              <span className="text-zinc-600 dark:text-zinc-400">
                {event.actor}
              </span>
            </li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}
