"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ApiError,
  api,
  type CaseDetail,
  type CaseListItem,
  type ConsultationMode,
  type HospitalConfig,
} from "@/lib/api";
import { DEMO_DETAILS, DEMO_NOTICE } from "@/lib/demo";
import {
  Banner,
  Button,
  DemoBanner,
  Dot,
  Empty,
  Panel,
  PriorityTag,
  Tag,
  caseRef,
  humanTime,
  icons,
  inputClass,
  since,
  titleCase,
} from "@/lib/ui";

/**
 * The doctor's own surface: my patients, and what I have to do about them.
 *
 * This is the clinician side of the human-review gate, so unlike the patient
 * portal it shows everything — the triage priority, the rules that fired and
 * the AI pre-screening brief. Those exist for exactly this reader.
 *
 * The three actions here are the whole clinical loop, in the order the backend
 * enforces:
 *
 * 1. **Review** — approve or reject. Nothing downstream is possible first:
 *    `POST /consultation-notes` and `/finalize` both 409 without a review.
 * 2. **Record the consultation** — advice, prescription and follow-up, marked
 *    as seen in person or virtually.
 * 3. **Release** — finalise the visit, which is what puts a summary on the
 *    patient's "My results" screen.
 *
 * Cases are matched to a doctor by `doctor_name`, because that is what the
 * case list carries; `routing.doctor_id` on the loaded case is the id-based
 * truth and is what the confirmation line shows.
 */

type Bucket = "review" | "consult" | "done";

const BUCKETS: { key: Bucket; label: string; hint: string }[] = [
  { key: "review", label: "To review", hint: "Approve before anything else can happen" },
  { key: "consult", label: "To consult", hint: "Approved — record the visit" },
  { key: "done", label: "Completed", hint: "Summary released to the patient" },
];

function bucketOf(item: CaseListItem): Bucket | null {
  if (item.status === "NEEDS_REVIEW") return "review";
  if (item.status === "APPROVED") return "consult";
  if (item.status === "COMPLETED") return "done";
  return null;
}

