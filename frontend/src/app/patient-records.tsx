"use client";

import { useRef, useState } from "react";
import { api, type Attachment, type CaseDetail } from "@/lib/api";
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
  inputClass,
  titleCase,
} from "@/lib/ui";

/**
 * What the patient has given the clinic: past visits, the documents attached
 * to them, and the medicines and allergies they have stated.
 *
 * Everything here is the patient's own information read back to them. Nothing
 * the AI produced and nothing a clinician wrote appears on this screen — that
 * is `patient-results.tsx`, and only after review.
 */

const ATTACHMENT_KINDS = [
  ["prescription", "Prescription"],
  ["lab_report", "Lab / blood report"],
  ["radiology", "Scan or X-ray"],
  ["pathology", "Pathology report"],
  ["referral", "Referral letter"],
  ["other", "Something else"],
] as const;

/**
 * Values intake writes when there was no answer to record.
 *
 * They are real rows — the clinician sees them, and that is the point of them
 * — but showing a patient "Allergies: Answered — see the intake transcript"
 * reads as broken. Mirrors the constants in `agents/question_planner.py`.
 */
const PLACEHOLDERS = new Set([
  "None reported by patient",
  "Declined to answer",
  "Answered — see the intake transcript",
]);

/** How far a visit has got, in words a patient would use. */
function visitStage(status: string): { label: string; tone: "neutral" | "info" | "med" | "accent" | "low" | "high" } {
  switch (status) {
    case "CREATED":
    case "INGESTING":
      return { label: "Not finished", tone: "neutral" };
    case "ANALYZING":
      return { label: "Being prepared", tone: "info" };
    case "NEEDS_REVIEW":
      return { label: "With a clinician", tone: "med" };
    case "APPROVED":
      return { label: "Ready for your appointment", tone: "accent" };
    case "COMPLETED":
      return { label: "Visit complete", tone: "low" };
    case "REJECTED":
      return { label: "Closed by the clinic", tone: "high" };
    default:
      return { label: titleCase(status), tone: "neutral" };
  }
}

/** The patient's own words for why they came, if intake got that far. */
function reasonFor(visit: CaseDetail): string | null {
  const fact = visit.facts.find((f) => f.kind === "reason_for_visit");
  if (fact && !PLACEHOLDERS.has(fact.value)) return fact.value;
  const first = visit.transcript.find((turn) => turn.role === "patient");
  return first?.content ?? null;
}

