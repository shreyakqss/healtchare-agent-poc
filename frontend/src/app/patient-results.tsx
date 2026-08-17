"use client";

import type { CaseDetail, Summary } from "@/lib/api";
import {
  Banner,
  Button,
  Dot,
  Empty,
  Panel,
  Tag,
  caseRef,
  humanTime,
  icons,
} from "@/lib/ui";

/**
 * What the clinic has said back to the patient.
 *
 * **This screen is the human-review gate made visible.** Nothing the AI wrote
 * on its own reaches it:
 *
 * - the pre-screening summary is never shown — it is written before any
 *   clinician has read the case, and it is for the clinician;
 * - the triage priority is never shown, in any form. It is an administrative
 *   routing decision, and a patient reading "HIGH" would reasonably hear a
 *   clinical verdict that nobody has given them;
 * - the department and doctor appear only once a clinician has approved the
 *   case, because before that they are a suggestion, not a plan;
 * - the visit summary appears only when it exists, and it cannot exist until
 *   the case was approved — `POST /finalize` returns 409 otherwise.
 *
 * Fields are read by name rather than iterated, so a new key added to the
 * summary on the backend cannot appear here without someone deciding it
 * should. `draft_care_task` in particular carries the priority.
 */

/** Read one string field out of a summary's sections. */
function text(summary: Summary | null, key: string): string | null {
  const value = summary?.sections?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Read one list-of-strings field out of a summary's sections. */
function list(summary: Summary | null, key: string): string[] {
  const value = summary?.sections?.[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && !!item.trim());
}

/** Whether a clinician has actually signed off on this case. */
const isReleased = (visit: CaseDetail) =>
  visit.review?.decision === "approve" || visit.review?.decision === "edit";

export default function PatientResults({
  visits,
  busy,
  error,
  onRefresh,
}: {
  /** Null until the tab has been opened once. */
  visits: CaseDetail[] | null;
  busy: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  // Already newest first — see the note in `patient-records.tsx`.
  const ordered = visits ?? [];

  return (
    <div className="space-y-5">
      {error && <Banner tone="error">{error}</Banner>}

      <Panel
        eyebrow="From your care team"
        title="Notes and visit summaries"
        actions={
          <Button onClick={onRefresh} disabled={busy}>
            <icons.refresh className={busy ? "animate-spin text-[15px]" : "text-[15px]"} />
            {busy ? "Loading" : "Refresh"}
          </Button>
        }
      >
        <p className="text-sm leading-6 text-dim">
          Only what a clinician has written or approved appears here. While a
          visit is still being prepared you will see that it is waiting —
          nothing is shown to you before a qualified person has read it.
        </p>
      </Panel>

      {ordered.length === 0 ? (
        <Panel>
          <Empty>
            Nothing yet. Once you have finished a conversation on the{" "}
            <span className="text-text">Chat</span> tab and a clinician has
            reviewed it, their notes will appear here.
          </Empty>
        </Panel>
      ) : (
        ordered.map((visit) => (
          <VisitResult key={visit.case_id} visit={visit} />
        ))
      )}
    </div>
  );
}

function VisitResult({ visit }: { visit: CaseDetail }) {
  const released = isReleased(visit);
  const notes = visit.consultation_notes;
  const summary = visit.final_summary;

  const overview = text(summary, "consultation_overview");
  const notesSummary = text(summary, "doctor_notes_summary");
  const reason = text(summary, "visit_reason");
  const followUps = list(summary, "follow_up_instructions");

  return (
    <Panel
      eyebrow={`Visit ${caseRef(visit.case_id)}`}
      title={reason ?? "Your visit"}
      actions={
        summary ? (
          <Tag tone="low">
            <Dot tone="low" />
            Complete
          </Tag>
        ) : released ? (
          <Tag tone="accent">
            <Dot tone="accent" />
            Reviewed
          </Tag>
        ) : (
          <Tag tone="med">
            <Dot tone="med" live />
            Waiting for a clinician
          </Tag>
        )
      }
    >
      {/* --- not yet reviewed ------------------------------------------- */}
      {!released && (
        <div className="flex items-start gap-3 rounded border border-med/35 bg-med/8 px-4 py-3">
          <icons.clock className="mt-0.5 shrink-0 text-[16px] text-med" />
          <p className="text-sm leading-6 text-dim">
            A clinician has not reviewed this visit yet. Nothing is shown here
            until they have — including anything the assistant prepared while
            you were talking to it.
          </p>
        </div>
      )}

      {/* --- where you are going ---------------------------------------- */}
      {released && visit.routing && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          {[
            ["Department", visit.routing.specialty, icons.building],
            ["Clinician", visit.routing.doctor_name, icons.stethoscope],
            [
              "Appointment",
              visit.routing.appointment_type?.replaceAll("_", " "),
              icons.clock,
            ],
          ].map(([label, value, Icon]) => {
            const Glyph = Icon as (typeof icons)["clock"];
            return (
              <div
                key={label as string}
                className="rounded border border-line bg-raised/40 px-3.5 py-3"
              >
                <p className="eyebrow flex items-center gap-1.5">
                  <Glyph className="text-[13px]" />
                  {label as string}
                </p>
                <p className="mt-1 text-sm text-text">
                  {(value as string) ?? (
                    <span className="text-faint">To be confirmed</span>
                  )}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* --- the doctor's own words -------------------------------------- */}
      {notes.length > 0 && (
        <div className="space-y-3">
          <p className="eyebrow">What your clinician wrote</p>
          {notes.map((note) => (
            <div
              key={note.id}
              className="rounded border border-line bg-raised/40 px-4 py-3.5"
            >
              <p className="mb-2.5 flex items-center gap-2">
                <Tag tone={note.consultation_mode === "virtual" ? "info" : "accent"}>
                  {note.consultation_mode === "virtual"
                    ? "Seen virtually"
                    : "Seen in person"}
                </Tag>
              </p>
              <p className="whitespace-pre-wrap text-sm leading-6 text-text">
                {note.notes}
              </p>

              {/* The prescription is the doctor's own text, kept in its own
                  field so it can be shown as a prescription rather than
                  buried in the paragraph above. No agent writes here. */}
              {note.prescription && (
                <div className="mt-3 rounded border border-accent/30 bg-accent/6 px-3.5 py-3">
                  <p className="eyebrow flex items-center gap-1.5 text-accent">
                    <icons.pill className="text-[13px]" />
                    Prescription
                  </p>
                  <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6 text-text">
                    {note.prescription}
                  </p>
                  <p className="mt-2 text-[11px] leading-4 text-faint">
                    Written by your clinician. Follow it as given, and contact
                    the clinic if anything is unclear.
                  </p>
                </div>
              )}

              {note.follow_up_instructions && (
                <p className="mt-3 flex gap-2.5 border-t border-line-soft pt-3 text-sm leading-6 text-dim">
                  <icons.route className="mt-1 shrink-0 text-[15px] text-accent" />
                  <span>
                    <span className="text-text">Follow up: </span>
                    {note.follow_up_instructions}
                  </span>
                </p>
              )}
              <p
                className="mt-2 text-[11px] text-faint"
                suppressHydrationWarning
              >
                {humanTime(note.created_at)}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* --- the released visit summary ---------------------------------- */}
      {summary && (
        <div className="mt-4 space-y-3">
          <p className="eyebrow">Your visit summary</p>
          {overview && (
            <p className="text-sm leading-6 text-dim">{overview}</p>
          )}
          {notesSummary && (
            <p className="text-sm leading-6 text-dim">{notesSummary}</p>
          )}
          {followUps.length > 0 && (
            <ul className="space-y-1.5">
              {followUps.map((item, index) => (
                <li key={index} className="flex gap-2.5 text-sm leading-6">
                  <icons.check className="mt-1 shrink-0 text-[14px] text-low" />
                  <span className="text-dim">{item}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="border-t border-line-soft pt-3 text-[11px] leading-4 text-faint">
            Written up after your consultation and released by your clinician.
            It is a record of the visit, not a diagnosis or a prescription. Any
            appointment mentioned still has to be confirmed by the clinic.
          </p>
        </div>
      )}

      {/* --- reviewed, but nothing written yet --------------------------- */}
      {released && notes.length === 0 && !summary && (
        <div className="flex items-start gap-3 rounded border border-line bg-raised/40 px-4 py-3">
          <icons.check className="mt-0.5 shrink-0 text-[16px] text-accent" />
          <p className="text-sm leading-6 text-dim">
            A clinician has reviewed your information and your appointment is
            being arranged. Notes will appear here after your consultation.
          </p>
        </div>
      )}
    </Panel>
  );
}