export default function DoctorView({
  initialCases,
  doctors,
  departments,
  demo,
}: {
  initialCases: CaseListItem[];
  doctors: HospitalConfig["doctors"];
  departments: HospitalConfig["departments"];
  /** True when the backend was unreachable and these are preview patients. */
  demo: boolean;
}) {
  const [cases, setCases] = useState(initialCases);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);

  /** Who is using this screen. No auth in the POC — this is the whole login. */
  const [doctorId, setDoctorId] = useState<string>("");
  const [bucket, setBucket] = useState<Bucket>("review");

  /** The case being worked on, loaded in full when it is opened. */
  const [open, setOpen] = useState<CaseDetail | null>(null);
  const [openBusy, setOpenBusy] = useState(false);

  const me = doctors.find((d) => d.id === doctorId) ?? null;
  const department = departments.find((d) => d.id === me?.department_id) ?? null;

  const mine = me
    ? cases.filter((item) => item.doctor_name === me.name)
    : [];
  const inBucket = (key: Bucket) => mine.filter((item) => bucketOf(item) === key);
  const visible = inBucket(bucket);

  async function refresh() {
    if (demo) return;
    setBusy(true);
    try {
      setCases(await api.listCases());
      setNow(Date.now());
      setError(null);
      if (open) {
        setOpen(await api.getCase(open.case_id));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function openCase(caseId: string) {
    // Preview cases exist only in the browser, so there is nothing to fetch.
    if (demo) {
      setOpen(DEMO_DETAILS[caseId] ?? null);
      return;
    }
    setOpenBusy(true);
    setError(null);
    try {
      setOpen(await api.getCase(caseId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setOpenBusy(false);
    }
  }

  /* --- who are you? ------------------------------------------------------ */

  if (!me) {
    return (
      <div className="mx-auto mt-6 max-w-xl space-y-4">
        {demo && <DemoBanner>{DEMO_NOTICE}</DemoBanner>}
        <Panel eyebrow="Clinician" title="Who is seeing patients?">
          {error && (
            <div className="mb-4">
              <Banner tone="error">{error}</Banner>
            </div>
          )}
          {doctors.length === 0 ? (
            <Empty>
              No doctors are configured. Add one under{" "}
              <Link href="/hospital" className="text-accent underline underline-offset-2">
                Configuration
              </Link>
              .
            </Empty>
          ) : (
            <>
              <p className="text-sm leading-6 text-dim">
                Pick your name to see the patients routed to you. This demo has
                no sign-in — choosing here is the whole of it, and every action
                you take is recorded against the name you pick.
              </p>
              <ul className="mt-4 space-y-1.5">
                {doctors.map((doctor) => {
                  const dept = departments.find((d) => d.id === doctor.department_id);
                  const load = cases.filter(
                    (c) => c.doctor_name === doctor.name && bucketOf(c) !== "done",
                  ).length;
                  return (
                    <li key={doctor.id}>
                      <button
                        onClick={() => setDoctorId(doctor.id)}
                        className="flex w-full items-center gap-3 rounded border border-line px-4 py-3 text-left transition-colors hover:border-accent/50 hover:bg-accent/6"
                      >
                        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent/12 text-accent ring-1 ring-accent/25">
                          <icons.stethoscope className="text-[17px]" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-text">
                            {doctor.name}
                          </span>
                          <span className="block truncate text-[11px] text-faint">
                            {dept?.name ?? doctor.department_id}
                          </span>
                        </span>
                        {load > 0 && (
                          <Tag tone="med">{load} open</Tag>
                        )}
                        <icons.chevron className="shrink-0 text-[15px] text-faint" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </Panel>
      </div>
    );
  }

  /* --- worklist ---------------------------------------------------------- */

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
      {/* --- left: who I am and my list --------------------------------- */}
      <div className="space-y-4 xl:sticky xl:top-20">
        <div className="rounded-md border border-line bg-surface/80 p-4">
          <div className="flex items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent/12 text-accent ring-1 ring-accent/30">
              <icons.stethoscope className="text-[17px]" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-text">{me.name}</p>
              <p className="truncate text-[11px] text-faint">
                {department?.name ?? me.department_id}
              </p>
            </div>
            <button
              onClick={() => {
                setDoctorId("");
                setOpen(null);
              }}
              className="text-[11px] text-faint underline underline-offset-2 hover:text-dim"
            >
              change
            </button>
          </div>
        </div>

        <nav className="rounded-md border border-line bg-surface/80 p-1.5">
          <ul className="space-y-0.5">
            {BUCKETS.map(({ key, label, hint }) => {
              const active = bucket === key;
              const value = inBucket(key).length;
              return (
                <li key={key}>
                  <button
                    onClick={() => setBucket(key)}
                    aria-current={active ? "page" : undefined}
                    className={`flex w-full items-center gap-3 rounded px-3 py-2.5 text-left transition-colors ${
                      active
                        ? "bg-accent/10 text-text"
                        : "text-dim hover:bg-raised/60 hover:text-text"
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{label}</span>
                      <span className="block truncate text-[11px] text-faint">{hint}</span>
                    </span>
                    {value > 0 && (
                      <span
                        className={`nums rounded px-1.5 py-0.5 text-[10px] ${
                          key === "review" ? "bg-med/15 text-med" : "bg-raised text-dim"
                        }`}
                      >
                        {value}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <Panel
          eyebrow="My patients"
          title={`${visible.length} ${BUCKETS.find((b) => b.key === bucket)?.label.toLowerCase()}`}
          bodyClassName=""
          actions={
            <Button onClick={() => void refresh()} disabled={busy}>
              <icons.refresh
                className={busy ? "animate-spin text-[15px]" : "text-[15px]"}
              />
              {busy ? "…" : "Refresh"}
            </Button>
          }
        >
          {visible.length === 0 ? (
            <div className="p-5">
              <Empty>
                {mine.length === 0
                  ? "No patients are routed to you yet."
                  : "Nothing in this list."}
              </Empty>
            </div>
          ) : (
            <ul className="divide-y divide-line-soft">
              {visible.map((item) => {
                const selected = open?.case_id === item.case_id;
                const patient =
                  (item.demographics as Record<string, unknown>).name ??
                  "Patient";
                return (
                  <li key={item.case_id}>
                    <button
                      onClick={() => void openCase(item.case_id)}
                      className={`flex w-full items-start gap-3 px-4 py-3 text-left transition-colors ${
                        selected ? "bg-accent/8" : "hover:bg-raised/50"
                      }`}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-sm text-text">
                            {String(patient)}
                          </span>
                          <PriorityTag priority={item.priority} />
                        </span>
                        <span className="mt-0.5 block truncate text-[11px] text-dim">
                          {item.chief_complaint ?? "No reason recorded"}
                        </span>
                        <span
                          className="mt-0.5 block font-mono text-[10px] text-faint"
                          suppressHydrationWarning
                        >
                          {caseRef(item.case_id)} · {since(item.created_at, now)}
                        </span>
                      </span>
                      <icons.chevron className="mt-1 shrink-0 text-[14px] text-faint" />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>

      {/* --- right: the case being worked on ----------------------------- */}
      <div className="min-w-0 space-y-5">
        {demo && <DemoBanner>{DEMO_NOTICE}</DemoBanner>}
        {error && <Banner tone="error">{error}</Banner>}

        {openBusy && !open && (
          <Panel>
            <Empty>Loading the case…</Empty>
          </Panel>
        )}

        {!open && !openBusy && (
          <Panel eyebrow="Consultation" title="Pick a patient">
            <Empty>
              Choose someone from your list to see what they reported and to
              record your advice.
            </Empty>
          </Panel>
        )}

        {open && (
          <CasePanel
            detail={open}
            doctorId={me.id}
            doctorName={me.name}
            demo={demo}
            onChanged={() => void refresh()}
            onError={setError}
          />
        )}
      </div>
    </div>
  );
}

/* --- the open case --------------------------------------------------------- */

function CasePanel({
  detail,
  doctorId,
  doctorName,
  demo,
  onChanged,
  onError,
}: {
  detail: CaseDetail;
  doctorId: string;
  doctorName: string;
  /** Preview mode: the form is shown, but nothing may be written. */
  demo: boolean;
  onChanged: () => void;
  onError: (message: string | null) => void;
}) {
  const [mode, setMode] = useState<ConsultationMode>("in_person");
  const [advice, setAdvice] = useState("");
  const [prescription, setPrescription] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  const reviewed =
    detail.review?.decision === "approve" || detail.review?.decision === "edit";
  const released = Boolean(detail.final_summary);
  const patient = (detail.demographics as Record<string, unknown>).name ?? "Patient";

  /**
   * Preview mode has no backend to write to. Refusing here rather than
   * letting the call fail keeps the screen honest: an approval that only
   * appeared to happen is worse than one that plainly did not.
   */
  const blocked = () => {
    if (!demo) return false;
    onError("Preview mode — connect the backend to record anything.");
    return true;
  };

  async function approve() {
    if (blocked()) return;
    setSaving(true);
    onError(null);
    try {
      await api.review(detail.case_id, "approve", `doctor:${doctorId}`);
      setSaved("Approved. You can record the consultation now.");
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function reject() {
    if (blocked()) return;
    setSaving(true);
    onError(null);
    try {
      await api.review(detail.case_id, "reject", `doctor:${doctorId}`);
      setSaved("Case rejected. Nothing further is released.");
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function record() {
    if (!advice.trim() || blocked()) return;
    setSaving(true);
    onError(null);
    try {
      await api.addConsultationNote(detail.case_id, {
        doctor_id: doctorId,
        notes: advice.trim(),
        prescription: prescription.trim() || null,
        follow_up_instructions: followUp.trim() || null,
        consultation_mode: mode,
      });
      setAdvice("");
      setPrescription("");
      setFollowUp("");
      setSaved("Consultation recorded.");
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function release() {
    if (blocked()) return;
    setSaving(true);
    onError(null);
    try {
      await api.finalize(detail.case_id);
      setSaved("Visit summary released to the patient.");
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {/* --- who they are and what they said --------------------------- */}
      <Panel
        eyebrow={`Case ${caseRef(detail.case_id)}`}
        title={String(patient)}
        actions={
          <>
            <PriorityTag priority={detail.triage?.priority} />
            <Link
              href={`/cases/${detail.case_id}`}
              className="inline-flex items-center gap-1 text-xs text-faint hover:text-accent"
            >
              Full record
              <icons.chevron className="text-[14px]" />
            </Link>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="eyebrow">Reported</p>
            <ul className="mt-1.5 space-y-1">
              {detail.facts.length === 0 ? (
                <li className="text-xs text-faint">Nothing recorded.</li>
              ) : (
                detail.facts.slice(0, 8).map((fact) => (
                  <li key={fact.id} className="text-xs text-dim">
                    <span className="text-faint">
                      {fact.kind.replaceAll("_", " ")}:{" "}
                    </span>
                    {fact.value}
                  </li>
                ))
              )}
            </ul>
          </div>
          <div>
            <p className="eyebrow">Allergies &amp; medicines</p>
            <ul className="mt-1.5 space-y-1">
              {detail.allergies_medications.length === 0 ? (
                <li className="text-xs text-faint">Nothing recorded.</li>
              ) : (
                detail.allergies_medications.map((entry) => (
                  <li key={entry.id} className="text-xs text-dim">
                    <span className="text-faint">{entry.kind}: </span>
                    {entry.name}
                    {entry.reaction_or_dose && ` — ${entry.reaction_or_dose}`}
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>

        {detail.triage && detail.triage.rule_codes.length > 0 && (
          <p className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-line-soft pt-3">
            <span className="eyebrow">Triage rules</span>
            {detail.triage.rule_codes.map((code) => (
              <Tag key={code}>{code}</Tag>
            ))}
          </p>
        )}
      </Panel>

      {saved && <Banner tone="ok">{saved}</Banner>}

      {/* --- step 1: review --------------------------------------------- */}
      {!reviewed && (
        <Panel eyebrow="Step 1" title="Review before anything else">
          <p className="text-sm leading-6 text-dim">
            The assistant has prepared this case but nothing has been released.
            Consultation notes and the patient&apos;s visit summary are both
            refused by the API until you have approved it.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              onClick={() => void approve()}
              disabled={saving || demo}
            >
              <icons.check className="text-[15px]" />
              Approve
            </Button>
            <Button
              variant="danger"
              onClick={() => void reject()}
              disabled={saving || demo}
            >
              Reject
            </Button>
            {demo && (
              <span className="text-[11px] text-med">
                Disabled in preview — no backend to record it.
              </span>
            )}
          </div>
        </Panel>
      )}

      {/* --- step 2: the consultation ------------------------------------ */}
      {reviewed && (
        <Panel eyebrow="Step 2" title="Record the consultation">
          <div className="space-y-4">
            <div>
              <p className="eyebrow">How did you see this patient?</p>
              <div className="mt-1.5 flex rounded border border-line p-0.5">
                {(
                  [
                    ["in_person", "In person", icons.users],
                    ["virtual", "Virtual", icons.speaker],
                  ] as const
                ).map(([value, label, Glyph]) => (
                  <button
                    key={value}
                    onClick={() => setMode(value)}
                    className={`flex flex-1 items-center justify-center gap-1.5 rounded px-3 py-1.5 text-xs transition-colors ${
                      mode === value
                        ? "bg-accent/12 text-accent"
                        : "text-faint hover:text-dim"
                    }`}
                  >
                    <Glyph className="text-[14px]" />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <label className="block">
              <span className="eyebrow">Advice and findings</span>
              <textarea
                value={advice}
                onChange={(event) => setAdvice(event.target.value)}
                rows={5}
                placeholder="What you found, and what you told the patient."
                className={`${inputClass} mt-1.5 resize-y py-2.5 leading-6`}
              />
            </label>

            <label className="block">
              <span className="eyebrow">Prescription</span>
              <textarea
                value={prescription}
                onChange={(event) => setPrescription(event.target.value)}
                rows={3}
                placeholder="Medicine, dose and duration. Leave blank if none."
                className={`${inputClass} mt-1.5 resize-y py-2.5 leading-6`}
              />
            </label>

            <label className="block">
              <span className="eyebrow">Follow-up</span>
              <input
                value={followUp}
                onChange={(event) => setFollowUp(event.target.value)}
                placeholder="When to come back, or what to watch for."
                className={`${inputClass} mt-1.5`}
              />
            </label>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                onClick={() => void record()}
                disabled={saving || demo || !advice.trim()}
              >
                <icons.check className="text-[15px]" />
                {saving ? "Saving…" : "Save consultation"}
              </Button>
              <span className={`text-[11px] ${demo ? "text-med" : "text-faint"}`}>
                {demo
                  ? "Preview — you can type here, but nothing is saved."
                  : `Recorded against ${doctorName}. The patient sees this only after the visit is released.`}
              </span>
            </div>
          </div>
        </Panel>
      )}

      {/* --- what has already been written ------------------------------- */}
      {detail.consultation_notes.length > 0 && (
        <Panel
          eyebrow="On record"
          title={`${detail.consultation_notes.length} consultation ${
            detail.consultation_notes.length === 1 ? "note" : "notes"
          }`}
        >
          <ul className="space-y-3">
            {detail.consultation_notes.map((note) => (
              <li
                key={note.id}
                className="rounded border border-line bg-raised/40 px-4 py-3"
              >
                <p className="flex flex-wrap items-center gap-2">
                  <Tag tone={note.consultation_mode === "virtual" ? "info" : "accent"}>
                    {note.consultation_mode === "virtual" ? "Virtual" : "In person"}
                  </Tag>
                  <span className="font-mono text-[11px] text-faint">
                    {note.doctor_id}
                  </span>
                  <span
                    className="ml-auto text-[11px] text-faint"
                    suppressHydrationWarning
                  >
                    {humanTime(note.created_at)}
                  </span>
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-text">
                  {note.notes}
                </p>
                {note.prescription && (
                  <p className="mt-2 flex gap-2 rounded border border-line-soft bg-ink/40 px-3 py-2 text-sm leading-6">
                    <icons.pill className="mt-1 shrink-0 text-[15px] text-accent" />
                    <span className="whitespace-pre-wrap text-dim">
                      {note.prescription}
                    </span>
                  </p>
                )}
                {note.follow_up_instructions && (
                  <p className="mt-2 text-xs text-dim">
                    <span className="text-faint">Follow-up: </span>
                    {note.follow_up_instructions}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {/* --- step 3: release --------------------------------------------- */}
      {reviewed && detail.consultation_notes.length > 0 && (
        <Panel eyebrow="Step 3" title="Release to the patient">
          {released ? (
            <p className="flex items-center gap-2.5 text-sm text-dim">
              <Dot tone="low" />
              Released. The patient can see the visit summary under{" "}
              <span className="text-text">My results</span>.
            </p>
          ) : (
            <>
              <p className="text-sm leading-6 text-dim">
                Writes up the visit and puts it on the patient&apos;s results
                screen, along with your notes and prescription. Any appointment
                it mentions is a draft — nothing is booked.
              </p>
              <Button
                variant="primary"
                onClick={() => void release()}
                disabled={saving || demo}
                className="mt-3"
              >
                <icons.send className="text-[15px]" />
                {saving ? "Releasing…" : "Finalise and release"}
              </Button>
            </>
          )}
        </Panel>
      )}

      <p className="px-1 text-[11px] leading-4 text-faint">
        Case status: {titleCase(detail.status.replaceAll("_", " "))}. Every
        action on this screen is written to the case audit trail.
      </p>
    </>
  );
}
