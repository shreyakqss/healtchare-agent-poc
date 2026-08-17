"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  api,
  type AnswerOptions,
  type Attachment,
  type MessageResponse,
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
import { Banner, Button, Dot, Tag, caseRef, icons, inputClass } from "@/lib/ui";
import VoiceConsole, { type VoicePhase } from "./voice-console";

/**
 * The conversation. Deliberately says nothing about agents, rules, priorities
 * or model behaviour — the clinician sees that, the patient sees a calm
 * assistant.
 *
 * **There is no start step.** The patient lands in a live chat with the
 * assistant already speaking, and the intake session is created on their first
 * message or upload rather than behind a consent wall. Consent is still
 * recorded — `ensureSession` posts it in the same breath as opening the
 * session, and the notice above the composer is what the patient agrees to by
 * sending. That is a deliberate trade of an explicit click for a direct
 * screen; if a deployment needs affirmative click-through consent, this is the
 * one place to put it back.
 */

const ATTACHMENT_KINDS = [
  ["prescription", "Prescription"],
  ["lab_report", "Lab / blood report"],
  ["radiology", "Scan or X-ray"],
  ["pathology", "Pathology report"],
  ["referral", "Referral letter"],
  ["other", "Something else"],
] as const;

/** Intake steps, each satisfied by the backend's required-field keys. */
const STEPS = [
  { label: "Reason for visit", fields: ["reason_for_visit"] },
  { label: "Symptoms", fields: ["symptom", "duration"] },
  { label: "About you", fields: ["name", "age", "gender"] },
  { label: "History", fields: ["history"] },
  { label: "Medicines & allergies", fields: ["medication", "allergy"] },
  { label: "Contact", fields: ["contact_preference"] },
];

const GREETING =
  "Hello — I'm the clinic assistant. Tell me what's bothering you and I'll " +
  "get everything your clinician needs. You can also attach a prescription " +
  "or an old report at any point, using the paperclip below.";

/** An upload, pinned to the point in the conversation where it happened. */
type PostedFile = { file: Attachment; afterTurn: number };

/**
 * Where a turn is. `thinking` is the wait before the first token — extraction
 * and planning — and `streaming` is the reply arriving. They are separate so
 * the patient can tell "still working" from "writing now", which is the whole
 * reason for streaming in the first place.
 */
type TurnState = "idle" | "thinking" | "streaming" | "error";

