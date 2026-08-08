"use client";

import { useEffect, useState } from "react";
import type { Recording } from "@/lib/audio";
import { Button, Dot, icons } from "@/lib/ui";

/**
 * The voice control surface. Presentational: it draws whichever phase the
 * portal is in and emits control events. The portal owns the state machine and
 * every network call, so there is exactly one place where a spoken turn is
 * turned into an intake turn.
 */

export type VoicePhase =
  | "idle"
  | "listening"
  | "transcribing"
  | "processing"
  | "speaking";

const PHASE_COPY: Record<VoicePhase, { label: string; hint: string }> = {
  idle: { label: "Tap to speak", hint: "Your answer is written down, not recorded." },
  listening: { label: "Listening…", hint: "Speak naturally, then press Stop." },
  transcribing: { label: "Writing that down…", hint: "Turning your speech into text." },
  processing: { label: "Thinking…", hint: "The assistant is reading your answer." },
  speaking: { label: "Speaking…", hint: "Press Stop to interrupt." },
};

const BAR_COUNT = 28;
const FLAT: number[] = new Array(BAR_COUNT).fill(0);

export default function VoiceConsole({
  phase,
  recording,
  transcript,
  disabled,
  onStart,
  onStop,
  onCancel,
}: {
  phase: VoicePhase;
  /** Live handle while listening; used only to read real audio levels. */
  recording: Recording | null;
  /** Last transcript, shown back so the patient can see what was heard. */
  transcript: string | null;
  disabled: boolean;
  onStart: () => void;
  onStop: () => void;
  onCancel: () => void;
}) {
  const [bars, setBars] = useState<number[]>(FLAT);

  // Animate the meter from real analyser data while listening. Confined to
  // this component so the conversation above does not re-render each frame.
  // The idle state is derived below rather than reset here — resetting would
  // be a synchronous setState in an effect body.
  useEffect(() => {
    if (phase !== "listening" || !recording) return;
    let frame = requestAnimationFrame(function tick() {
      setBars(recording.bands(BAR_COUNT));
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [phase, recording]);

  const levels = phase === "listening" ? bars : FLAT;
  const copy = PHASE_COPY[phase];
  const busy = phase === "transcribing" || phase === "processing";

  return (
    <div className="rounded-md border border-line bg-ink/40 px-5 py-4">
      <div className="flex items-center gap-5">
        {/* mic / state button */}
        <button
          onClick={phase === "idle" ? onStart : onStop}
          disabled={disabled || busy}
          aria-label={phase === "idle" ? "Start speaking" : "Stop"}
          className={`grid size-14 shrink-0 place-items-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            phase === "listening"
              ? "running-dot border-high/60 bg-high/12 text-high"
              : phase === "speaking"
                ? "border-info/60 bg-info/12 text-info"
                : busy
                  ? "border-line bg-raised text-faint"
                  : "border-accent/50 bg-accent/12 text-accent hover:bg-accent/20"
          }`}
        >
          {phase === "listening" ? (
            <icons.stop className="text-[18px]" />
          ) : phase === "speaking" ? (
            <icons.pulse className="text-[22px]" />
          ) : (
            <icons.mic className="text-[24px]" />
          )}
        </button>

        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-medium text-text">
            <Dot
              tone={
                phase === "listening"
                  ? "high"
                  : phase === "speaking"
                    ? "info"
                    : phase === "idle"
                      ? "neutral"
                      : "med"
              }
              live={phase !== "idle"}
            />
            {copy.label}
          </p>
          <p className="mt-0.5 text-[11px] text-faint">{copy.hint}</p>

          {/* real analyser output, flat when not listening */}
          <div className="mt-2.5 flex h-8 items-center gap-[3px]" aria-hidden>
            {levels.map((value, index) => (
              <span
                key={index}
                className={`w-full rounded-full transition-[height] duration-75 ${
                  phase === "listening" ? "bg-high/70" : "bg-line"
                }`}
                style={{ height: `${Math.max(3, value * 100)}%` }}
              />
            ))}
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2">
          {phase === "listening" && (
            <>
              <Button variant="primary" onClick={onStop}>
                <icons.stop className="text-[13px]" />
                Stop
              </Button>
              <Button onClick={onCancel}>Cancel</Button>
            </>
          )}
          {phase === "speaking" && (
            <Button onClick={onStop}>
              <icons.stop className="text-[13px]" />
              Stop
            </Button>
          )}
          {busy && (
            <span className="text-[11px] text-faint">working…</span>
          )}
        </div>
      </div>

      {transcript && (
        <p className="mt-3 border-t border-line-soft pt-3 text-sm leading-6 text-dim">
          <span className="eyebrow mr-2">Heard</span>
          &ldquo;{transcript}&rdquo;
        </p>
      )}
    </div>
  );
}
