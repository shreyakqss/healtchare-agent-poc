"use client";

import { useCallback, useRef, useState } from "react";
import { ApiError, casesApi, intakeApi } from "@/lib/api";
import type { ActiveIntake, Attachment, IdentityFormRequest, PatientCase, PreviousVisit, SessionResponse, VisitType } from "@/lib/api";
import { ATTACHMENT_KINDS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";

export interface ChatMessage {
  id: number;
  role: "patient" | "assistant";
  content: string;
  streaming?: boolean;
}

export interface IntakeState {
  sessionId: string | null;
  caseId: string | null;
  visitType: VisitType;
  previousVisit: PreviousVisit | null;
  startingVisit: boolean;
  identityComplete: boolean; // step 1 (name/age/gender/contact) done
  messages: ChatMessage[]; // step 2, the clinical chat
  missingFields: string[] | null; // full (identity + clinical); null until the session exists
  capturedFields: Record<string, string[]>; // current value(s) per field kind, for review/correction
  complete: boolean; // step 2 closed itself (missing_fields empty or the question backstop hit)
  submittingIdentity: boolean;
  sending: boolean;
  awaitingFirstToken: boolean;
  error: string | null;
  lastCase: PatientCase | null;
  // Documents added during this visit. Held here rather than in the panel so the chat
  // (where uploading happens) and the Documents tab (where it is listed) never disagree.
  attachments: Attachment[];
  // Documents from this account's other cases (past visits) - read-only reference.
  pastAttachments: Attachment[];
  skippedKinds: Record<string, string | null>; // kind -> reason given, if any
  uploading: boolean;
}

let nextId = 1;

/** The assistant's first line: the clinic greeting, or for a follow-up, the visit it is about. */
export function openingFor(greeting: string, previous: PreviousVisit | null): string {
  if (!previous) return greeting;
  const about = previous.diagnosis?.split("\n")[0]?.trim() || previous.complaint || "your last visit";
  const doctor = previous.doctor_name ? ` with ${previous.doctor_name}` : "";
  return `Welcome back. This is a follow-up to your visit${doctor} on ${formatDate(previous.visit_at)} for **${about}**. How have you been since then, and what would you like the doctor to know today?`;
}

// A 401 mid-conversation means the CareFlow session itself expired (not a chat/upload
// failure) - send the patient to sign in again instead of showing an inline error they
// can't act on.
function redirectToSignIn(): void {
  const returnTo = window.location.pathname + window.location.search;
  window.location.href = `/api/auth/login?return_to=${encodeURIComponent(returnTo)}`;
}

export function useIntakeSession(greeting: string, initialActive: ActiveIntake | null, initialPastAttachments: Attachment[] = []) {
  const resumedMessages: ChatMessage[] = initialActive?.identity_complete
    ? [
        { id: nextId++, role: "assistant", content: openingFor(greeting, initialActive.previous_visit) },
        ...initialActive.transcript.map((message) => ({
          id: nextId++,
          role: message.role,
          content: message.content,
        })),
      ]
    : [];
  const [state, setState] = useState<IntakeState>({
    sessionId: initialActive?.session_id ?? null,
    caseId: initialActive?.case_id ?? null,
    visitType: initialActive?.visit_type ?? "new",
    previousVisit: initialActive?.previous_visit ?? null,
    startingVisit: false,
    identityComplete: initialActive?.identity_complete ?? false,
    messages: resumedMessages,
    missingFields: initialActive?.missing_fields ?? null,
    capturedFields: initialActive?.captured_fields ?? {},
    complete: initialActive?.intake_complete ?? false,
    submittingIdentity: false,
    sending: false,
    awaitingFirstToken: false,
    error: null,
    lastCase: null,
    attachments: initialActive?.attachments ?? [],
    pastAttachments: initialActive?.past_attachments ?? initialPastAttachments,
    skippedKinds: Object.fromEntries((initialActive?.skipped_attachment_kinds ?? []).map((kind) => [kind, null])),
    uploading: false,
  });
  const sessionRef = useRef<{ sessionId: string; caseId: string; consented: boolean } | null>(
    initialActive
      ? {
          sessionId: initialActive.session_id,
          caseId: initialActive.case_id,
          consented: initialActive.consent_status === "GRANTED",
        }
      : null,
  );
  const lastSentRef = useRef<string | null>(null);

  const patch = useCallback((p: Partial<IntakeState>) => setState((s) => ({ ...s, ...p })), []);

  /** Create the session + record consent the first time the patient actually submits something. */
  const ensureSession = useCallback(async (): Promise<{ sessionId: string; caseId: string }> => {
    if (sessionRef.current) {
      if (!sessionRef.current.consented) {
        await intakeApi.consent(sessionRef.current.sessionId, true);
        sessionRef.current.consented = true;
      }
      return sessionRef.current;
    }
    const started: SessionResponse = await intakeApi.start();
    const consented = await intakeApi.consent(started.session_id, true);
    const ref = { sessionId: consented.session_id, caseId: consented.case_id, consented: true };
    sessionRef.current = ref;
    patch({
      sessionId: ref.sessionId, caseId: ref.caseId, missingFields: consented.missing_fields,
      capturedFields: consented.captured_fields, pastAttachments: consented.past_attachments,
    });
    return ref;
  }, [patch]);

  /** The patient chose a new problem or a follow-up: the session starts now. A registered
   * patient's identity is filled from their profile by the server, so they go straight to the
   * conversation; a first-time patient gets the registration form. */
  const startVisit = useCallback(
    async (visitType: VisitType, followUpOf: string | null, openingLine: string) => {
      if (sessionRef.current || state.startingVisit) return;
      patch({ startingVisit: true, error: null });
      try {
        const started = await intakeApi.start({ visit_type: visitType, follow_up_of: followUpOf });
        const consented = await intakeApi.consent(started.session_id, true);
        sessionRef.current = { sessionId: consented.session_id, caseId: consented.case_id, consented: true };
        patch({
          startingVisit: false,
          sessionId: consented.session_id, caseId: consented.case_id,
          visitType: consented.visit_type, previousVisit: consented.previous_visit,
          identityComplete: consented.identity_complete,
          missingFields: consented.missing_fields, capturedFields: consented.captured_fields,
          pastAttachments: consented.past_attachments,
          messages: consented.identity_complete ? [{ id: nextId++, role: "assistant", content: openingLine }] : [],
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return redirectToSignIn();
        const detail = err instanceof ApiError ? err.message : "Could not start your visit. Please try again.";
        patch({ startingVisit: false, error: detail });
      }
    },
    [patch, state.startingVisit],
  );

  const submitIdentity = useCallback(
    async (values: IdentityFormRequest) => {
      if (state.submittingIdentity || state.identityComplete) return;
      patch({ submittingIdentity: true, error: null });
      try {
        await ensureSession();
        const { sessionId } = sessionRef.current!;
        const result = await intakeApi.submitIdentity(sessionId, values);
        patch({
          submittingIdentity: false,
          identityComplete: true,
          missingFields: result.missing_fields,
          capturedFields: result.captured_fields,
          messages: [{ id: nextId++, role: "assistant", content: openingFor(greeting, state.previousVisit) }],
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return redirectToSignIn();
        const detail = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
        patch({ submittingIdentity: false, error: detail });
      }
    },
    [ensureSession, greeting, patch, state.identityComplete, state.previousVisit, state.submittingIdentity],
  );

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || state.sending || state.complete || !sessionRef.current) return;
      lastSentRef.current = content;

      const patientMsg: ChatMessage = { id: nextId++, role: "patient", content };
      const assistantMsg: ChatMessage = { id: nextId++, role: "assistant", content: "", streaming: true };
      setState((s) => ({ ...s, messages: [...s.messages, patientMsg, assistantMsg], sending: true, awaitingFirstToken: true, error: null }));

      try {
        const { sessionId, caseId } = sessionRef.current;
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
              capturedFields: r.captured_fields,
              messages: s.messages.map((m) => (m.id === assistantMsg.id ? { ...m, content: r.reply, streaming: false } : m)),
            }));
            if (r.intake_complete) {
              // The chat may have closed while an attachment gate is still pending - the case
              // detail (fetched here) reflects whether pre-screening actually fired.
              void casesApi.patientGet(caseId).then((detail) => patch({ lastCase: detail })).catch(() => undefined);
            }
          } else if (ev.type === "error") {
            throw new ApiError(ev.status, ev.detail);
          }
        }
        if (!finished) throw new Error("The assistant did not finish its reply.");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return redirectToSignIn();
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
    [patch, state.complete, state.sending],
  );

  /** Upload from wherever the patient is - the chat composer today. Records the file on the
   * case and drops a note in the transcript so there is visible feedback in the conversation. */
  const uploadDocument = useCallback(
    async (file: File, kind: string) => {
      patch({ uploading: true, error: null });
      try {
        const { caseId } = await ensureSession();
        const saved = await casesApi.upload(caseId, file, kind, "patient");
        const label = ATTACHMENT_KINDS.find((k) => k.id === kind)?.label ?? kind;
        setState((s) => ({
          ...s,
          uploading: false,
          attachments: [saved, ...s.attachments],
          messages: s.identityComplete
            ? [...s.messages, { id: nextId++, role: "patient", content: `Attached ${label}: ${saved.filename}` }]
            : s.messages,
        }));
        return saved;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          redirectToSignIn();
          return null;
        }
        const detail = err instanceof ApiError ? err.message : "Upload failed. Please try again.";
        patch({ uploading: false, error: detail });
        return null;
      }
    },
    [ensureSession, patch],
  );

  /** "Required, with a skip option": a logged skip satisfies the gate the same way a file does. */
  const skipDocument = useCallback(
    async (kind: string, reason?: string) => {
      patch({ uploading: true, error: null });
      try {
        const { caseId } = await ensureSession();
        await casesApi.skipAttachment(caseId, kind, reason?.trim() || undefined);
        setState((s) => ({ ...s, uploading: false, skippedKinds: { ...s.skippedKinds, [kind]: reason?.trim() || null } }));
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return redirectToSignIn();
        const detail = err instanceof ApiError ? err.message : "Could not record the skip. Please try again.";
        patch({ uploading: false, error: detail });
      }
    },
    [ensureSession, patch],
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
    const detail = await casesApi.patientGet(ref.caseId);
    patch({ lastCase: detail });
    return detail;
  }, [patch]);

  const clearError = useCallback(() => patch({ error: null }), [patch]);

  return { state, startVisit, submitIdentity, send, retry, ensureSession, refreshCase, clearError, uploadDocument, skipDocument };
}
