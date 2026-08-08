"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  api,
  type Attachment,
  type TranscriptTurn,
  type VoiceStatus,
} from "@/lib/api";
import {
  MicrophoneError,
  record,
  speechQueue,
  type Recording,
  type SpeechQueue,
} from "@/lib/audio";
import {
  Banner,
  Button,
  Dot,
  Panel,
  Tag,
  caseRef,
  icons,
  inputClass,
} from "@/lib/ui";
import VoiceConsole, { type VoicePhase } from "./voice-console";

/**
 * The patient-facing surface. Deliberately says nothing about agents, rules,
 * priorities or model behaviour — the clinician sees that, the patient sees a
 * calm assistant and their own progress.
 *
 * The shell is viewport-height with only the conversation scrolling, so the
 * composer and the progress rail stay put however long the intake runs.
 */

const ATTACHMENT_KINDS = [
  ["lab_report", "Lab / blood report"],
  ["radiology", "Scan or X-ray"],
  ["pathology", "Pathology report"],
  ["prescription", "Prescription"],
  ["referral", "Referral letter"],
  ["other", "Something else"],
] as const;

/** Intake steps, each satisfied by the backend's required-field keys. */
const STEPS = [
  { label: "Consent", fields: [] as string[] },
  { label: "Reason for visit", fields: ["reason_for_visit"] },
  { label: "Symptoms", fields: ["symptom", "duration"] },
  { label: "Medical history", fields: ["history"] },
  { label: "Medications & allergies", fields: ["medication", "allergy"] },
  { label: "Contact preference", fields: ["contact_preference"] },
  { label: "Documents", fields: [], optional: true },
  { label: "Review", fields: [] },
];

/** An upload, pinned to the point in the conversation where it happened. */
type PostedFile = { file: Attachment; afterTurn: number };

/**
 * Where a turn is. `thinking` is the wait before the first token — extraction
 * and planning — and `streaming` is the reply arriving. They are separate so
 * the patient can tell "still working" from "writing now", which is the whole
 * reason for streaming in the first place.
 */
type TurnState = "idle" | "thinking" | "streaming" | "error";

