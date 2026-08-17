"use client";

import Link from "next/link";
import { useState } from "react";
import { buildPipeline, timeline } from "@/lib/agents";
import {
  ApiError,
  api,
  type AuditEvent,
  type CaseDetail,
} from "@/lib/api";
import {
  Banner,
  Button,
  Dot,
  Empty,
  Panel,
  PriorityTag,
  StatusTag,
  Tag,
  caseRef,
  duration,
  humanTime,
  icons,
  inputClass,
  titleCase,
} from "@/lib/ui";
import AgentRail from "./agent-rail";

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v) => typeof v === "string") : [];
}

/** Fact kinds grouped the way a clinician reads them, in that order. */
const FACT_GROUPS: [string, string[]][] = [
  ["Symptoms", ["symptom", "reason_for_visit"]],
  ["Duration & onset", ["duration", "onset"]],
  ["History", ["history"]],
  ["Contact", ["contact_preference"]],
];

export default function CaseView({
  caseId,
  initialDetail,
  initialAudit,
}: {
  caseId: string;
  initialDetail: CaseDetail;
  initialAudit: AuditEvent[];
}) {
  // Seeded from the server render — reloads happen in event handlers only.
  const [detail, setDetail] = useState(initialDetail);
  const [audit, setAudit] = useState(initialAudit);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [reviewerRole, setReviewerRole] = useState("clinician");
  const [editField, setEditField] = useState("");
  const [editValue, setEditValue] = useState("");
  const [doctorId, setDoctorId] = useState(initialDetail.routing?.doctor_id ?? "");
  const [notes, setNotes] = useState("");
  const [followUp, setFollowUp] = useState("");

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      const [caseDetail, auditTrail] = await Promise.all([
        api.getCase(caseId),
        api.audit(caseId),
      ]);
      setDetail(caseDetail);
      setAudit(auditTrail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const runs = buildPipeline(detail, audit);
  const trace = timeline(audit);
  const summary = (detail.prescreening_summary?.sections ?? {}) as Record<string, unknown>;
  const finalSections = (detail.final_summary?.sections ?? {}) as Record<string, unknown>;
  const approved =
    detail.review?.decision === "approve" || detail.review?.decision === "edit";
  const demographics = detail.demographics as Record<string, unknown>;

  return (
    <div className="space-y-5">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1.5 text-xs text-faint hover:text-dim"
      >
        <icons.chevron className="rotate-180 text-[14px]" />
        Patient queue
      </Link>

      {/* --- case header --------------------------------------------------- */}
      <div className="rounded-md border border-line bg-gradient-to-r from-surface to-surface/40">
        <div className="flex flex-wrap items-start gap-x-8 gap-y-4 px-6 py-5">
          <div className="min-w-[16rem]">
            <p className="font-mono text-xs text-accent">{caseRef(detail.case_id)}</p>
            <h1 className="mt-1 text-xl font-semibold tracking-tight">
              {(summary.chief_complaint as string) ??
                detail.facts.find((f) => f.kind === "reason_for_visit")?.value ??
                "Patient case"}
            </h1>
            <p className="mt-1 font-mono text-[11px] text-faint">{detail.case_id}</p>
          </div>

          {(
            [
              [
                "Patient",
                // What intake collected, else the label the case was created
                // with.
                (demographics.name as string) ??
                  (demographics.fixture_id as string) ??
                  "Synthetic patient",
                [demographics.age && `${demographics.age}`, demographics.sex]
                  .filter(Boolean)
                  .join(" · "),
              ],
              [
                "Department",
                detail.routing?.specialty ?? "Not routed",
                detail.routing?.appointment_type ?? "",
              ],
              [
                "Doctor",
                detail.routing?.doctor_name ?? "Unassigned",
                detail.routing?.doctor_id ?? "",
              ],
            ] as const
          ).map(([label, value, hint]) => (
            <div key={label}>
              <p className="eyebrow">{label}</p>
              <p className="mt-1 text-sm font-medium">{value}</p>
              {hint && <p className="text-[11px] text-faint">{hint}</p>}
            </div>
          ))}

          <div className="ml-auto flex items-center gap-2">
            <PriorityTag priority={detail.triage?.priority} />
            <StatusTag status={detail.status} />
          </div>
        </div>

        {/* stage strip */}
        <div className="flex flex-wrap items-center gap-x-1 gap-y-2 border-t border-line-soft px-6 py-3">
          {runs.map((step, index) => (
            <span key={step.key} className="flex items-center gap-1">
              <span
                className={`flex items-center gap-1.5 rounded px-2 py-1 text-[11px] ${
                  step.status === "completed"
                    ? "text-low"
                    : step.status === "running"
                      ? "bg-info/10 text-info"
                      : step.status === "waiting"
                        ? "bg-med/10 text-med"
                        : step.status === "failed"
                          ? "bg-high/10 text-high"
                          : "text-faint"
                }`}
              >
                {step.status === "completed" ? (
                  <icons.check className="text-[12px]" />
                ) : (
                  <Dot
                    tone={
                      step.status === "running"
                        ? "info"
                        : step.status === "waiting"
                          ? "med"
                          : step.status === "failed"
                            ? "high"
                            : "neutral"
                    }
                    live={step.status === "running"}
                  />
                )}
                {step.name}
              </span>
              {index < runs.length - 1 && (
                <icons.chevron className="text-[12px] text-line" />
              )}
            </span>
          ))}
        </div>
      </div>

      {error && <Banner tone="error">{error}</Banner>}

      {detail.triage?.warnings.map((warning, index) => (
        <Banner key={index} tone="warn">
          <span className="font-medium">{titleCase(warning.type ?? "warning")}: </span>
          {warning.message ?? "Flagged for clinician attention."}
        </Banner>
      ))}

      <div className="grid items-start gap-5 xl:grid-cols-[19rem_minmax(0,1fr)_23rem]">
        {/* --- column 1: the patient record ------------------------------- */}
        <div className="space-y-5">
          <Panel eyebrow="Profile" title="Patient">
            <dl className="space-y-2 text-sm">
              {Object.entries(demographics).map(([key, value]) => (
                <div key={key} className="flex gap-3">
                  <dt className="w-24 shrink-0 text-xs text-faint">{titleCase(key)}</dt>
                  <dd className="text-dim">{String(value)}</dd>
                </div>
              ))}
              <div className="flex gap-3">
                <dt className="w-24 shrink-0 text-xs text-faint">Consent</dt>
                <dd>
                  <Tag tone={detail.consent_status === "granted" ? "low" : "high"}>
                    {detail.consent_status}
                  </Tag>
                </dd>
              </div>
            </dl>
          </Panel>

          <Panel
            eyebrow="Patient-reported"
            title="Facts"
            actions={<span className="text-[11px] text-faint">{detail.facts.length}</span>}
          >
            {detail.facts.length === 0 ? (
              <Empty>Nothing recorded yet.</Empty>
            ) : (
              <div className="space-y-4">
                {FACT_GROUPS.map(([label, kinds]) => {
                  const facts = detail.facts.filter((f) => kinds.includes(f.kind));
                  if (facts.length === 0) return null;
                  return (
                    <div key={label}>
                      <p className="eyebrow mb-1.5">{label}</p>
                      <ul className="space-y-1.5">
                        {facts.map((fact) => (
                          <li key={fact.id} className="flex gap-2 text-sm">
                            <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent/70" />
                            <span className="text-dim">{fact.value}</span>
                            <span className="ml-auto shrink-0 font-mono text-[10px] text-faint">
                              t{fact.source_turn}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
              </div>
            )}
            <p className="mt-4 border-t border-line-soft pt-2.5 text-[11px] leading-4 text-faint">
              Original patient statements. Clinician corrections are stored
              separately and never overwrite these.
            </p>
          </Panel>

          <Panel eyebrow="Clinical" title="Allergies & medications">
            {detail.allergies_medications.length === 0 ? (
              <Empty>None recorded.</Empty>
            ) : (
              <ul className="space-y-2">
                {detail.allergies_medications.map((entry) => (
                  <li key={entry.id} className="flex items-start gap-2.5 text-sm">
                    <span
                      className={`mt-0.5 shrink-0 ${
                        entry.kind === "allergy" ? "text-high" : "text-info"
                      }`}
                    >
                      {entry.kind === "allergy" ? <icons.alert /> : <icons.pill />}
                    </span>
                    <span>
                      <span className="text-text">{entry.name}</span>
                      {entry.reaction_or_dose && (
                        <span className="block text-xs text-faint">
                          {entry.reaction_or_dose}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel eyebrow="Uploads" title="Medical records">
            {detail.attachments.length === 0 ? (
              <Empty>No attachments.</Empty>
            ) : (
              <ul className="space-y-2">
                {detail.attachments.map((file) => (
                  <li key={file.id}>
                    <a
                      href={api.attachmentUrl(detail.case_id, file.id)}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-3 rounded border border-line bg-raised/40 p-2.5 transition-colors hover:border-faint"
                    >
                      <span className="text-faint">
                        {file.mime_type.startsWith("image/") ? (
                          <icons.image className="text-[18px]" />
                        ) : (
                          <icons.file className="text-[18px]" />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-medium text-text">
                          {file.filename}
                        </span>
                        <span className="block text-[10px] text-faint">
                          {file.kind.replaceAll("_", " ")} ·{" "}
                          {(file.size_bytes / 1024).toFixed(0)} KB ·{" "}
                          {file.has_extracted_text ? "text extracted" : "stored only"}
                        </span>
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 border-t border-line-soft pt-2.5 text-[11px] leading-4 text-faint">
              Attachment content is never passed to the triage engine — an upload
              cannot change a priority.
            </p>
          </Panel>
        </div>

        {/* --- column 2: the AI output and the clinician's actions -------- */}
        <div className="space-y-5">
          <Panel
            eyebrow="Rule engine"
            title="AI pre-screening"
            actions={<PriorityTag priority={detail.triage?.priority} />}
          >
            {!detail.triage ? (
              <Empty>Pre-screening has not run for this case yet.</Empty>
            ) : (
              <div className="grid gap-5 md:grid-cols-2">
                <div>
                  <p className="eyebrow mb-2">Key facts</p>
                  <ul className="space-y-1.5 text-sm">
                    {(asStringList(summary.reported_symptoms).length
                      ? asStringList(summary.reported_symptoms)
                      : detail.facts.filter((f) => f.kind === "symptom").map((f) => f.value)
                    ).map((item, index) => (
                      <li key={index} className="flex gap-2">
                        <icons.heart className="mt-0.5 shrink-0 text-[13px] text-high" />
                        <span className="text-dim">{item}</span>
                      </li>
                    ))}
                    {asStringList(summary.relevant_history).map((item, index) => (
                      <li key={`h${index}`} className="flex gap-2">
                        <icons.clock className="mt-0.5 shrink-0 text-[13px] text-faint" />
                        <span className="text-dim">{item}</span>
                      </li>
                    ))}
                  </ul>

                  {(detail.prescreening_summary?.missing_information.length ?? 0) > 0 && (
                    <>
                      <p className="eyebrow mb-1.5 mt-4">Missing</p>
                      <ul className="space-y-1">
                        {detail.prescreening_summary!.missing_information.map((item) => (
                          <li key={item} className="flex gap-2 text-sm text-med">
                            <icons.alert className="mt-0.5 shrink-0 text-[13px]" />
                            {titleCase(item)}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>

                <div>
                  <p className="eyebrow mb-2">Evidence</p>
                  <ul className="space-y-2">
                    {detail.triage.evidence.map((item, index) => (
                      <li
                        key={index}
                        className="rounded border border-line bg-ink/50 px-3 py-2"
                      >
                        <p className="flex items-center gap-2">
                          <span className="font-mono text-[11px] text-accent">
                            {item.rule_code}
                          </span>
                          <span className="text-[10px] text-faint">
                            matched on {item.matched_on}
                          </span>
                        </p>
                        <p className="mt-1 text-xs text-dim">
                          {item.text ?? item.keyword}
                          {item.days !== undefined && (
                            <span className="text-faint">
                              {" "}
                              ({item.days} days ≥ {item.threshold_days})
                            </span>
                          )}
                        </p>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 flex gap-1.5 text-[11px] leading-4 text-faint">
                    <icons.shield className="mt-px shrink-0 text-[13px] text-accent" />
                    Priority came from rules{" "}
                    <span className="font-mono text-accent">
                      {detail.triage.rule_codes.join(", ")}
                    </span>
                    , not from a language model.
                  </p>
                </div>
              </div>
            )}
          </Panel>

          <Panel eyebrow="Advisory" title="Care recommendation">
            {!detail.routing ? (
              <Empty>No recommendation yet.</Empty>
            ) : (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  {(
                    [
                      ["Department", detail.routing.specialty, icons.route],
                      [
                        "Doctor",
                        detail.routing.doctor_name ?? "Unassigned",
                        icons.stethoscope,
                      ],
                      ["Appointment", detail.routing.appointment_type, icons.clock],
                    ] as const
                  ).map(([label, value, Glyph]) => (
                    <div
                      key={label}
                      className="rounded border border-line bg-raised/40 px-3 py-2.5"
                    >
                      <p className="eyebrow flex items-center gap-1.5">
                        <Glyph className="text-[13px]" />
                        {label}
                      </p>
                      <p className="mt-1 text-sm font-medium">{value}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs leading-5 text-dim">
                  {detail.routing.rationale}
                </p>
              </>
            )}
          </Panel>

          <Panel eyebrow="Generated" title="Clinician brief">
            {!detail.prescreening_summary ? (
              <Empty>Not generated yet.</Empty>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="leading-6 text-dim">
                  {summary.context_for_clinician as string}
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(
                    [
                      ["Reported symptoms", "reported_symptoms"],
                      ["Relevant history", "relevant_history"],
                      ["Medications", "medications"],
                      ["Allergies", "allergies"],
                    ] as const
                  ).map(([label, key]) => {
                    const values = asStringList(summary[key]);
                    if (values.length === 0) return null;
                    return (
                      <div key={key}>
                        <p className="eyebrow mb-1">{label}</p>
                        <div className="flex flex-wrap gap-1">
                          {values.map((value, index) => (
                            <Tag key={index}>{value}</Tag>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="border-t border-line-soft pt-2.5 text-[11px] text-faint">
                  Written from recorded facts only. Not a diagnosis.
                </p>
              </div>
            )}
          </Panel>

          {/* --- clinician gate ------------------------------------------ */}
          <Panel
            eyebrow="Human in the loop"
            title="Clinician review"
            actions={
              detail.review ? (
                <Tag tone={detail.review.decision === "reject" ? "high" : "low"}>
                  {detail.review.decision}
                </Tag>
              ) : (
                <Tag tone="med">
                  <Dot tone="med" live />
                  awaiting decision
                </Tag>
              )
            }
          >
            {detail.review ? (
              <div className="text-sm text-dim">
                Recorded as <span className="text-text">{detail.review.decision}</span> by{" "}
                {detail.review.reviewer_role} at{" "}
                <span suppressHydrationWarning>
                  {new Date(detail.review.created_at).toLocaleString()}
                </span>
                .
                {Object.keys(detail.review.edits).length > 0 && (
                  <div className="mt-3">
                    <p className="eyebrow mb-1">Clinician corrections</p>
                    <dl className="space-y-1">
                      {Object.entries(detail.review.edits).map(([key, value]) => (
                        <div key={key} className="flex gap-2 text-xs">
                          <dt className="font-mono text-faint">{key}</dt>
                          <dd className="text-text">{String(value)}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-dim">
                  Nothing is released to the patient and no consultation can be
                  recorded until a decision exists.
                </p>
                <div className="grid gap-2 sm:grid-cols-3">
                  <input
                    value={reviewerRole}
                    onChange={(event) => setReviewerRole(event.target.value)}
                    placeholder="reviewer role"
                    className={inputClass}
                  />
                  <input
                    value={editField}
                    onChange={(event) => setEditField(event.target.value)}
                    placeholder="field to correct (optional)"
                    className={inputClass}
                  />
                  <input
                    value={editValue}
                    onChange={(event) => setEditValue(event.target.value)}
                    placeholder="corrected value"
                    className={inputClass}
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    disabled={busy}
                    onClick={() => void run(() => api.review(caseId, "approve", reviewerRole))}
                  >
                    <icons.check className="text-[15px]" />
                    Approve
                  </Button>
                  <Button
                    disabled={busy || !editField.trim()}
                    onClick={() =>
                      void run(() =>
                        api.review(caseId, "edit", reviewerRole, {
                          [editField.trim()]: editValue,
                        }),
                      )
                    }
                  >
                    Approve with correction
                  </Button>
                  <Button
                    variant="danger"
                    disabled={busy}
                    onClick={() => void run(() => api.review(caseId, "reject", reviewerRole))}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            )}
          </Panel>

          {approved && (
            <Panel eyebrow="Consultation" title="Doctor notes">
              {detail.consultation_notes.length > 0 && (
                <ul className="mb-4 space-y-2">
                  {detail.consultation_notes.map((note) => (
                    <li key={note.id} className="rounded border border-line bg-ink/50 p-3">
                      <p className="flex items-center gap-2 text-[11px] text-faint">
                        <icons.stethoscope className="text-[13px]" />
                        {note.doctor_id}
                        <Tag tone={note.consultation_mode === "virtual" ? "info" : "accent"}>
                          {note.consultation_mode === "virtual" ? "virtual" : "in person"}
                        </Tag>
                        <span suppressHydrationWarning>
                          · {new Date(note.created_at).toLocaleString()}
                        </span>
                      </p>
                      <p className="mt-1.5 text-sm leading-6 text-dim">{note.notes}</p>
                      {note.prescription && (
                        <p className="mt-1.5 flex gap-2 text-xs">
                          <icons.pill className="mt-0.5 shrink-0 text-[13px] text-accent" />
                          <span className="whitespace-pre-wrap text-dim">
                            {note.prescription}
                          </span>
                        </p>
                      )}
                      {note.follow_up_instructions && (
                        <p className="mt-1.5 text-xs text-accent">
                          Follow-up: {note.follow_up_instructions}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              <div className="space-y-2">
                <input
                  value={doctorId}
                  onChange={(event) => setDoctorId(event.target.value)}
                  placeholder="doctor id (e.g. dr_rao)"
                  className={inputClass}
                />
                <textarea
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder="Consultation notes…"
                  rows={3}
                  className={`${inputClass} resize-y`}
                />
                <input
                  value={followUp}
                  onChange={(event) => setFollowUp(event.target.value)}
                  placeholder="Follow-up instructions (optional)"
                  className={inputClass}
                />
                <div className="flex flex-wrap gap-2">
                  <Button
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
                  >
                    Save notes
                  </Button>
                  <Button
                    variant="primary"
                    disabled={busy || detail.consultation_notes.length === 0}
                    onClick={() => void run(() => api.finalize(caseId))}
                  >
                    <icons.play className="text-[13px]" />
                    Run final summary
                  </Button>
                </div>
              </div>
            </Panel>
          )}

          {detail.final_summary && (
            <Panel
              eyebrow="Released"
              title="Final visit summary"
              actions={<Tag tone="low">completed</Tag>}
            >
              <div className="space-y-3 text-sm">
                <div>
                  <p className="eyebrow mb-1">Visit reason</p>
                  <p className="text-dim">{finalSections.visit_reason as string}</p>
                </div>
                <div>
                  <p className="eyebrow mb-1">Overview</p>
                  <p className="leading-6 text-dim">
                    {finalSections.consultation_overview as string}
                  </p>
                </div>
                <div>
                  <p className="eyebrow mb-1">Doctor notes</p>
                  <p className="leading-6 text-dim">
                    {finalSections.doctor_notes_summary as string}
                  </p>
                </div>
                {asStringList(finalSections.follow_up_instructions).length > 0 && (
                  <div>
                    <p className="eyebrow mb-1">Follow-up</p>
                    <ul className="space-y-1">
                      {asStringList(finalSections.follow_up_instructions).map(
                        (instruction, index) => (
                          <li key={index} className="flex gap-2 text-dim">
                            <icons.check className="mt-1 shrink-0 text-[13px] text-accent" />
                            {instruction}
                          </li>
                        ),
                      )}
                    </ul>
                  </div>
                )}
                <p className="rounded border border-line bg-raised/50 px-3 py-2 text-[11px] text-faint">
                  A draft scheduling task was created. Draft only — nothing has been
                  booked.
                </p>
              </div>
            </Panel>
          )}
        </div>

        {/* --- column 3: how it got here ---------------------------------- */}
        <div className="space-y-5">
          <AgentRail runs={runs} />

          <Panel
            eyebrow="Observability"
            title="Execution timeline"
            actions={<span className="text-[11px] text-faint">{trace.length} events</span>}
            bodyClassName="p-4"
          >
            {trace.length === 0 ? (
              <Empty>No events recorded.</Empty>
            ) : (
              <ol className="space-y-0">
                {trace.map((entry, index) => (
                  <li key={entry.id} className="relative flex gap-3 pb-3 last:pb-0">
                    {index < trace.length - 1 && (
                      <span className="absolute left-[3.55rem] top-4 h-full w-px bg-line" />
                    )}
                    <span
                      className="nums w-14 shrink-0 pt-px font-mono text-[10px] text-faint"
                      suppressHydrationWarning
                    >
                      {humanTime(entry.at)}
                    </span>
                    <span className="z-10 mt-1 size-1.5 shrink-0 rounded-full bg-accent/60 ring-4 ring-surface" />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline gap-2">
                        <span className="text-xs font-medium text-text">
                          {entry.label}
                        </span>
                        <span className="nums ml-auto shrink-0 font-mono text-[10px] text-faint">
                          +{duration(entry.offsetMs)}
                        </span>
                      </span>
                      <span className="block truncate text-[10px] text-faint">
                        {entry.actor}
                        {entry.detail && ` · ${entry.detail}`}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
