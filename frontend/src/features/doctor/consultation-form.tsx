"use client";

import { useState, type KeyboardEvent } from "react";
import {
  ApiError, casesApi, hospitalApi,
  type CaseDetail, type ConsultationNote, type HospitalIdentity, type ReportEdit, type ReportSection,
} from "@/lib/api";
import { Alert, Badge, Button, Card, CardBody, CardHeader, Field, Icons, Textarea, useToast } from "@/components/ui";
import { cn, formatDate, formatDateTime, titleCase } from "@/lib/utils";
import { CredentialFields, useClinicianCredentials } from "@/features/doctor/credential-fields";
import { acceptedDiagnoses } from "@/features/case/diagnosis-tab";
import type { Me } from "@/features/doctor/use-doctor";

type Sections = Record<ReportSection, string>;

/** The OPD consultation record (SOAP / ABDM OP consultation shape), in order. `half` sections sit
 * side by side; the rest take the full width. */
const TEMPLATE: Array<{ key: ReportSection; label: string; hint: string; rows: number; half?: boolean }> = [
  { key: "complaints", label: "Presenting complaints", hint: "One per line with duration, e.g. Fever x 3 days", rows: 3 },
  { key: "history", label: "History of presenting illness", hint: "Short clinical lines, including pertinent negatives", rows: 4 },
  { key: "past_history", label: "Past history", hint: "Medical / surgical; Nil significant if none", rows: 2, half: true },
  { key: "allergies", label: "Allergies", hint: "With reaction; NKDA if none", rows: 2, half: true },
  { key: "medications", label: "Current medications", hint: "What the patient already takes", rows: 2 },
  { key: "examination", label: "Examination findings", hint: "Yours alone - the AI never writes findings", rows: 3 },
  { key: "diagnosis", label: "Diagnosis", hint: "Starts from the diagnoses you accepted on the AI Diagnosis tab", rows: 2 },
  { key: "investigations", label: "Investigations", hint: "Test names, one per line", rows: 2 },
  { key: "prescription", label: "Rx", hint: "One per line: Tab. Name strength, 1-0-1 (BD) x days, instructions", rows: 4 },
  { key: "advice", label: "Advice", hint: "Short plain-language lines for the patient", rows: 3 },
  { key: "follow_up", label: "Follow-up", hint: "When to review, and when to come back earlier", rows: 2 },
  { key: "referral", label: "Notes for other doctors", hint: "Clinicians only, never shown to the patient", rows: 2 },
];

// The clinical part of the record lives in the note's `notes` text under these headings.
const NOTE_HEADINGS: Array<[ReportSection, string]> = [
  ["complaints", "Presenting complaints:"],
  ["history", "History of presenting illness:"],
  ["past_history", "Past history:"],
  ["allergies", "Allergies:"],
  ["medications", "Current medications:"],
  ["examination", "Examination:"],
];
const LEGACY_HISTORY = "Complaint and history:";
const FOLLOW_UP_PREFIX = "Follow-up: ";

function emptySections(): Sections {
  return {
    complaints: "", history: "", past_history: "", allergies: "", medications: "", examination: "",
    diagnosis: "", investigations: "", prescription: "", advice: "", follow_up: "", referral: "",
  };
}

function composeNotes(s: Sections): string {
  return NOTE_HEADINGS.map(([key, heading]) => s[key].trim() && `${heading}\n${s[key].trim()}`).filter(Boolean).join("\n\n");
}

/** Advice and follow-up are stored together as the patient's instructions, follow-up last. */
function composeInstructions(s: Sections): string {
  return [s.advice.trim(), s.follow_up.trim() && `${FOLLOW_UP_PREFIX}${s.follow_up.trim()}`].filter(Boolean).join("\n");
}

function parseNotes(text: string): Partial<Sections> {
  const headings: Array<[ReportSection, string]> = [...NOTE_HEADINGS, ["history", LEGACY_HISTORY]];
  const found = headings
    .map(([key, heading]) => ({ key, heading, at: text.indexOf(heading) }))
    .filter((h) => h.at >= 0)
    .sort((a, b) => a.at - b.at);
  if (!found.length) return { history: text.trim() };
  return Object.fromEntries(found.map((h, i) => [
    h.key, text.slice(h.at + h.heading.length, i + 1 < found.length ? found[i + 1].at : undefined).trim(),
  ]));
}

