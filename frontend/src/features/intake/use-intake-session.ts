"use client";

import { useCallback, useRef, useState } from "react";
import { ApiError, casesApi, intakeApi } from "@/lib/api";
import type { CaseDetail, HMSPatient, SessionResponse } from "@/lib/api";
import { rememberVisit } from "@/lib/patient-history";

export interface ChatMessage {
  id: number;
  role: "patient" | "assistant";
  content: string;
  streaming?: boolean;
}

export interface IntakeState {
  sessionId: string | null;
  caseId: string | null;
  messages: ChatMessage[];
  missingFields: string[] | null; // null until the session exists
  complete: boolean;
  sending: boolean;
  awaitingFirstToken: boolean;
  error: string | null;
  linkedPatient: HMSPatient | null;
  lastCase: CaseDetail | null;
}

let nextId = 1;

export function useIntakeSession(greeting: string) {
  const [state, setState] = useState<IntakeState>(() => ({
    sessionId: null,
    caseId: null,
    messages: [{ id: nextId++, role: "assistant", content: greeting }],
    missingFields: null,
    complete: false,
    sending: false,
    awaitingFirstToken: false,
    error: null,
    linkedPatient: null,
    lastCase: null,
  }));
  const sessionRef = useRef<{ sessionId: string; caseId: string } | null>(null);
  const lastSentRef = useRef<string | null>(null);

  const patch = useCallback((p: Partial<IntakeState>) => setState((s) => ({ ...s, ...p })), []);
  const setLinkedPatient = useCallback((p: HMSPatient | null) => patch({ linkedPatient: p }), [patch]);

  /** Create the session + record consent the first time the patient actually shares something. */
  const ensureSession = useCallback(async (): Promise<{ sessionId: string; caseId: string }> => {
    if (sessionRef.current) return sessionRef.current;
    const started: SessionResponse = await intakeApi.start(state.linkedPatient ? { mrn: state.linkedPatient.mrn } : {});
    const consented = await intakeApi.consent(started.session_id, true);
    const ref = { sessionId: consented.session_id, caseId: consented.case_id };
    sessionRef.current = ref;
    rememberVisit(ref.caseId, new Date().toISOString());
    patch({ sessionId: ref.sessionId, caseId: ref.caseId, missingFields: consented.missing_fields });
    return ref;
  }, [patch, state.linkedPatient]);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || state.sending || state.complete) return;
      lastSentRef.current = content;

      const patientMsg: ChatMessage = { id: nextId++, role: "patient", content };
      const assistantMsg: ChatMessage = { id: nextId++, role: "assistant", content: "", streaming: true };
      setState((s) => ({ ...s, messages: [...s.messages, patientMsg, assistantMsg], sending: true, awaitingFirstToken: true, error: null }));

      try {
        const { sessionId } = await ensureSession();
        let streamed = "";
        let finished = false;
        for await (const ev of intakeApi.stream(sessionId, content)) {
          if (ev.type === "token") {
            streamed += ev.text;
            const snapshot = streamed;
            setState((s) => ({
              ...s,
              awaitingFirstToken: false,
              messages: s.messages.map((m) => (m.id === assistantMsg.id ? { ...m, content: snapshot } : m)),
            }));
          } else if (ev.type === "done") {
            finished = true;
            const r = ev.response;
            setState((s) => ({
              ...s,
              awaitingFirstToken: false,
              sending: false,
              complete: r.intake_complete,
              missingFields: r.missing_fields,
              messages: s.messages.map((m) => (m.id === assistantMsg.id ? { ...m, content: r.reply, streaming: false } : m)),
            }));
          } else if (ev.type === "error") {
            throw new ApiError(ev.status, ev.detail);
          }
        }
        if (!finished) throw new Error("The assistant did not finish its reply.");
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Something went wrong.";
        setState((s) => ({
          ...s,
          sending: false,
          awaitingFirstToken: false,
          error: detail,
          // Drop the assistant bubble; keep the patient's words so they can retry.
          messages: s.messages.filter((m) => m.id !== assistantMsg.id),
        }));
      }
    },
    [ensureSession, state.complete, state.sending],
  );

  const retry = useCallback(async () => {
    const last = lastSentRef.current;
    if (!last) return;
    // Remove the failed patient bubble so it is not duplicated on resend.
    setState((s) => {
      const idx = s.messages.map((m) => m.role === "patient" && m.content === last).lastIndexOf(true);
      return idx === -1 ? s : { ...s, messages: s.messages.filter((_, i) => i !== idx), error: null };
    });
    await send(last);
  }, [send]);

  const refreshCase = useCallback(async () => {
    const ref = sessionRef.current;
    if (!ref) return null;
    const detail = await casesApi.get(ref.caseId);
    patch({ lastCase: detail });
    return detail;
  }, [patch]);

  const clearError = useCallback(() => patch({ error: null }), [patch]);

  /** Demo shortcut: skip the turn-by-turn chat entirely, land straight in the completed state. */
  const quickStart = useCallback(
    async (key: string) => {
      const started = await intakeApi.quickStart(key);
      const ref = { sessionId: started.session_id, caseId: started.case_id };
      sessionRef.current = ref;
      rememberVisit(ref.caseId, new Date().toISOString());
      const detail = await casesApi.get(ref.caseId);
      const messages: ChatMessage[] = [
        { id: nextId++, role: "assistant", content: greeting },
        ...detail.transcript.map((t) => ({ id: nextId++, role: t.role, content: t.content })),
      ];
      patch({
        sessionId: ref.sessionId,
        caseId: ref.caseId,
        messages,
        missingFields: started.missing_fields,
        complete: true,
        lastCase: detail,
        linkedPatient: state.linkedPatient,
      });
    },
    [greeting, patch, state.linkedPatient],
  );

  return { state, send, retry, ensureSession, setLinkedPatient, refreshCase, clearError, quickStart };
}