export default function PatientRecords({
  visits,
  busy,
  error,
  readOnly = false,
  onRefresh,
}: {
  /** Null until the tab has been opened once. */
  visits: CaseDetail[] | null;
  busy: boolean;
  error: string | null;
  /** Preview mode — these visits are invented, so nothing may be uploaded. */
  readOnly?: boolean;
  onRefresh: () => void;
}) {
  const [kind, setKind] = useState<string>("prescription");
  const [target, setTarget] = useState<string>("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [justUploaded, setJustUploaded] = useState<Attachment | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Already newest first: the shell loads them in the order this browser
  // remembers them, which is by when the visit was started. `CaseDetail`
  // carries no created_at, so re-sorting here could only make it worse.
  const ordered = visits ?? [];
  const openVisit = ordered.find((v) => !["COMPLETED", "REJECTED"].includes(v.status));
  const uploadTo = target || openVisit?.case_id || ordered[0]?.case_id || "";

  const documents = ordered.flatMap((visit) =>
    visit.attachments.map((file) => ({ file, visit })),
  );

  /** Allergies and medicines as stated, deduplicated across visits. */
  const stated = (want: string) => {
    const seen = new Map<string, { name: string; detail: string | null }>();
    for (const visit of ordered) {
      for (const entry of visit.allergies_medications) {
        if (entry.kind !== want || PLACEHOLDERS.has(entry.name)) continue;
        if (!seen.has(entry.name.toLowerCase())) {
          seen.set(entry.name.toLowerCase(), {
            name: entry.name,
            detail: entry.reaction_or_dose,
          });
        }
      }
    }
    return [...seen.values()];
  };
  const allergies = stated("allergy");
  const medications = stated("medication");

  async function upload(file: File) {
    if (!uploadTo) return;
    if (readOnly) {
      setUploadError("Preview mode — connect the backend to upload anything.");
      return;
    }
    setUploadBusy(true);
    setUploadError(null);
    setJustUploaded(null);
    try {
      const stored = await api.uploadAttachment(uploadTo, file, kind);
      setJustUploaded(stored);
      onRefresh();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploadBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="space-y-5">
      {error && <Banner tone="error">{error}</Banner>}

      {/* --- upload ------------------------------------------------------- */}
      <Panel
        eyebrow="Add to your file"
        title="Upload a prescription or report"
        actions={
          <Button onClick={onRefresh} disabled={busy}>
            <icons.refresh className={busy ? "animate-spin text-[15px]" : "text-[15px]"} />
            {busy ? "Loading" : "Refresh"}
          </Button>
        }
      >
        {ordered.length === 0 ? (
          <Empty>
            Nothing on file yet. Start a conversation on the{" "}
            <span className="text-text">Chat</span> tab and you can attach
            documents there, or come back here afterwards.
          </Empty>
        ) : (
          <>
            <p className="text-sm leading-6 text-dim">
              Attach an old prescription, a lab report or a scan. It is stored
              for your clinician to open — nothing is read automatically, and a
              document never changes how urgent your case is judged to be.
            </p>

            <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
              <label className="block">
                <span className="eyebrow">Attach to</span>
                <select
                  value={uploadTo}
                  onChange={(event) => setTarget(event.target.value)}
                  className={`${inputClass} mt-1.5`}
                >
                  {ordered.map((visit) => (
                    <option key={visit.case_id} value={visit.case_id}>
                      {caseRef(visit.case_id)} — {visitStage(visit.status).label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="eyebrow">Document type</span>
                <select
                  value={kind}
                  onChange={(event) => setKind(event.target.value)}
                  className={`${inputClass} mt-1.5`}
                >
                  {ATTACHMENT_KINDS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <input
                ref={fileInput}
                type="file"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void upload(file);
                }}
              />
              <Button
                variant="primary"
                onClick={() => fileInput.current?.click()}
                disabled={uploadBusy || readOnly || !uploadTo}
                className="justify-center"
              >
                <icons.plus className="text-[15px]" />
                {uploadBusy ? "Uploading…" : "Choose file"}
              </Button>
            </div>

            {uploadError && (
              <div className="mt-3">
                <Banner tone="error">{uploadError}</Banner>
              </div>
            )}
            {justUploaded && (
              <div className="mt-3">
                <Banner tone="ok">
                  {justUploaded.filename} was added to your file.
                </Banner>
              </div>
            )}
          </>
        )}
      </Panel>

      {/* --- what you have told us ---------------------------------------- */}
      {(allergies.length > 0 || medications.length > 0) && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel eyebrow="As you told us" title="Allergies">
            {allergies.length === 0 ? (
              <Empty>None recorded.</Empty>
            ) : (
              <ul className="space-y-2">
                {allergies.map((entry) => (
                  <li key={entry.name} className="flex items-start gap-2.5 text-sm">
                    <icons.alert className="mt-0.5 shrink-0 text-[15px] text-high" />
                    <span>
                      <span className="text-text">{entry.name}</span>
                      {entry.detail && (
                        <span className="text-dim"> — {entry.detail}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel eyebrow="As you told us" title="Medicines">
            {medications.length === 0 ? (
              <Empty>None recorded.</Empty>
            ) : (
              <ul className="space-y-2">
                {medications.map((entry) => (
                  <li key={entry.name} className="flex items-start gap-2.5 text-sm">
                    <icons.pill className="mt-0.5 shrink-0 text-[15px] text-accent" />
                    <span>
                      <span className="text-text">{entry.name}</span>
                      {entry.detail && (
                        <span className="text-dim"> — {entry.detail}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      )}

      {/* --- documents ---------------------------------------------------- */}
      <Panel eyebrow="Your documents" title={`${documents.length} on file`}>
        {documents.length === 0 ? (
          <Empty>No documents yet.</Empty>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {documents.map(({ file, visit }) => (
              <li key={file.id}>
                <a
                  href={api.attachmentUrl(visit.case_id, file.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex gap-3 rounded border border-line bg-raised/40 p-3 transition-colors hover:border-accent/45"
                >
                  <span className="grid size-11 shrink-0 place-items-center overflow-hidden rounded border border-line bg-ink text-faint">
                    {file.mime_type.startsWith("image/") ? (
                      // eslint-disable-next-line @next/next/no-img-element -- backend file route, not an optimisable asset
                      <img
                        src={api.attachmentUrl(visit.case_id, file.id)}
                        alt=""
                        className="size-full object-cover"
                      />
                    ) : (
                      <icons.file className="text-[18px]" />
                    )}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium text-text">
                      {file.filename}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-faint">
                      {(file.size_bytes / 1024).toFixed(0)} KB ·{" "}
                      <span suppressHydrationWarning>
                        {humanTime(file.created_at)}
                      </span>
                    </span>
                    <span className="mt-1.5 flex items-center gap-1.5">
                      <Tag>{file.kind.replaceAll("_", " ")}</Tag>
                      <span className="font-mono text-[10px] text-faint">
                        {caseRef(visit.case_id)}
                      </span>
                    </span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {/* --- visits ------------------------------------------------------- */}
      <Panel eyebrow="Your visits" title={`${ordered.length} on this device`}>
        {ordered.length === 0 ? (
          <Empty>
            No visits yet. Anything you start on the Chat tab will be listed
            here.
          </Empty>
        ) : (
          <ul className="divide-y divide-line-soft">
            {ordered.map((visit) => {
              const stage = visitStage(visit.status);
              const reason = reasonFor(visit);
              return (
                <li
                  key={visit.case_id}
                  className="flex flex-wrap items-start gap-x-4 gap-y-2 py-3 first:pt-0 last:pb-0"
                >
                  <span className="font-mono text-xs text-accent">
                    {caseRef(visit.case_id)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm text-text">
                      {reason ?? (
                        <span className="text-faint">Nothing recorded yet</span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-faint">
                      {visit.attachments.length} document
                      {visit.attachments.length === 1 ? "" : "s"} ·{" "}
                      {visit.transcript.length} message
                      {visit.transcript.length === 1 ? "" : "s"}
                      {visit.routing?.specialty && (
                        <> · {visit.routing.specialty}</>
                      )}
                    </span>
                  </span>
                  <Tag tone={stage.tone}>
                    <Dot tone={stage.tone} />
                    {stage.label}
                  </Tag>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <p className="px-1 text-[11px] leading-4 text-faint">
        This list is remembered by this browser, because the demo has no
        patient login yet. Clearing your browser data will empty it — the
        visits themselves are kept by the clinic either way.
      </p>
    </div>
  );
}