function fromNote(n: ConsultationNote): Sections {
  const lines = (n.follow_up_instructions ?? "").split("\n");
  const followUp = lines.find((l) => l.startsWith(FOLLOW_UP_PREFIX));
  return {
    ...emptySections(), ...parseNotes(n.notes),
    diagnosis: n.diagnosis ?? "", investigations: n.tests_ordered ?? "", prescription: n.prescription ?? "",
    advice: lines.filter((l) => l !== followUp).join("\n").trim(),
    follow_up: followUp ? followUp.slice(FOLLOW_UP_PREFIX.length).trim() : "",
    referral: n.referral_notes ?? "",
  };
}

/** Where the report starts: the saved version; otherwise the AI draft written at pre-screening,
 * with Diagnosis and Investigations taken from what the doctor accepted on the AI Diagnosis tab
 * (their decision outranks the draft's provisional one). */
function startingReport(c: CaseDetail, latest: ConsultationNote | null): { sections: Sections; ai: ReportSection[] } {
  if (latest) return { sections: fromNote(latest), ai: [] };
  const draft = (c.report_draft?.sections ?? {}) as Partial<Sections>;
  const sections: Sections = { ...emptySections(), ...draft, examination: "" };
  const ai = (Object.keys(sections) as ReportSection[]).filter((k) => sections[k]?.trim());
  const accepted = acceptedDiagnoses(c.ai_diagnosis);
  if (accepted.conditions.length) {
    sections.diagnosis = accepted.conditions.join("\n");
    sections.investigations = accepted.tests.join("\n") || sections.investigations;
    // The accepted diagnoses' allergy-checked regimens; still an AI draft the doctor must verify.
    sections.prescription = accepted.medicines.join("\n") || sections.prescription;
    return { sections, ai: ai.filter((k) => k !== "diagnosis" && (k !== "investigations" || !accepted.tests.length)) };
  }
  return { sections, ai };
}

/** The consultation report: an AI first draft of the template (Heidi Health style), edited
 * section by section, with a report assistant that proposes changes the doctor applies. Editable
 * until release - every save a signed, audited new version - and final once released. */