export default function PatientChat({
  voice,
  onSessionStarted,
  onSubmitted,
}: {
  /** Null when the backend could not be reached; voice is then simply absent. */
  voice: VoiceStatus | null;
  /** Fires once, when the visit is actually opened on the backend. */
  onSessionStarted: (caseId: string, sessionId: string) => void;
  /** Fires when the visit goes to the care team, so the shell can refresh. */
  onSubmitted: () => void;
}) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([
    { role: "assistant", content: GREETING },
  ]);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [turns, setTurns] = useState(0);
  const [posted, setPosted] = useState<PostedFile[]>([]);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<string>("prescription");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [turnState, setTurnState] = useState<TurnState>("idle");
  /** The reply as it arrives. Transient — the stored turn replaces it. */
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // --- one-tap answers -----------------------------------------------------
  // Offered beside the question, never instead of it: tapping one sends an
  // ordinary patient message and the composer never goes away.
  const [options, setOptions] = useState<AnswerOptions | null>(null);
  /** A chosen option that still needs a detail typed — "Phone" wants a number. */
  const [pending, setPending] = useState<{ option: string; prompt: string } | null>(
    null,
  );
  const [pendingDetail, setPendingDetail] = useState("");
  /** Which turn the options belong to, so a late reply cannot show stale chips. */
  const turnToken = useRef(0);

  // --- voice ---------------------------------------------------------------
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

  /**
   * The visit, opened on demand.
   *
   * Called by the first thing the patient actually does — sending a message or
   * attaching a document — so nothing is created for someone who only looked
   * at the page. Consent is recorded here because this is the moment the
   * patient has acted on the notice shown above the composer.
   */
  async function ensureSession(): Promise<{ sessionId: string; caseId: string } | null> {
    if (sessionId && caseId) return { sessionId, caseId };
    try {
      const session = await api.startSession({ fixture: "walk-in" });
      await api.recordConsent(session.session_id, true);
      setSessionId(session.session_id);
      setCaseId(session.case_id);
      onSessionStarted(session.case_id, session.session_id);
      return { sessionId: session.session_id, caseId: session.case_id };
    } catch (err) {
      fail(err);
      return null;
    }
  }

  /**
   * Fetch the one-tap answers for the question that just arrived.
   *
   * Deliberately not awaited by the turn: the reply is already on screen and
   * readable, and chips appearing a moment later costs the patient nothing.
   * `token` drops the result if another turn has started since.
   */
  async function loadOptions(result: MessageResponse, token: number) {
    if (result.intake_complete || !result.next_question) return;
    try {
      const next = await api.suggestions(
        result.session_id,
        result.next_question,
        result.asks_field,
      );
      if (token !== turnToken.current) return;
      setOptions(next.options.length ? next : null);
    } catch {
      /* Options are a convenience. Without them the patient types. */
    }
  }

  /**
   * One patient turn, whether it was typed or spoken.
   *
   * Both modes hit the same endpoint and render the same stream — voice
   * differs only in also handing each speech segment to the playback queue.
   * The ids are passed in rather than read from state because the very first
   * turn creates them, and that `setState` has not landed yet.
   */
  async function runTurn(
    content: string,
    channel: "text" | "voice",
    ids: { sessionId: string; caseId: string },
  ) {
    // Whatever was on offer answered the previous question.
    const token = ++turnToken.current;
    setOptions(null);
    setPending(null);
    setPendingDetail("");

    // Voice: the queue lives for one turn, so an interrupt cannot leak into
    // the next one. Text: no queue at all, so a broken TTS model cannot touch
    // typed intake.
    const queue =
      channel === "voice"
        ? speechQueue(
            (text, index) => api.speech(text, ids.caseId, index),
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
      const result = await api.streamMessage(
        ids.sessionId,
        content,
        channel,
        (event) => {
          if (event.type === "token") {
            setTurnState("streaming");
            setStreamText((prior) => prior + event.text);
          } else if (event.type === "segment" && queue) {
            // "Speaking" from the first phrase, not from the end of
            // generation — which is the point of segmenting at all.
            setPhase("speaking");
            queue.push(event.text, event.index);
          }
        },
      );

      // The stored turn, not the chunks, is what the thread shows from here.
      // The greeting is local, so it is kept in front of the server's copy.
      setTranscript([{ role: "assistant", content: GREETING }, ...result.transcript]);
      setMissingFields(result.missing_fields);
      setTurns(result.turn_index + 1);
      if (channel === "voice") {
        setSpokenTurns((prior) => [...prior, result.turn_index]);
      }
      setTurnState("idle");
      setStreamText("");

      await queue?.idle();

      // Intake is finished, so the workflow continues on its own rather than
      // waiting for a button the patient has no reason to expect.
      if (result.intake_complete && !submitted) {
        await submit(ids.caseId);
      } else {
        void loadOptions(result, token);
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

  /** Show the message immediately, then open the visit if this is the first one. */
  async function sendContent(content: string, channel: "text" | "voice") {
    setTranscript((prior) => [...prior, { role: "patient", content }]);
    const ids = await ensureSession();
    if (!ids) return;
    await runTurn(content, channel, ids);
  }

  async function send() {
    if (!draft.trim() || busy || working) return;
    const content = draft.trim();
    setDraft("");
    await sendContent(content, "text");
  }

  /**
   * Tap an offered answer.
   *
   * Most send straight away — the whole point is one tap instead of typing.
   * The ones that need a detail ("Phone" wants a number) open a single input
   * instead, and what is finally sent is still one ordinary patient message.
   */
  async function choose(option: string) {
    if (busy || working) return;
    const prompt = options?.follow_ups?.[option];
    if (prompt) {
      setPending({ option, prompt });
      setPendingDetail("");
      return;
    }
    await sendContent(option, "text");
  }

  /** Send the chosen option with whatever was typed after it, as one turn. */
  async function sendPending() {
    if (!pending || busy || working) return;
    const typed = pendingDetail.trim();
    const content = typed
      ? `Contact me by ${pending.option.toLowerCase()}: ${typed}`
      : `Contact me by ${pending.option.toLowerCase()}.`;
    await sendContent(content, "text");
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setUploadOpen(false);
    try {
      const ids = await ensureSession();
      if (!ids) return;
      const stored = await api.uploadAttachment(ids.caseId, file, kind);
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
   * is written. Only the first and last steps are voice; the middle is the
   * same call the Send button makes. */

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
    if (!recording) return;
    const handle = recording;
    setRecording(null);
    setPhase("transcribing");
    setError(null);
    try {
      // Transcription is filed against the case, so the visit has to exist
      // before the microphone result can be sent anywhere.
      const ids = await ensureSession();
      if (!ids) {
        setPhase("idle");
        return;
      }
      const wav = await handle.stop();
      const { transcript: spoken } = await api.transcribe(wav, ids.caseId);
      setHeard(spoken);

      setPhase("processing");
      setTranscript((prior) => [...prior, { role: "patient", content: spoken }]);
      await runTurn(spoken, "voice", ids);
    } catch (err) {
      setPhase("idle");
      fail(err);
    }
  }

  /**
   * Interrupt playback. Silences what is being spoken and drops the segments
   * queued behind it; the reply stays on screen and the turn is already
   * stored, so nothing about the conversation is lost.
   */
  function stopSpeaking() {
    speaker.current?.stop();
    setPhase("idle");
  }

  async function submit(id: string) {
    setBusy(true);
    setError(null);
    try {
      await api.prescreen(id);
      setSubmitted(true);
      onSubmitted();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  /* --- progress ----------------------------------------------------------- */

  const collected = (field: string) => turns > 0 && !missingFields.includes(field);
  const done = STEPS.filter((step) => step.fields.every(collected)).length;
  const currentIndex = STEPS.findIndex((step) => !step.fields.every(collected));

  /** Turns and uploads woven into one ordered thread. */
  const filesAfter = (index: number) =>
    posted.filter((entry) => entry.afterTurn === index);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-md border border-line bg-surface/80">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line-soft px-6 py-4">
        <span className="grid size-9 place-items-center rounded-full bg-accent/12 text-accent ring-1 ring-accent/30">
          <icons.stethoscope className="text-[18px]" />
        </span>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold">Healthcare Assistant</h1>
          <p className="font-mono text-xs text-faint">
            {caseId ? `Visit ${caseRef(caseId)}` : "Not started yet"}
          </p>
        </div>
        <span className="ml-auto flex items-center gap-2 text-xs text-dim">
          <Dot tone={submitted ? "low" : caseId ? "info" : "neutral"} live={Boolean(caseId) && !submitted} />
          {submitted
            ? "With the care team"
            : caseId
              ? "In progress"
              : "Ready when you are"}
        </span>
      </header>

      {/* A quiet progress strip rather than a column of its own: it says how
          much is left without competing with the conversation. */}
      {caseId && !submitted && (
        <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line-soft bg-raised/30 px-6 py-2.5">
          <span className="eyebrow">Progress</span>
          <span className="flex flex-1 items-center gap-1.5">
            {STEPS.map((step, index) => {
              const isDone = step.fields.every(collected);
              return (
                <span
                  key={step.label}
                  title={step.label}
                  className={`h-1 flex-1 rounded-full transition-colors ${
                    isDone
                      ? "bg-accent"
                      : index === currentIndex
                        ? "bg-accent/35"
                        : "bg-line"
                  }`}
                />
              );
            })}
          </span>
          <span className="text-[11px] text-faint">
            {currentIndex === -1
              ? "All done"
              : `${done} of ${STEPS.length} · ${STEPS[currentIndex].label}`}
          </span>
        </div>
      )}

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

        {/* The reply in progress: one bubble that grows, never one per chunk.
            It is replaced by the stored turn when the stream ends. */}
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
          <div className="flex items-start gap-3 rounded border border-low/40 bg-low/8 px-4 py-3">
            <icons.check className="mt-0.5 shrink-0 text-[16px] text-low" />
            <p className="text-sm leading-6 text-dim">
              Thank you — everything you told us is with the care team, and a
              clinician will review it. Anything they write back will appear
              under <span className="text-text">My results</span>.
            </p>
          </div>
        ) : (
          <>
            {/* One-tap answers. Never a menu: the composer below stays live,
                and anything not on offer is typed as it always was. */}
            {pending ? (
              <div className="mb-3 rounded border border-accent/35 bg-accent/6 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <Tag tone="accent">{pending.option}</Tag>
                  <span className="text-xs text-dim">{pending.prompt}</span>
                  <button
                    onClick={() => setPending(null)}
                    className="ml-auto text-[11px] text-faint hover:text-dim"
                  >
                    change
                  </button>
                </div>
                <div className="mt-2 flex items-stretch gap-2">
                  <input
                    value={pendingDetail}
                    onChange={(event) => setPendingDetail(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void sendPending();
                      }
                    }}
                    // Gets the right keyboard on a phone, which is most of
                    // why anyone taps a chip instead of typing.
                    type={pending.option === "Email" ? "email" : "tel"}
                    inputMode={pending.option === "Email" ? "email" : "tel"}
                    autoFocus
                    placeholder={pending.prompt}
                    disabled={busy || working}
                    className={`${inputClass} h-9 min-w-0 flex-1`}
                  />
                  <Button
                    variant="primary"
                    onClick={() => void sendPending()}
                    disabled={busy || working}
                    className="h-9 shrink-0 px-3"
                  >
                    <icons.send className="text-[14px]" />
                    Send
                  </Button>
                </div>
              </div>
            ) : (
              options && (
                <div className="mb-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {options.options.map((option) => (
                      <button
                        key={option}
                        onClick={() => void choose(option)}
                        disabled={busy || working}
                        className="rounded-full border border-line bg-raised/50 px-3 py-1.5 text-xs text-dim transition-colors hover:border-accent/45 hover:bg-accent/8 hover:text-accent disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                  <p className="mt-1.5 text-[11px] text-faint">
                    {options.source === "llm"
                      ? "Shortcuts based on what you have already told us — tap one, or type your own answer."
                      : "Tap an answer, or type your own."}
                  </p>
                </div>
              )
            )}

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
                  {voice?.detail ?? "Voice unavailable — typing is unaffected."}
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
                  placeholder={
                    caseId
                      ? "Type your answer…"
                      : "Tell me what's bothering you…"
                  }
                  // Only while a turn is actually in flight. Reading a reply
                  // as it arrives should never block the page.
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

            {/* The consent that replaced the start screen. Shown until the
                visit exists, which is exactly until it has been acted on. */}
            {!caseId && (
              <p className="mt-2.5 text-[11px] leading-4 text-faint">
                By sending a message you agree we may collect this information
                for your care. It is not a diagnosis — a clinician reviews
                everything before any next step, and you may decline any
                question.
              </p>
            )}
          </>
        )}
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
              A prescription, an old report, a scan. Stored for your clinician
              to open — it is not read automatically.
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
