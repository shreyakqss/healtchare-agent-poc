"use client";

import { useState, type KeyboardEvent } from "react";
import {
  ApiError, casesApi, hospitalApi,
  type CaseDetail, type ConsultationNote, type HospitalIdentity, type ReportEdit, type ReportSection,
} from "@/lib/api";
import { Alert, Badge, Button, Card, CardBody, CardHeader, Field, Icons, Textarea, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";
import { CredentialFields, useClinicianCredentials } from "@/features/doctor/credential-fields";
import { acceptedDiagnoses } from "@/features/case/diagnosis-tab";
import type { Me } from "@/features/doctor/use-doctor";

type Sections = Record<ReportSection, string>;

/** The consultation report template (the ABDM OP consultation shape), in order. */
const TEMPLATE: Array<{ key: ReportSection; label: string; hint: string; rows: number }> = [
  { key: "history", label: "Complaint & history", hint: "Presenting complaint and relevant history", rows: 4 },
  { key: "examination", label: "Examination findings", hint: "Yours alone - the AI never writes findings", rows: 3 },
  { key: "diagnosis", label: "Diagnosis", hint: "Starts from the diagnoses you accepted on the AI Diagnosis tab", rows: 2 },
  { key: "investigations", label: "Investigations", hint: "Tests to get done, one per line", rows: 3 },
  { key: "prescription", label: "Prescription", hint: "One medicine per line: dose, frequency, route, duration", rows: 4 },
  { key: "advice", label: "Advice & follow-up", hint: "Plain language for the patient; becomes the draft follow-up task", rows: 4 },
  { key: "referral", label: "Notes for other doctors", hint: "Clinicians only, never shown to the patient", rows: 3 },
];

const HISTORY_HEADING = "Complaint and history:";
const EXAM_HEADING = "Examination:";

function emptySections(): Sections {
  return { history: "", examination: "", diagnosis: "", investigations: "", prescription: "", advice: "", referral: "" };
}

/** History and examination share the note's `notes` text under two headings. */
function composeNotes(s: Sections): string {
  return [s.history.trim() && `${HISTORY_HEADING}\n${s.history.trim()}`, s.examination.trim() && `${EXAM_HEADING}\n${s.examination.trim()}`]
    .filter(Boolean).join("\n\n");
}

function fromNote(n: ConsultationNote): Sections {
  const exam = n.notes.indexOf(EXAM_HEADING);
  const history = (exam >= 0 ? n.notes.slice(0, exam) : n.notes).replace(HISTORY_HEADING, "").trim();
  return {
    history, examination: exam >= 0 ? n.notes.slice(exam + EXAM_HEADING.length).trim() : "",
    diagnosis: n.diagnosis ?? "", investigations: n.tests_ordered ?? "", prescription: n.prescription ?? "",
    advice: n.follow_up_instructions ?? "", referral: n.referral_notes ?? "",
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
        tests_ordered: opt(sections.investigations), follow_up_instructions: opt(sections.advice),
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
          <ReportDocument patientName={c.demographics.name} doctorName={latest.doctor_name} sections={saved} hospital={hospital} />
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

  const hasBody = Boolean(sections.history.trim() || sections.examination.trim());

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
          <div className="space-y-4">
            {TEMPLATE.map((t) => {
              const ai = aiSections.includes(t.key);
              return (
                <div key={t.key}>
                  <Field htmlFor={`r-${t.key}`} hint={t.hint}
                    label={<span className="inline-flex items-center gap-2">{t.label}{ai ? <Badge tone="brand">AI draft</Badge> : null}</span>}>
                    <Textarea id={`r-${t.key}`} rows={t.rows} value={sections[t.key]} onChange={(e) => setSection(t.key, e.target.value)}
                      className={cn("min-h-0", ai && "border-brand-ring/60")} />
                  </Field>
                  {ai && t.key === "prescription" ? (
                    <p className="mt-1 text-xs font-medium text-warning">AI draft: verify every medicine, dose and duration before signing.</p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="space-y-4">
            <ReportDocument patientName={c.demographics.name} doctorName={me.name} sections={sections} hospital={hospital} />
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

const DOCUMENT_SECTIONS: Array<{ key: ReportSection; label: string }> = [
  { key: "diagnosis", label: "Diagnosis" },
  { key: "prescription", label: "Prescription" },
  { key: "investigations", label: "Tests / investigations" },
  { key: "advice", label: "Advice & follow-up" },
];

/** A live, read-only render of what the patient will see, on the clinic's own letterhead.
 * `hospital` is the facility record this app already reads for the clinic's identity (OpenEMR
 * first, YAML config as fallback - see GET /hospital/config). History, examination and notes for
 * other doctors are clinical record, not the patient's document. */
function ReportDocument({ patientName, doctorName, hospital, sections }: {
  patientName: string; doctorName: string | null; hospital: HospitalIdentity | null; sections: Sections;
}) {
  const addressLine = hospital?.address
    ? [hospital.address.line1, hospital.address.city, hospital.address.state, hospital.address.postal_code].filter(Boolean).join(", ")
    : null;
  const contactLine = hospital ? [hospital.phone, hospital.email].filter(Boolean).join(" · ") : null;
  const filled = DOCUMENT_SECTIONS.filter((s) => sections[s.key]?.trim());

  return (
    <div className="rounded-md border border-line bg-surface shadow-card">
      <div className={hospital?.has_letterhead ? "border-b border-line" : "border-b-2 border-brand px-5 py-4"}>
        {hospital?.has_letterhead ? (
          // eslint-disable-next-line @next/next/no-img-element -- the clinic's own uploaded letterhead, not a static import
          <img src={hospitalApi.letterheadUrl(hospital.id)} alt={`${hospital.name} letterhead`} className="w-full object-contain" />
        ) : hospital ? (
          <>
            <p className="text-lg font-bold text-fg">{hospital.name}</p>
            {addressLine ? <p className="mt-0.5 text-xs text-fg-muted">{addressLine}</p> : null}
            {contactLine ? <p className="text-xs text-fg-muted">{contactLine}</p> : null}
          </>
        ) : (
          <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Visit report</p>
        )}
      </div>
      <div className="max-h-[32rem] min-h-[15.5rem] space-y-4 overflow-y-auto px-5 py-4">
        <dl className="grid grid-cols-2 gap-2 text-xs text-fg-muted">
          <div><dt className="text-fg-subtle">Patient</dt><dd className="font-medium text-fg">{patientName || "Unnamed patient"}</dd></div>
          <div><dt className="text-fg-subtle">Date</dt><dd className="font-medium text-fg" suppressHydrationWarning>{new Date().toLocaleDateString()}</dd></div>
          <div className="col-span-2"><dt className="text-fg-subtle">Clinician</dt><dd className="font-medium text-fg">{doctorName ?? "–"}</dd></div>
        </dl>
        <hr className="border-line" />
        {filled.length ? filled.map((s) => (
          <div key={s.key}>
            <p className="text-xs font-medium text-fg-muted">{s.label}</p>
            <p className="mt-0.5 whitespace-pre-wrap text-[15px] leading-6 text-fg">{sections[s.key]}</p>
          </div>
        )) : <p className="text-sm italic text-fg-subtle">Nothing written yet.</p>}
      </div>
    </div>
  );
}