export default function PatientPortal({
  clinicName,
  voice,
}: {
  clinicName: string;
  /** Null when the backend could not be reached; voice is then simply absent. */
  voice: VoiceStatus | null;
}) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [turns, setTurns] = useState(0);
  const [intakeComplete, setIntakeComplete] = useState(false);
  const [posted, setPosted] = useState<PostedFile[]>([]);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<string>("lab_report");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [turnState, setTurnState] = useState<TurnState>("idle");
  /** The reply as it arrives. Transient — the stored turn replaces it. */
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // --- voice ---------------------------------------------------------------
  // Voice is an input channel, so it owns no conversation state of its own:
  // a transcript goes straight into `runTurn` alongside typed turns, and the
  // reply it plays is the same stream the thread is rendering.
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [recording, setRecording] = useState<Recording | null>(null);
  const [heard, setHeard] = useState<string | null>(null);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  /** Turn indices that arrived by voice, so the thread can mark them. */
  const [spokenTurns, setSpokenTurns] = useState<number[]>([]);
  const speaker = useRef<SpeechQueue | null>(null);

  /** True while a turn is in flight, in either mode. */
  const working = turnState === "thinking" || turnState === "streaming";

  // Keep the newest message in view as it grows. Scrolling only — no state is
  // set here, so this stays legal under the React Compiler's effect rules.
  useEffect(() => {
    const node = scroller.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [transcript.length, posted.length, busy, streamText, turnState]);

  const fail = (err: unknown) =>
    setError(err instanceof ApiError ? err.message : String(err));

  async function begin(granted: boolean) {
    setBusy(true);
    setError(null);
    try {
      const session = await api.startSession({ fixture: "walk-in demo" });
      await api.recordConsent(session.session_id, granted);
      if (!granted) {
        setError("Intake stopped. Nothing further was collected.");
        return;
      }
      setSessionId(session.session_id);
      setCaseId(session.case_id);
      setTranscript([
        {
          role: "assistant",
          content:
            "Thanks for confirming. To get started — what brings you in today?",
        },
      ]);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  /**
   * One patient turn, whether it was typed or spoken.
   *
   * Both modes call this, both modes hit the same endpoint, and both modes
   * render the same stream — voice differs only in that it also hands each
   * speech segment to the playback queue. There is one generated reply and it
   * is heard and read at the same time.
   */
  async function runTurn(content: string, channel: "text" | "voice") {
    if (!sessionId) return;

    // Voice: the queue lives for one turn, so an interrupt cannot leak into
    // the next one. Text: no queue at all, so a broken TTS model cannot touch
    // typed intake.
    const queue =
      channel === "voice" && caseId
        ? speechQueue(
            (text, index) => api.speech(text, caseId, index),
            () =>
              setVoiceNotice(
                "The reply could not be played aloud. You can read it above.",
              ),
          )
        : null;
    speaker.current = queue;

    setTurnState("thinking");
    setStreamText("");
    setError(null);
    setVoiceNotice(null);

    try {
      const result = await api.streamMessage(sessionId, content, channel, (event) => {
        if (event.type === "token") {
          setTurnState("streaming");
          setStreamText((prior) => prior + event.text);
        } else if (event.type === "segment" && queue) {
          // The console shows "speaking" from the first phrase, not from the
          // end of generation — which is the point of segmenting at all.
          setPhase("speaking");
          queue.push(event.text, event.index);
        }
      });

      // The stored turn, not the chunks, is what the thread shows from here.
      setTranscript(result.transcript);
      setMissingFields(result.missing_fields);
      setIntakeComplete(result.intake_complete);
      setTurns(result.turn_index + 1);
      if (channel === "voice") {
        setSpokenTurns((prior) => [...prior, result.turn_index]);
      }
      setTurnState("idle");
      setStreamText("");

      await queue?.idle();

      // Intake is finished, so the workflow continues on its own rather than
      // waiting for a button the patient has no reason to expect. The closing
      // message says this is happening. Submit stays for anyone who wants to
      // stop early with fields still outstanding.
      if (result.intake_complete && !submitted) {
        await submit();
      }
    } catch (err) {
      queue?.stop();
      setTurnState("error");
      setStreamText("");
      fail(err);
    } finally {
      if (speaker.current === queue) speaker.current = null;
      setPhase("idle");
    }
  }

  async function send() {
    if (!sessionId || !draft.trim() || busy || working) return;
    const content = draft.trim();
    setDraft("");
    setTranscript((prior) => [...prior, { role: "patient", content }]);
    await runTurn(content, "text");
  }

  async function upload(file: File) {
    if (!caseId) return;
    setBusy(true);
    setError(null);
    setUploadOpen(false);
    try {
      const stored = await api.uploadAttachment(caseId, file, kind);
      // Pin it where the conversation is now, so it reads as part of the thread.
      setPosted((prior) => [
        ...prior,
        { file: stored, afterTurn: transcript.length },
      ]);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  /* --- voice cycle -------------------------------------------------------
   * listen -> transcribe -> the ordinary intake turn -> speak the reply as it
   * is written. Only the first and last steps are voice; the middle is
   * `runTurn`, exactly what the Send button calls, and the speech comes out of
   * that same stream rather than a second request once it has finished. */

  async function startListening() {
    setError(null);
    setVoiceNotice(null);
    try {
      const handle = await record();
      setRecording(handle);
      setPhase("listening");
    } catch (err) {
      setPhase("idle");
      setError(
        err instanceof MicrophoneError
          ? err.message
          : "The microphone could not be started. You can still type your answers.",
      );
    }
  }

  function cancelListening() {
    recording?.cancel();
    setRecording(null);
    setPhase("idle");
  }

  async function stopListening() {
    if (!recording || !sessionId || !caseId) return;
    const handle = recording;
    setRecording(null);
    setPhase("transcribing");
    setError(null);
    try {
      const wav = await handle.stop();
      const { transcript: spoken } = await api.transcribe(wav, caseId);
      setHeard(spoken);

      // From here it is an ordinary typed turn — same endpoint, same agents,
      // same stream. `runTurn` moves the console on to speaking by itself,
      // when the first speakable phrase arrives rather than when the model
      // has finished writing.
      setPhase("processing");
      setTranscript((prior) => [...prior, { role: "patient", content: spoken }]);
      await runTurn(spoken, "voice");
    } catch (err) {
      setPhase("idle");
      fail(err);
    }
  }

  /**
   * Interrupt playback. Silences what is being spoken and drops the segments
   * queued behind it; the reply itself stays on screen and the turn is already
   * stored, so nothing about the conversation is lost.
   */
  function stopSpeaking() {
    speaker.current?.stop();
    setPhase("idle");
  }

  async function submit() {
    if (!caseId) return;
    setBusy(true);
    setError(null);
    try {
      await api.prescreen(caseId);
      setSubmitted(true);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  /* --- consent gate ------------------------------------------------------ */

  if (!sessionId) {
    return (
      <div className="mx-auto mt-6 max-w-2xl">
        <div className="rounded-md border border-line bg-surface/80">
          <div className="border-b border-line-soft bg-gradient-to-r from-accent/8 to-transparent px-7 py-6">
            <p className="eyebrow">{clinicName}</p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight">
              Let&apos;s get you ready for your appointment
            </h1>
            <p className="mt-2 text-sm leading-6 text-dim">
              An assistant will ask a few questions so your clinician has what they
              need before you arrive. It takes about three minutes.
            </p>
          </div>

          <div className="space-y-4 px-7 py-6">
            <ul className="space-y-3 text-sm text-dim">
              {[
                ["It organises what you tell us — it does not diagnose you or suggest treatment.", icons.shield],
                ["A qualified clinician reviews everything before any next step.", icons.stethoscope],
                ["You can upload reports or scans; they are stored for your clinician to read.", icons.file],
              ].map(([text, Icon]) => {
                const Glyph = Icon as (typeof icons)["shield"];
                return (
                  <li key={text as string} className="flex gap-3">
                    <Glyph className="mt-0.5 shrink-0 text-[16px] text-accent" />
                    <span>{text as string}</span>
                  </li>
                );
              })}
            </ul>

            <p className="rounded border border-line bg-raised/60 px-4 py-3 text-sm">
              Do you consent to us collecting this information?
            </p>

            {error && <Banner tone="error">{error}</Banner>}

            <div className="flex gap-3">
              <Button variant="primary" onClick={() => void begin(true)} disabled={busy}>
                {busy ? "Starting…" : "I consent — start"}
              </Button>
              <Button onClick={() => void begin(false)} disabled={busy}>
                I do not consent
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* --- intake ------------------------------------------------------------ */

  const collected = (field: string) => turns > 0 && !missingFields.includes(field);
  const stepState = STEPS.map((step, index) => {
    if (index === 0) return "done" as const;
    if (step.label === "Documents")
      return posted.length ? ("done" as const) : ("open" as const);
    if (step.label === "Review")
      return submitted ? ("done" as const) : intakeComplete ? ("open" as const) : ("todo" as const);
    return step.fields.every(collected) ? ("done" as const) : ("todo" as const);
  });
  const currentIndex = stepState.findIndex((state) => state !== "done");

  /** Turns and uploads woven into one ordered thread. */
  const filesAfter = (index: number) =>
    posted.filter((entry) => entry.afterTurn === index);

  return (
    // Viewport-locked once the rail sits beside the chat; below that the two
    // stack and the page scrolls normally rather than squeezing both.
    <div className="grid items-stretch gap-5 lg:h-[calc(100vh-10rem)] lg:grid-cols-[1fr_22rem]">
      <div className="flex min-h-0 flex-col overflow-hidden rounded-md border border-line bg-surface/80 max-lg:h-[70vh]">
        <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line-soft px-6 py-4">
          <span className="grid size-9 place-items-center rounded-full bg-accent/12 text-accent ring-1 ring-accent/30">
            <icons.stethoscope className="text-[18px]" />
          </span>
          <div>
            <h1 className="text-sm font-semibold">Healthcare Assistant</h1>
            <p className="font-mono text-xs text-faint">
              Case {caseId ? caseRef(caseId) : "—"}
            </p>
          </div>
          <span className="ml-auto flex items-center gap-2 text-xs text-dim">
            <Dot tone={submitted ? "low" : "info"} live={!submitted} />
            {submitted ? "Submitted for review" : "Intake in progress"}
          </span>
        </header>

        {/* the only scrollable region on the page */}
        <div ref={scroller} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-6">
          {filesAfter(0).map((entry) => (
            <FileMessage key={entry.file.id} file={entry.file} caseId={caseId} />
          ))}

          {transcript.map((turn, index) => (
            <div key={index} className="space-y-5">
              <div
                className={`flex gap-3 ${turn.role === "patient" ? "flex-row-reverse" : ""}`}
              >
                <span
                  className={`mt-0.5 grid size-7 shrink-0 place-items-center rounded-full text-[13px] ${
                    turn.role === "patient"
                      ? "bg-raised text-dim"
                      : "bg-accent/12 text-accent ring-1 ring-accent/25"
                  }`}
                >
                  {turn.role === "patient" ? "You" : <icons.stethoscope />}
                </span>
                <p
                  className={`max-w-2xl rounded-lg px-4 py-2.5 text-sm leading-6 ${
                    turn.role === "patient"
                      ? "rounded-tr-sm bg-raised text-text"
                      : "rounded-tl-sm border border-line bg-surface text-text"
                  }`}
                >
                  {spokenTurns.includes(index) && (
                    <icons.mic
                      className="mr-1.5 inline-block align-[-2px] text-[14px] text-faint"
                      aria-label="Spoken"
                    />
                  )}
                  {turn.content}
                </p>
              </div>

              {filesAfter(index + 1).map((entry) => (
                <FileMessage key={entry.file.id} file={entry.file} caseId={caseId} />
              ))}
            </div>
          ))}

          {/* The reply in progress: one bubble that grows, never one per
              chunk. It is replaced by the stored turn when the stream ends. */}
          {working && (
            <div className="flex items-start gap-3">
              <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-accent/12 text-accent ring-1 ring-accent/25">
                <icons.stethoscope className="text-[13px]" />
              </span>
              {turnState === "streaming" ? (
                <p className="max-w-2xl rounded-lg rounded-tl-sm border border-line bg-surface px-4 py-2.5 text-sm leading-6 text-text">
                  {streamText}
                  <span className="ml-0.5 inline-block h-4 w-px translate-y-0.5 animate-pulse bg-accent" />
                </p>
              ) : (
                <span className="flex gap-1 rounded-lg border border-line bg-surface px-4 py-3">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="size-1.5 animate-bounce rounded-full bg-faint"
                      style={{ animationDelay: `${i * 120}ms` }}
                    />
                  ))}
                </span>
              )}
            </div>
          )}

          {/* "generating" vs "finished" is the distinction streaming exists to
              make, so it is said in words rather than left to the caret. */}
          {working && (
            <p className="flex items-center gap-2 pl-10 text-[11px] text-faint">
              <Dot tone="info" live />
              {turnState === "thinking"
                ? "Reading your answer…"
                : phase === "speaking"
                  ? "Writing and speaking…"
                  : "Writing a reply…"}
            </p>
          )}
        </div>

        {(error || voiceNotice) && (
          <div className="shrink-0 space-y-2 px-6 pb-3">
            {error && <Banner tone="error">{error}</Banner>}
            {voiceNotice && <Banner tone="warn">{voiceNotice}</Banner>}
          </div>
        )}

        {/* --- composer ------------------------------------------------- */}
        <div className="shrink-0 border-t border-line-soft px-6 py-4">
          {submitted ? (
            <p className="text-sm text-dim">
              Your information is with the care team. There is nothing more to do
              here.{" "}
              <Link href="/dashboard" className="text-accent underline underline-offset-2">
                Open the staff view
              </Link>{" "}
              to continue the demonstration.
            </p>
          ) : (
            <>
              {/* Voice is optional: if the models are missing the tab explains
                  why and text intake is untouched. */}
              <div className="mb-3 flex items-center gap-2">
                <div className="flex rounded border border-line p-0.5">
                  {(
                    [
                      ["text", "Type", icons.file],
                      ["voice", "Voice", icons.mic],
                    ] as const
                  ).map(([value, label, Glyph]) => (
                    <button
                      key={value}
                      onClick={() => {
                        if (value === "text") {
                          cancelListening();
                          stopSpeaking();
                        }
                        setMode(value);
                      }}
                      disabled={value === "voice" && !voice?.available}
                      title={
                        value === "voice" && !voice?.available
                          ? (voice?.detail ?? "Voice is unavailable right now.")
                          : undefined
                      }
                      className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
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
                {mode === "voice" && voice?.available && (
                  <span className="text-[11px] text-faint">
                    Runs on this machine — {voice.stt_model} · {voice.tts_model}
                  </span>
                )}
                {!voice?.available && (
                  <span className="text-[11px] text-faint">
                    {voice?.detail ?? "Voice unavailable — text intake is unaffected."}
                  </span>
                )}
              </div>

              {/* One file input for both modes; the attach control just clicks it. */}
              <input
                ref={fileInput}
                type="file"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void upload(file);
                }}
              />

              {mode === "voice" ? (
                <div className="flex items-stretch gap-2">
                  <div className="min-w-0 flex-1">
                    <VoiceConsole
                      phase={phase}
                      recording={recording}
                      transcript={heard}
                      disabled={(busy || working) && phase === "idle"}
                      onStart={() => void startListening()}
                      onStop={() =>
                        phase === "speaking" ? stopSpeaking() : void stopListening()
                      }
                      onCancel={cancelListening}
                    />
                  </div>
                  <AttachControl
                    open={uploadOpen}
                    onToggle={() => setUploadOpen((open) => !open)}
                    kind={kind}
                    onKind={setKind}
                    onChoose={() => fileInput.current?.click()}
                    disabled={busy}
                  />
                </div>
              ) : (
                <div className="flex items-stretch gap-2">
                  <textarea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void send();
                      }
                    }}
                    placeholder="Type your answer…"
                    // Only while a turn is actually in flight. Reading a
                    // reply as it arrives should never block the page.
                    disabled={busy || working}
                    className={`${inputClass} h-11 min-w-0 flex-1 resize-none py-3 leading-5`}
                  />
                  <AttachControl
                    open={uploadOpen}
                    onToggle={() => setUploadOpen((open) => !open)}
                    kind={kind}
                    onKind={setKind}
                    onChoose={() => fileInput.current?.click()}
                    disabled={busy}
                  />
                  <Button
                    variant="primary"
                    onClick={() => void send()}
                    disabled={busy || working || !draft.trim()}
                    className="h-11 shrink-0 px-4"
                  >
                    <icons.send className="text-[15px]" />
                    Send
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* --- progress rail --------------------------------------------- */}
      <div className="min-h-0 space-y-5 lg:overflow-y-auto">
        <Panel eyebrow="Your intake" title="Progress">
          <ol className="space-y-0.5">
            {STEPS.map((step, index) => {
              const state = stepState[index];
              const isCurrent = index === currentIndex;
              return (
                <li
                  key={step.label}
                  className={`flex items-center gap-3 rounded px-2 py-2 text-sm ${
                    isCurrent ? "bg-accent/8 text-text" : "text-dim"
                  }`}
                >
                  <span
                    className={`grid size-5 shrink-0 place-items-center rounded-full border text-[10px] ${
                      state === "done"
                        ? "border-accent/50 bg-accent/15 text-accent"
                        : isCurrent
                          ? "border-accent text-accent"
                          : "border-line text-faint"
                    }`}
                  >
                    {state === "done" ? (
                      <icons.check className="text-[11px]" />
                    ) : isCurrent ? (
                      <span className="size-1.5 rounded-full bg-accent" />
                    ) : null}
                  </span>
                  <span className={isCurrent ? "font-medium" : ""}>{step.label}</span>
                  {step.optional && (
                    <span className="ml-auto text-[11px] text-faint">optional</span>
                  )}
                </li>
              );
            })}
          </ol>
        </Panel>

        <Panel eyebrow="Last step" title="Send to your care team">
          <p className="text-xs leading-5 text-dim">
            Your answers go to a clinician for review. No advice or result is shown
            to you before they have read it.
          </p>
          <Button
            variant="primary"
            onClick={() => void submit()}
            disabled={busy || working || submitted || turns === 0}
            className="mt-3 w-full justify-center"
          >
            {submitted ? "Submitted" : "Submit for clinician review"}
          </Button>
          {!intakeComplete && !submitted && turns > 0 && (
            <p className="mt-2 text-[11px] text-med">
              You can submit now, but the assistant still has a few questions.
            </p>
          )}
        </Panel>
      </div>
    </div>
  );
}

/**
 * The attach button and its upload popover.
 *
 * Rendered next to whichever composer is active — the text field or the voice
 * console — so documents work the same either way. Uploads are separate from
 * speech: a recording is transcribed and discarded, never filed as a record.
 */
function AttachControl({
  open,
  onToggle,
  kind,
  onKind,
  onChoose,
  disabled,
}: {
  open: boolean;
  onToggle: () => void;
  kind: string;
  onKind: (kind: string) => void;
  onChoose: () => void;
  disabled: boolean;
}) {
  return (
    <div className="relative shrink-0">
      {open && (
        <>
          {/* Click-away without a document listener. */}
          <button
            className="fixed inset-0 z-10 cursor-default"
            onClick={onToggle}
            aria-label="Close upload panel"
          />
          <div className="absolute bottom-full right-0 z-20 mb-2 w-72 rounded-md border border-line bg-surface p-4 shadow-lg">
            <p className="eyebrow">Attach a document</p>
            <p className="mt-1 text-[11px] leading-4 text-faint">
              Stored for your clinician to open. It is not read automatically.
            </p>
            <select
              value={kind}
              onChange={(event) => onKind(event.target.value)}
              className={`${inputClass} mt-3`}
              aria-label="Document type"
            >
              {ATTACHMENT_KINDS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <Button
              variant="primary"
              onClick={onChoose}
              disabled={disabled}
              className="mt-2 w-full justify-center"
            >
              <icons.plus className="text-[15px]" />
              Choose file
            </Button>
          </div>
        </>
      )}
      <Button
        onClick={onToggle}
        disabled={disabled}
        aria-label="Attach a document"
        aria-expanded={open}
        className={`h-11 w-11 justify-center px-0 ${
          open ? "border-accent/50 text-accent" : ""
        }`}
      >
        <icons.paperclip className="text-[17px]" />
      </Button>
    </div>
  );
}

/** An upload rendered as the patient's own message in the thread. */
function FileMessage({
  file,
  caseId,
}: {
  file: Attachment;
  caseId: string | null;
}) {
  const isImage = file.mime_type.startsWith("image/");
  return (
    <div className="flex flex-row-reverse gap-3">
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-raised text-[13px] text-dim">
        You
      </span>
      <div className="flex max-w-[22rem] gap-3 rounded-lg rounded-tr-sm border border-line bg-raised p-3">
        <span className="grid size-12 shrink-0 place-items-center overflow-hidden rounded border border-line bg-ink text-faint">
          {isImage && caseId ? (
            // eslint-disable-next-line @next/next/no-img-element -- backend file route, not an optimisable asset
            <img
              src={api.attachmentUrl(caseId, file.id)}
              alt=""
              className="size-full object-cover"
            />
          ) : (
            <icons.file className="text-[20px]" />
          )}
        </span>
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-text">{file.filename}</p>
          <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-faint">
            <Dot tone="low" />
            Uploaded · {(file.size_bytes / 1024).toFixed(0)} KB
          </p>
          <p className="mt-1.5 flex items-center gap-1.5">
            <Tag>{file.kind.replaceAll("_", " ")}</Tag>
            <span className="font-mono text-[10px] text-faint">
              {file.id.slice(0, 8)}
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
