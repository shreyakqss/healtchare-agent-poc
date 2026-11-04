"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import { ApiError, casesApi, type AssistantTurn, type ProposedDiagnosis, type Summary } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/feedback";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import { MARKDOWN_COMPONENTS } from "@/features/intake/message-list";

/** A clinical discussion for whoever is reading this case - it reads the uploaded reports and the
 * AI differential, looks up literature, and never writes anything back to the record itself. */
export function AssistantPanel({ caseId, doctorContext, initialMessages, text, onTextChange, onDiagnosisAdded, className, canAddDiagnosis = true }: {
  caseId: string; doctorContext: string; initialMessages: AssistantTurn[];
  /** The composer is controlled so the differential beside it can prefill a question. */
  text: string; onTextChange: (text: string) => void;
  /** The doctor took a diagnosis from a reply into the differential. */
  onDiagnosisAdded: (summary: Summary) => void; className?: string;
  // False once the visit is closed: the differential is final, so replies offer no "Add".
  canAddDiagnosis?: boolean;
}) {
  // The chat is kept on the case server-side, so it is here again after a reload.
  const [turns, setTurns] = useState<AssistantTurn[]>(initialMessages);
  const setText = onTextChange;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement | null>(null);

  async function send() {
    const message = text.trim();
    if (!message || busy) return;
    const next: AssistantTurn[] = [...turns, { role: "doctor", content: message }];
    setTurns(next);
    setText("");
    if (ref.current) ref.current.style.height = "auto";
    setBusy(true);
    setError(null);
    try {
      const { reply } = await casesApi.assistantChat(caseId, message, doctorContext);
      setTurns([...next, { role: "assistant", content: reply }]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reach the assistant.");
    } finally {
      setBusy(false);
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  return (
    <Card className={className}>
      <CardHeader
        title="Ask the assistant"
        description="About this differential, the uploaded reports or the literature (PubMed). Saved on this case; never writes to the record."
      />
      <CardBody className="space-y-3">
        <div className="max-h-[50vh] min-h-[14rem] space-y-4 overflow-y-auto rounded-md border border-line bg-sunken/40 p-4">
          {!turns.length ? (
            <EmptyState icon={<Icons.sparkles size={20} />} title="Ask about this case" description="Type a question, or use Ask about this on a diagnosis." />
          ) : (
            turns.map((t, i) => (
              <div key={i} className={cn("flex gap-3", t.role === "doctor" && "flex-row-reverse")}>
                <span className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                  t.role === "doctor" ? "bg-brand-soft text-brand" : "bg-surface text-fg-muted",
                )} aria-hidden="true">
                  {t.role === "doctor" ? <Icons.stethoscope size={15} /> : <Icons.sparkles size={15} />}
                </span>
                <div className="max-w-[80%] min-w-0 space-y-1.5">
                  <div className={cn("rounded-lg px-3.5 py-2.5 text-sm leading-6", t.role === "doctor" ? "whitespace-pre-wrap bg-brand text-brand-fg" : "border border-line bg-surface")}>
                    {t.role === "doctor" ? t.content : <ReactMarkdown components={MARKDOWN_COMPONENTS}>{t.content}</ReactMarkdown>}
                  </div>
                  {t.role === "assistant" && canAddDiagnosis ? (
                    <AddToDiagnosis caseId={caseId} reply={t.content} onAdded={onDiagnosisAdded} />
                  ) : null}
                </div>
              </div>
            ))
          )}
          {busy ? <p className="text-xs text-fg-subtle">Thinking…</p> : null}
        </div>

        {error ? <Alert tone="danger">{error}</Alert> : null}

        <div className="flex items-end gap-2 rounded-lg border border-line bg-surface p-2 shadow-card focus-within:border-brand-ring focus-within:ring-2 focus-within:ring-brand-ring/25">
          <label htmlFor="assistant-composer" className="sr-only">Ask the assistant</label>
          <textarea
            id="assistant-composer"
            ref={ref}
            rows={1}
            value={text}
            disabled={busy}
            placeholder="Ask a question…"
            onChange={(e) => {
              setText(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
            }}
            onKeyDown={onKey}
            className="max-h-44 min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-[15px] leading-6 text-fg placeholder:text-fg-subtle focus:outline-none"
          />
          <Button type="button" onClick={() => void send()} disabled={!text.trim() || busy} loading={busy} aria-label="Send" className="h-11 w-11 shrink-0 px-0" icon={<Icons.send size={18} />} />
        </div>
      </CardBody>
    </Card>
  );
}

/** Picks the diagnoses a reply puts forward (read by the model, never free text), so advice or
 * dosing can't end up in the differential. The doctor adds each one they agree with. */
function AddToDiagnosis({ caseId, reply, onAdded }: {
  caseId: string; reply: string; onAdded: (summary: Summary) => void;
}) {
  const [proposed, setProposed] = useState<ProposedDiagnosis[] | null>(null);
  const [added, setAdded] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy("load");
    setError(null);
    try {
      setProposed(await casesApi.proposedDiagnoses(caseId, reply));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read diagnoses from this reply.");
    } finally {
      setBusy(null);
    }
  }

  async function add(d: ProposedDiagnosis) {
    setBusy(d.condition);
    setError(null);
    try {
      onAdded(await casesApi.addDiagnosis(caseId, d));
      setAdded((a) => [...a, d.condition]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add the diagnosis.");
    } finally {
      setBusy(null);
    }
  }

  if (proposed === null) {
    return (
      <div className="space-y-1">
        <button type="button" onClick={load} disabled={busy === "load"}
          className="inline-flex items-center gap-1 text-xs font-medium text-fg-muted hover:text-brand disabled:opacity-60">
          <Icons.plus size={12} /> {busy === "load" ? "Reading diagnoses…" : "Add to diagnosis"}
        </button>
        {error ? <p className="text-xs text-danger">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="space-y-1.5 rounded-md border border-line bg-surface p-2.5">
      {!proposed.length ? (
        <p className="text-xs text-fg-muted">This reply doesn&rsquo;t propose a diagnosis, so there is nothing to add. Advice like this belongs in the prescription or follow-up instructions.</p>
      ) : (
        <>
          <p className="text-xs font-medium text-fg-muted">Diagnoses in this reply</p>
          {proposed.map((d) => {
            const done = added.includes(d.condition);
            return (
              <div key={d.condition} className="flex items-center justify-between gap-2">
                <span className="min-w-0 text-sm">{d.condition} <span className="text-xs text-fg-subtle">({d.likelihood})</span></span>
                <Button size="sm" variant={done ? "ghost" : "secondary"} disabled={done} loading={busy === d.condition}
                  icon={done ? <Icons.check size={14} /> : <Icons.plus size={14} />} onClick={() => add(d)}>
                  {done ? "Added" : "Add"}
                </Button>
              </div>
            );
          })}
        </>
      )}
      {error ? <p className="text-xs text-danger">{error}</p> : null}
      <button type="button" onClick={() => setProposed(null)} className="text-xs text-fg-subtle hover:text-fg">Close</button>
    </div>
  );
}