export function ConsultationForm({ c, me, onDone, hospital }: {
  c: CaseDetail; me: Me; onDone: () => Promise<void>; hospital: HospitalIdentity | null;
}) {
  const latest = c.consultation_notes.length ? c.consultation_notes[c.consultation_notes.length - 1] : null;
  const released = c.status === "COMPLETED";
  // Signing the first report on a case awaiting review is the doctor's review (backend records it).
  const awaitingReview = c.status === "NEEDS_REVIEW";
  const [declining, setDeclining] = useState(false);
  const [declineReason, setDeclineReason] = useState("");
  const [editing, setEditing] = useState(!latest);
  const [initial] = useState(() => startingReport(c, latest));
  const [sections, setSections] = useState<Sections>(initial.sections);
  // Sections whose text is still exactly what the AI wrote - shown as "AI draft" until touched.
  const [aiSections, setAiSections] = useState<ReportSection[]>(initial.ai);
  const { credentials, setCredentials, missing: missingCredentials, clearPassword } = useClinicianCredentials(me.username ?? "");
  const [busy, setBusy] = useState<"draft" | "note" | "finalize" | "decline" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  function setSection(key: ReportSection, text: string, byAi = false) {
    setSections((s) => ({ ...s, [key]: text }));
    setAiSections((a) => (byAi ? [...new Set([...a, key])] : a.filter((k) => k !== key)));
  }

  async function draft() {
    const typed = TEMPLATE.some((t) => t.key !== "examination" && sections[t.key].trim() && !aiSections.includes(t.key));
    if (typed && !window.confirm("Replace what you've written with an AI draft? Examination findings are kept.")) return;
    setBusy("draft");
    setError(null);
    try {
      const d = await casesApi.draftReport(c.case_id);
      const keys = TEMPLATE.map((t) => t.key).filter((k) => k !== "examination");
      setSections((s) => ({ ...s, ...Object.fromEntries(keys.map((k) => [k, d[k] ?? ""])) }));
      setAiSections(keys.filter((k) => (d[k] ?? "").trim()));
      toast.push({ tone: "success", message: "AI draft ready - check every section, especially the prescription" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not draft the report.");
    } finally {
      setBusy(null);
    }
  }

  async function saveNote() {
    setBusy("note");
    setError(null);
    try {
      const opt = (v: string) => v.trim() || undefined;
      await casesApi.addNote(c.case_id, {
        doctor_username: credentials.username.trim(), doctor_password: credentials.password,
        consultation_mode: "in_person", notes: composeNotes(sections),
        diagnosis: opt(sections.diagnosis), prescription: opt(sections.prescription),
        tests_ordered: opt(sections.investigations), follow_up_instructions: opt(composeInstructions(sections)),
        referral_notes: opt(sections.referral), ai_drafted_sections: aiSections,
      });
      toast.push({ tone: "success", message: "Report saved" });
      clearPassword();
      setAiSections([]);
      setEditing(false);
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the report.");
    } finally {
      setBusy(null);
    }
  }

  /** "Can't proceed online": the reject decision the review form used to carry. The patient is
   * asked to call the clinic and the booking is released. */
  async function decline() {
    setBusy("decline");
    setError(null);
    try {
      await casesApi.review(c.case_id, {
        decision: "reject", reviewer_username: credentials.username.trim(), reviewer_password: credentials.password,
        comment: declineReason.trim() || undefined,
      });
      toast.push({ tone: "success", message: "Case declined - the patient is asked to contact the clinic" });
      clearPassword();
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not decline the case.");
    } finally {
      setBusy(null);
    }
  }

  async function finalize() {
    setBusy("finalize");
    setError(null);
    try {
      await casesApi.finalize(c.case_id, { finalizer_username: credentials.username.trim(), finalizer_password: credentials.password });
      toast.push({ tone: "success", message: "Visit summary released" });
      clearPassword();
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not release the visit summary.");
    } finally {
      setBusy(null);
    }
  }

  const credentialFields = (idPrefix: string) => (
    <CredentialFields idPrefix={idPrefix} value={credentials} onChange={setCredentials}
      signingInAs={me.username ? `${me.name} (${me.username})` : null} hint="Verified against the hospital system" />
  );

  if (latest && !editing) {
    const saved = fromNote(latest);
    return (
      <Card className="border-brand-ring/40">
        <CardHeader
          title={released ? "Consultation report (released)" : "Release visit summary"}
          description={released
            ? "Released to the patient. The report is final and can no longer be edited."
            : "The report is saved. Edit it until you release it; releasing generates the patient's summary and the draft follow-up task, and makes the report final."}
          action={released ? <Badge tone="success" dot>Final</Badge> : (
            <Button size="sm" variant="secondary" icon={<Icons.edit size={14} />} onClick={() => { setSections(saved); setEditing(true); }}>
              Edit report
            </Button>
          )}
        />
        <CardBody className="space-y-4">
          {saved.referral ? (
            <div className="rounded-md border border-line bg-sunken/60 px-3.5 py-3 text-sm">
              <p className="text-xs font-medium text-fg-muted">For other doctors (not shown to the patient)</p>
              <p className="mt-1 whitespace-pre-line">{saved.referral}</p>
            </div>
          ) : null}
          <ReportDocument c={c} doctorName={latest.doctor_name} sections={saved} hospital={hospital} full
            signedAt={latest.created_at} />
          {c.consultation_notes.length > 1 ? (
            <p className="text-xs text-fg-subtle">Version {c.consultation_notes.length}; earlier versions are kept in the record and the audit trail.</p>
          ) : null}
          {error ? <Alert tone="danger">{error}</Alert> : null}
          {!released ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              {credentialFields("finalizer")}
              <Button loading={busy === "finalize"} disabled={missingCredentials} onClick={finalize} icon={<Icons.send size={16} />}>
                Release visit summary
              </Button>
            </div>
          ) : null}
        </CardBody>
      </Card>
    );
  }

  const hasBody = Boolean(sections.complaints.trim() || sections.history.trim() || sections.examination.trim());

  return (
    <Card className="border-brand-ring/40">
      <CardHeader
        title={latest ? "Edit the consultation report" : "Consultation report"}
        description="Draft it with AI or write it yourself. Every section is yours to edit; nothing reaches the patient until you sign."
        action={
          <div className="flex flex-wrap gap-2">
            {latest ? <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setAiSections([]); }}>Cancel</Button> : null}
            <Button size="sm" variant="secondary" loading={busy === "draft"} icon={<Icons.sparkles size={14} />} onClick={draft}>
              Draft report with AI
            </Button>
          </div>
        }
      />
      <CardBody className="space-y-4">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="grid gap-4 sm:grid-cols-2">
            {TEMPLATE.map((t) => {
              const ai = aiSections.includes(t.key);
              return (
                <div key={t.key} className={t.half ? undefined : "sm:col-span-2"}>
                  <Field htmlFor={`r-${t.key}`} hint={t.hint}
                    label={<span className="inline-flex items-center gap-2">{t.label}{ai ? <Badge tone="brand">AI draft</Badge> : null}</span>}>
                    <Textarea id={`r-${t.key}`} rows={t.rows} value={sections[t.key]} onChange={(e) => setSection(t.key, e.target.value)}
                      className={cn("min-h-0", ai && "border-brand-ring/60")} />
                  </Field>
                  {t.key === "diagnosis" ? (
                    <MissingAccepted
                      conditions={acceptedDiagnoses(c.ai_diagnosis).conditions}
                      text={sections.diagnosis}
                      onAdd={(items) => setSection("diagnosis", [sections.diagnosis.trim(), ...items].filter(Boolean).join("\n"))}
                    />
                  ) : null}
                  {ai && t.key === "prescription" ? (
                    <p className="mt-1 text-xs font-medium text-warning">AI draft: verify every medicine, dose and duration before signing.</p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="space-y-4">
            <ReportDocument c={c} doctorName={me.name} sections={sections} hospital={hospital} />
            <ReportAssistant caseId={c.case_id} sections={sections} onApply={(e) => setSection(e.section, e.text, true)} />
          </div>
        </div>

        {error ? <Alert tone="danger">{error}</Alert> : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          {credentialFields("doctor")}
          <Button loading={busy === "note"} disabled={!hasBody || missingCredentials} onClick={saveNote} icon={<Icons.check size={16} />}>
            {latest ? "Save changes" : awaitingReview ? "Sign report & review case" : "Save report"}
          </Button>
        </div>
        {!hasBody ? <p className="text-xs text-fg-subtle">Write the complaint & history or examination findings to sign.</p> : null}
        {awaitingReview ? (
          <div className="border-t border-line pt-3">
            {!declining ? (
              <button type="button" onClick={() => setDeclining(true)} className="text-xs font-medium text-fg-muted hover:text-danger">
                Can&rsquo;t proceed online? Decline this case
              </button>
            ) : (
              <div className="space-y-2">
                <Field label="Reason for declining" htmlFor="decline-reason" hint="Kept in the record; the patient is only asked to call the clinic. Uses the login above.">
                  <Textarea id="decline-reason" rows={2} value={declineReason} onChange={(e) => setDeclineReason(e.target.value)} className="min-h-0" />
                </Field>
                <div className="flex gap-2">
                  <Button size="sm" variant="danger" loading={busy === "decline"} disabled={missingCredentials} onClick={decline}>Decline case</Button>
                  <Button size="sm" variant="ghost" onClick={() => setDeclining(false)}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

const SECTION_LABEL = Object.fromEntries(TEMPLATE.map((t) => [t.key, t.label])) as Record<ReportSection, string>;

type Exchange = { instruction: string; reply: string; edits: Array<ReportEdit & { state: "proposed" | "applied" | "discarded" }> };

/** "Ask Heidi"-style editing: the doctor asks for a change, the assistant proposes new text per
 * section, and nothing changes in the report until the doctor clicks Apply. */
function ReportAssistant({ caseId, sections, onApply }: {
  caseId: string; sections: Sections; onApply: (edit: ReportEdit) => void;
}) {
  const [text, setText] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    const instruction = text.trim();
    if (!instruction || busy) return;
    setBusy(true);
    setError(null);
    try {
      const p = await casesApi.reportAssistant(caseId, instruction, sections);
      setExchanges((x) => [...x, { instruction, reply: p.reply, edits: p.edits.map((e) => ({ ...e, state: "proposed" })) }]);
      setText("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reach the report assistant.");
    } finally {
      setBusy(false);
    }
  }

  function settle(i: number, j: number, state: "applied" | "discarded") {
    const edit = exchanges[i].edits[j];
    if (state === "applied") onApply(edit);
    setExchanges((x) => x.map((ex, a) => a !== i ? ex : { ...ex, edits: ex.edits.map((e, b) => (b === j ? { ...e, state } : e)) }));
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void ask();
    }
  }

  return (
    <div className="rounded-md border border-line bg-surface shadow-card">
      <div className="border-b border-line px-4 py-3">
        <p className="flex items-center gap-2 text-sm font-semibold"><Icons.sparkles size={14} /> Report assistant</p>
        <p className="mt-0.5 text-xs text-fg-muted">Ask for a change, e.g. &ldquo;make the advice simpler&rdquo;, &ldquo;use lactose-free formulations&rdquo; or &ldquo;add: temp 101F, calf tenderness&rdquo;. You apply each change yourself.</p>
      </div>
      <div className="max-h-[28rem] min-h-[10rem] space-y-4 overflow-y-auto bg-sunken/40 px-4 py-3">
        {!exchanges.length && !busy ? (
          <p className="py-6 text-center text-xs text-fg-subtle">Ask for a change and the proposed edit appears here.</p>
        ) : null}
        {exchanges.map((ex, i) => (
          <div key={i} className="space-y-3">
            <div className="flex flex-row-reverse gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand" aria-hidden="true"><Icons.stethoscope size={13} /></span>
              <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-brand px-3 py-2 text-sm text-brand-fg">{ex.instruction}</p>
            </div>
            <div className="flex gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface text-fg-muted" aria-hidden="true"><Icons.sparkles size={13} /></span>
              <div className="min-w-0 max-w-[90%] space-y-2 rounded-lg border border-line bg-surface px-3 py-2.5">
                <p className="text-sm">{ex.reply}</p>
                {ex.edits.map((e, j) => (
                  <div key={j} className={cn("rounded-md border bg-sunken/50 p-2.5", e.state === "applied" ? "border-success" : "border-line", e.state === "discarded" && "opacity-50")}>
                    <p className="text-xs font-medium">{SECTION_LABEL[e.section]} <span className="font-normal text-fg-subtle">· {e.reason}</span></p>
                    <p className="mt-1.5 whitespace-pre-wrap text-sm">{e.text}</p>
                    <div className="mt-2 flex gap-1.5">
                      {e.state === "proposed" ? (
                        <>
                          <Button size="sm" icon={<Icons.check size={14} />} onClick={() => settle(i, j, "applied")}>Apply</Button>
                          <Button size="sm" variant="ghost" onClick={() => settle(i, j, "discarded")}>Discard</Button>
                        </>
                      ) : <Badge tone={e.state === "applied" ? "success" : "neutral"}>{e.state === "applied" ? "Applied to report" : "Discarded"}</Badge>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
        {busy ? <p className="text-xs text-fg-subtle">Working on it…</p> : null}
        {error ? <Alert tone="danger">{error}</Alert> : null}
      </div>
      <div className="flex items-end gap-2 border-t border-line p-2">
        <label htmlFor="report-assistant" className="sr-only">Ask the report assistant</label>
        <textarea id="report-assistant" rows={1} value={text} disabled={busy} placeholder="Ask for a change…"
          onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
          className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none" />
        <Button type="button" onClick={() => void ask()} disabled={!text.trim() || busy} loading={busy} aria-label="Send"
          className="h-10 w-10 shrink-0 px-0" icon={<Icons.send size={16} />} />
      </div>
    </div>
  );
}

// The patient's copy: what they take away. The clinical record adds history and examination.
const PATIENT_SECTIONS: Array<{ key: ReportSection; label: string }> = [
  { key: "diagnosis", label: "Diagnosis" },
  { key: "prescription", label: "Rx" },
  { key: "investigations", label: "Investigations" },
  { key: "advice", label: "Advice" },
  { key: "follow_up", label: "Follow-up" },
];
const CLINICAL_SECTIONS: Array<{ key: ReportSection; label: string }> = [
  { key: "complaints", label: "Presenting complaints" },
  { key: "history", label: "History of presenting illness" },
  { key: "past_history", label: "Past history" },
  { key: "allergies", label: "Allergies" },
  { key: "medications", label: "Current medications" },
  { key: "examination", label: "Examination" },
];

/** The consultation record on the clinic's letterhead, laid out like a printed OPD sheet:
 * patient details, then the record section by section, then the doctor's signature block.
 * While editing it previews the patient's copy; `full` (the signed record) adds the clinical
 * sections. `hospital` is the facility record (OpenEMR first, YAML config as fallback). */
function ReportDocument({ c, doctorName, hospital, sections, full = false, signedAt }: {
  c: CaseDetail; doctorName: string | null; hospital: HospitalIdentity | null; sections: Sections;
  full?: boolean; signedAt?: string;
}) {
  const addressLine = hospital?.address
    ? [hospital.address.line1, hospital.address.city, hospital.address.state, hospital.address.postal_code].filter(Boolean).join(", ")
    : null;
  const contactLine = hospital ? [hospital.phone, hospital.email].filter(Boolean).join(" · ") : null;
  const shown = [...(full ? CLINICAL_SECTIONS : []), ...PATIENT_SECTIONS].filter((s) => sections[s.key]?.trim());
  const ageSex = [c.demographics.age && `${c.demographics.age} y`, c.demographics.sex ? titleCase(c.demographics.sex) : null].filter(Boolean).join(" / ");
  const allergies = sections.allergies.trim();

  return (
    <div className="rounded-md border border-line bg-surface text-fg shadow-card">
      <div className={hospital?.has_letterhead ? "border-b border-line" : "border-b-2 border-brand px-5 py-4"}>
        {hospital?.has_letterhead ? (
          // eslint-disable-next-line @next/next/no-img-element -- the clinic's own uploaded letterhead, not a static import
          <img src={hospitalApi.letterheadUrl(hospital.id)} alt={`${hospital.name} letterhead`} className="w-full object-contain" />
        ) : hospital ? (
          <>
            <p className="text-lg font-bold">{hospital.name}</p>
            {addressLine ? <p className="mt-0.5 text-xs text-fg-muted">{addressLine}</p> : null}
            {contactLine ? <p className="text-xs text-fg-muted">{contactLine}</p> : null}
          </>
        ) : null}
      </div>
      <div className="max-h-[40rem] min-h-[15.5rem] space-y-4 overflow-y-auto px-5 py-4">
        <p className="text-center text-xs font-semibold uppercase tracking-widest text-fg-muted">
          {full ? "OPD consultation record" : "Prescription & advice (patient copy)"}
        </p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-md border border-line px-3 py-2.5 text-xs sm:grid-cols-4">
          <Meta label="Patient" value={c.demographics.name || "–"} />
          <Meta label="Age / Sex" value={ageSex || "–"} />
          <Meta label="MRN" value={c.hms_patient_id ?? "–"} />
          <Meta label="Date" value={formatDate(signedAt ?? c.created_at)} />
          <Meta label="Doctor" value={doctorName ?? "–"} />
          <Meta label="Department" value={c.routing?.department_name ?? "–"} />
        </dl>
        {allergies && !full ? (
          <p className="rounded-md border border-danger/40 bg-danger-soft px-3 py-1.5 text-xs font-medium text-danger">Allergies: {allergies.replace(/\n/g, ", ")}</p>
        ) : null}
        {shown.length ? shown.map((s) => (
          <section key={s.key}>
            <h4 className="border-b border-line pb-0.5 text-xs font-semibold uppercase tracking-wide text-fg-muted">
              {s.key === "prescription" ? <span className="mr-1 font-serif text-base normal-case text-fg">&#8478;</span> : null}{s.label}
            </h4>
            {s.key === "prescription" ? (
              <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-sm leading-6">
                {sections.prescription.split("\n").filter((l) => l.trim()).map((l, i) => <li key={i}>{l}</li>)}
              </ol>
            ) : (
              <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6">{sections[s.key]}</p>
            )}
          </section>
        )) : <p className="text-sm italic text-fg-subtle">Nothing written yet.</p>}
        <div className="flex justify-end pt-4">
          <div className="min-w-48 border-t border-fg-subtle pt-1 text-right text-xs">
            <p className="font-semibold">{doctorName ?? "Doctor"}</p>
            <p className="text-fg-muted">{signedAt ? `Signed ${formatDateTime(signedAt)}` : "Signature on signing"}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-fg-subtle">{label}</dt>
      <dd className="truncate font-medium" suppressHydrationWarning>{value}</dd>
    </div>
  );
}

/** Diagnoses accepted on the AI Diagnosis tab that the report does not mention yet - e.g. one
 * accepted after the report was first saved. The doctor adds them; nothing is added silently. */
function MissingAccepted({ conditions, text, onAdd }: { conditions: string[]; text: string; onAdd: (items: string[]) => void }) {
  const lower = text.toLowerCase();
  const missing = conditions.filter((c) => !lower.includes(c.toLowerCase()));
  if (!missing.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
      <span className="text-fg-muted">Accepted on AI Diagnosis, not in the report:</span>
      {missing.map((m) => (
        <button key={m} type="button" onClick={() => onAdd([m])}
          className="inline-flex items-center gap-1 rounded-full border border-brand-ring bg-brand-soft px-2 py-0.5 font-medium text-brand hover:bg-brand-soft/70">
          <Icons.plus size={12} />{m}
        </button>
      ))}
      {missing.length > 1 ? (
        <button type="button" onClick={() => onAdd(missing)} className="font-medium text-brand hover:underline">Add all</button>
      ) : null}
    </div>
  );
}
