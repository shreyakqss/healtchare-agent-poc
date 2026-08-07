"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  ApiError,
  api,
  type Attachment,
  type TranscriptTurn,
} from "@/lib/api";

const ATTACHMENT_KINDS = [
  "radiology",
  "pathology",
  "lab_report",
  "prescription",
  "referral",
  "other",
];

export default function PatientIntakePage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [consented, setConsented] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [intakeComplete, setIntakeComplete] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState("other");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prescreened, setPrescreened] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  function fail(err: unknown) {
    setError(err instanceof ApiError ? err.message : String(err));
  }

  async function begin(granted: boolean) {
    setBusy(true);
    setError(null);
    try {
      const session = await api.startSession({ fixture: "walk-in demo" });
      setSessionId(session.session_id);
      setCaseId(session.case_id);
      await api.recordConsent(session.session_id, granted);
      setConsented(granted);
      if (granted) {
        setTranscript([
          {
            role: "assistant",
            content:
              "Thanks. To get started — what brings you in today?",
          },
        ]);
      }
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!sessionId || !draft.trim()) return;
    const content = draft.trim();
    setDraft("");
    setTranscript((prior) => [...prior, { role: "patient", content }]);
    setBusy(true);
    setError(null);
    try {
      const result = await api.sendMessage(sessionId, content);
      setTranscript(result.transcript);
      setMissingFields(result.missing_fields);
      setIntakeComplete(result.intake_complete);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File) {
    if (!caseId) return;
    setBusy(true);
    setError(null);
    try {
      const attachment = await api.uploadAttachment(caseId, file, kind);
      setAttachments((prior) => [...prior, attachment]);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function runPrescreening() {
    if (!caseId) return;
    setBusy(true);
    setError(null);
    try {
      await api.prescreen(caseId);
      setPrescreened(true);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  // --- consent gate --------------------------------------------------------

  if (!sessionId || !consented) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight">
          Patient intake
        </h1>
        <div className="mt-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="font-medium">Before we begin</h2>
          <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
            This assistant collects the information your care team needs before
            your appointment. It organises what you tell us and prepares a
            summary for a clinician to review.
          </p>
          <ul className="mt-4 space-y-1.5 text-sm text-zinc-600 dark:text-zinc-400">
            <li>• It does not diagnose you or recommend treatment.</li>
            <li>• A qualified clinician reviews everything before any next step.</li>
            <li>• This demonstration uses synthetic data only.</li>
          </ul>
          <p className="mt-4 text-sm font-medium">
            Do you consent to us collecting this information?
          </p>
          {error && (
            <p className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
              {error}
            </p>
          )}
          <div className="mt-5 flex gap-3">
            <button
              onClick={() => begin(true)}
              disabled={busy}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              {busy ? "Starting…" : "I consent — start intake"}
            </button>
            <button
              onClick={() => begin(false)}
              disabled={busy}
              className="rounded-md border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              I do not consent
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- intake conversation -------------------------------------------------

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
          <h1 className="font-semibold">Healthcare assistant</h1>
          <p className="text-xs text-zinc-500">Case {caseId?.slice(0, 8)}…</p>
        </div>

        <div className="max-h-[28rem] space-y-4 overflow-y-auto px-6 py-5">
          {transcript.map((turn, index) => (
            <div
              key={index}
              className={turn.role === "patient" ? "text-right" : ""}
            >
              <span
                className={`inline-block max-w-[85%] rounded-lg px-4 py-2 text-sm leading-6 ${
                  turn.role === "patient"
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "bg-zinc-100 dark:bg-zinc-800"
                }`}
              >
                {turn.content}
              </span>
            </div>
          ))}
          {busy && (
            <p className="text-sm text-zinc-400">The assistant is thinking…</p>
          )}
        </div>

        {error && (
          <p className="mx-6 mb-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            {error}
          </p>
        )}

        <div className="flex gap-2 border-t border-zinc-200 px-6 py-4 dark:border-zinc-800">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            placeholder="Type your answer…"
            disabled={busy}
            className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-950"
          />
          <button
            onClick={() => void send()}
            disabled={busy || !draft.trim()}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            Send
          </button>
        </div>
      </section>

      <aside className="space-y-6">
        <div className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="text-sm font-semibold">Still needed</h2>
          {missingFields.length === 0 ? (
            <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">
              {intakeComplete
                ? "Everything required has been collected."
                : "Nothing outstanding yet."}
            </p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
              {missingFields.map((field) => (
                <li key={field}>• {field.replaceAll("_", " ")}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="text-sm font-semibold">Medical records</h2>
          <p className="mt-1 text-xs text-zinc-500">
            Reports and images are stored for your clinician to read. They are
            not analysed automatically.
          </p>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
            className="mt-3 w-full rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          >
            {ATTACHMENT_KINDS.map((option) => (
              <option key={option} value={option}>
                {option.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <input
            ref={fileInput}
            type="file"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
            className="mt-2 w-full text-xs file:mr-3 file:rounded file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-xs dark:file:bg-zinc-800"
          />
          {attachments.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
              {attachments.map((attachment) => (
                <li key={attachment.id}>
                  {attachment.filename}
                  <span className="text-zinc-400">
                    {attachment.has_extracted_text
                      ? " — text extracted"
                      : " — stored, not interpreted"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="text-sm font-semibold">Finish intake</h2>
          <p className="mt-1 text-xs text-zinc-500">
            Your information is prepared for a clinician. No recommendation is
            shown to you before they review it.
          </p>
          <button
            onClick={() => void runPrescreening()}
            disabled={busy || prescreened}
            className="mt-3 w-full rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {prescreened ? "Submitted for review" : "Submit for clinician review"}
          </button>
          {prescreened && (
            <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-400">
              Submitted. A clinician will review your information.{" "}
              <Link href="/dashboard" className="underline">
                Open the staff view
              </Link>{" "}
              to continue the demo.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}
