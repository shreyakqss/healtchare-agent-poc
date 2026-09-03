"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import { ApiError, casesApi, type AssistantTurn } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/feedback";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { cn } from "@/lib/utils";
import { MARKDOWN_COMPONENTS } from "@/features/intake/message-list";

/** A clinical discussion for whoever is reading this case - literature lookups included, no
 * content filtering, and it never writes anything back to the record itself. */
export function AssistantTab({ caseId, doctorContext }: { caseId: string; doctorContext: string }) {
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [text, setText] = useState("");
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
      const { reply } = await casesApi.assistantChat(caseId, message, doctorContext, turns);
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
    <Card>
      <CardHeader
        title="Clinical assistant"
        description="Discussion only - literature lookups via PubMed included. Nothing here writes to the record; open for you, at any point in the visit."
      />
      <CardBody className="space-y-4">
        <div className="max-h-[55vh] min-h-[16rem] space-y-4 overflow-y-auto rounded-md border border-line bg-sunken/40 p-4">
          {!turns.length ? (
            <EmptyState icon={<Icons.sparkles size={20} />} title="Ask about this visit" description="Differentials, dosing, interactions, or a literature question." />
          ) : (
            turns.map((t, i) => (
              <div key={i} className={cn("flex gap-3", t.role === "doctor" && "flex-row-reverse")}>
                <span className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                  t.role === "doctor" ? "bg-brand-soft text-brand" : "bg-surface text-fg-muted",
                )} aria-hidden="true">
                  {t.role === "doctor" ? <Icons.stethoscope size={15} /> : <Icons.sparkles size={15} />}
                </span>
                <div className={cn("max-w-[80%] rounded-lg px-3.5 py-2.5 text-sm leading-6", t.role === "doctor" ? "whitespace-pre-wrap bg-brand text-brand-fg" : "border border-line bg-surface")}>
                  {t.role === "doctor" ? t.content : <ReactMarkdown components={MARKDOWN_COMPONENTS}>{t.content}</ReactMarkdown>}
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
            placeholder="Ask about diagnosis, treatment, interactions, or literature…"
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
