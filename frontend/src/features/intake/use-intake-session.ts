"use client";

import { useCallback, useRef, useState } from "react";
import { ApiError, casesApi, intakeApi } from "@/lib/api";
import type { ActiveIntake, Attachment, IdentityFormRequest, PatientCase, SessionResponse } from "@/lib/api";
import { ATTACHMENT_KINDS } from "@/lib/constants";

export interface ChatMessage {
  id: number;
  role: "patient" | "assistant";
  content: string;
  streaming?: boolean;
}

export interface IntakeState {
  sessionId: string | null;
  caseId: string | null;
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
        { id: nextId++, role: "assistant", content: greeting },
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
          messages: [{ id: nextId++, role: "assistant", content: greeting }],
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return redirectToSignIn();
        const detail = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
        patch({ submittingIdentity: false, error: detail });
      }
    },
    [ensureSession, greeting, patch, state.identityComplete, state.submittingIdentity],
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

  return { state, submitIdentity, send, retry, ensureSession, refreshCase, clearError, uploadDocument, skipDocument };
}
