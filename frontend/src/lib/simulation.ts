/**
 * Drives one simulated patient through the whole workflow.
 *
 * **There is no simulation backend.** Every line below is a call the patient
 * portal or the staff dashboard already makes: start a session, consent, send
 * turns, pre-screen, review, record notes, finalise. The only simulation-
 * specific call is `api.patientReply`, which asks the patient agent what its
 * Synthea record would say next — the patient's side of the conversation, never
 * the clinic's. That is what makes the demo honest: the agents cannot tell a
 * simulated case from a typed one, because there is nothing to tell apart.
 *
 * Several of these run at once, one per selected patient, as plain concurrent
 * promises. They share nothing but the control flags, so the interleaving on
 * screen is real concurrency rather than a scripted animation.
 *
 * The agent view of each run is not tracked here either: after every step the
 * case is re-read and `buildPipeline` derives statuses, artefacts and timings
 * from the audit trail, exactly as the case page and the operations centre do.
 */

import { buildPipeline, type AgentRun } from "./agents";
import {
  api,
  type AuditEvent,
  type CaseDetail,
  type PatientProfile,
  type TranscriptTurn,
} from "./api";

/** Where a run is in its journey. Coarser than the agent pipeline on purpose. */
export type SimPhase =
  | "queued"
  | "intake"
  | "prescreen"
  | "review"
  | "consultation"
  | "final"
  | "done"
  | "stopped"
  | "failed";

export type SimRun = {
  profile: PatientProfile;
  phase: SimPhase;
  /** One line of what this patient is doing right now. */
  activity: string;
  /** Pipeline key currently executing, overlaid on the derived statuses. */
  step: string | null;
  sessionId: string | null;
  caseId: string | null;
  detail: CaseDetail | null;
  audit: AuditEvent[];
  runs: AgentRun[];
  transcript: TranscriptTurn[];
  /** The assistant's reply as it streams in. Cleared when the turn lands. */
  streaming: string;
  turns: number;
  /** Whether the last patient turn was written by the model or the record. */
  replySource: "llm" | "script" | null;
  awaitingReview: boolean;
  startedAt: number | null;
  endedAt: number | null;
  error: string | null;
};

export type SimControl = {
  paused: boolean;
  stopped: boolean;
  /** Stop at the review gate for a human, instead of approving on the spot. */
  hold: boolean;
  /** Profile ids a human has approved while `hold` is on. */
  approved: Set<string>;
};

/** Beat between turns, so an audience can follow a conversation as it happens. */
const PACE_MS = 600;

/** Backstop matching the planner's own question ceiling. */
const MAX_TURNS = 14;

class Stopped extends Error {}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function blankRun(profile: PatientProfile): SimRun {
  return {
    profile,
    phase: "queued",
    activity: "Waiting to start",
    step: null,
    sessionId: null,
    caseId: null,
    detail: null,
    audit: [],
    runs: [],
    transcript: [],
    streaming: "",
    turns: 0,
    replySource: null,
    awaitingReview: false,
    startedAt: null,
    endedAt: null,
    error: null,
  };
}

export const newControl = (hold: boolean): SimControl => ({
  paused: false,
  stopped: false,
  hold,
  approved: new Set(),
});

/** Pause and stop are checked between steps, never mid-request. */
async function gate(ctl: SimControl) {
  while (ctl.paused && !ctl.stopped) await sleep(150);
  if (ctl.stopped) throw new Stopped();
}

/**
 * One patient, start to finish.
 *
 * `emit` receives partial updates as they happen; the caller owns the state.
 * Resolves when the visit summary is released, the run is stopped, or a step
 * fails — a failure is reported on the run, not thrown, because two other
 * patients are still going.
 */
export async function runPatient(
  profile: PatientProfile,
  ctl: SimControl,
  emit: (patch: Partial<SimRun>) => void,
): Promise<void> {
  try {
    emit({
      phase: "intake",
      step: "intake",
      activity: "Opening an intake session",
      startedAt: Date.now(),
      error: null,
    });
    await gate(ctl);

    // The record travels as the demographics fixture. `simulated` is a label
    // for the UI; no backend code branches on it, which is the point.
    const session = await api.startSession({
      name: profile.name,
      fixture_id: profile.name,
      age: profile.age,
      sex: profile.gender,
      simulated: true,
      source: "synthea",
      record_id: profile.id,
      reason: profile.reason,
    });
    const { session_id: sessionId, case_id: caseId } = session;
    emit({ sessionId, caseId });

    emit({ activity: "Granting consent" });
    await api.recordConsent(sessionId, true);

    /** Re-read the case and re-derive the agent view from the audit trail. */
    const refresh = async (): Promise<CaseDetail> => {
      const [next, audit] = await Promise.all([
        api.getCase(caseId),
        api.audit(caseId),
      ]);
      emit({ detail: next, audit, runs: buildPipeline(next, audit) });
      return next;
    };
    await refresh();

    /** Send one patient turn and watch the assistant's reply arrive. */
    const say = async (content: string) => {
      emit({
        activity: `Said: “${content}”`,
        streaming: "",
        step: "extractor",
      });
      let streamed = "";
      const response = await api.streamMessage(
        sessionId,
        content,
        "text",
        (event) => {
          if (event.type !== "token") return;
          streamed += event.text;
          emit({ streaming: streamed, step: "planner" });
        },
      );
      emit({
        transcript: response.transcript,
        streaming: "",
        turns: response.transcript.filter((turn) => turn.role === "patient").length,
      });
      await refresh();
      return response;
    };

    let response = await say(profile.opening);

    while (!response.intake_complete && response.turn_index < MAX_TURNS) {
      await gate(ctl);
      await sleep(PACE_MS);
      emit({ activity: "Reading the question and checking the record", step: "extractor" });

      const answer = await api.patientReply(
        profile.id,
        response.next_question,
        response.missing_fields,
      );
      emit({ replySource: answer.source });
      response = await say(answer.content);
    }

    await gate(ctl);
    emit({
      phase: "prescreen",
      step: "prescreen",
      activity: "Pre-screening: triage rules, care routing, clinical summary",
    });
    await api.prescreen(caseId);
    await refresh();

    await gate(ctl);
    if (ctl.hold) {
      emit({
        phase: "review",
        step: "review",
        activity: "Held at the review gate — waiting for a clinician",
        awaitingReview: true,
      });
      while (!ctl.approved.has(profile.id) && !ctl.stopped) await sleep(200);
      if (ctl.stopped) throw new Stopped();
      emit({ awaitingReview: false });
    }
    emit({ phase: "review", step: "review", activity: "Recording the clinician decision" });
    await api.review(caseId, "approve", "simulated clinician");
    const reviewed = await refresh();

    await gate(ctl);
    emit({ phase: "consultation", step: "review", activity: "Recording consultation notes" });
    const reason =
      reviewed.facts.find((fact) => fact.kind === "reason_for_visit")?.value ??
      profile.reason;
    await api.addConsultationNote(caseId, {
      // Whoever care navigation picked; the default department's doctor is the
      // fallback for a case that somehow never got routed.
      doctor_id: reviewed.routing?.doctor_id ?? "dr_mehta",
      notes:
        `Simulated consultation (demo). Patient reports ${reason}. ` +
        `Pre-screening summary and triage priority ` +
        `${reviewed.triage?.priority ?? "unassigned"} reviewed with the patient.`,
      follow_up_instructions: "Follow up if symptoms change or do not improve.",
    });
    await refresh();

    await gate(ctl);
    emit({ phase: "final", step: "final", activity: "Assembling the final visit summary" });
    await api.finalize(caseId);
    await refresh();

    emit({
      phase: "done",
      step: null,
      activity: "Visit summary released",
      endedAt: Date.now(),
    });
  } catch (error) {
    if (error instanceof Stopped) {
      emit({ phase: "stopped", step: null, activity: "Stopped", endedAt: Date.now() });
      return;
    }
    const message = error instanceof Error ? error.message : String(error);
    emit({
      phase: "failed",
      step: null,
      activity: message,
      error: message,
      endedAt: Date.now(),
    });
  }
}

/* --- derived views -------------------------------------------------------- */

export const PHASE_LABEL: Record<SimPhase, string> = {
  queued: "Queued",
  intake: "Intake",
  prescreen: "Pre-screening",
  review: "Doctor review",
  consultation: "Consultation",
  final: "Final summary",
  done: "Completed",
  stopped: "Stopped",
  failed: "Failed",
};

export const isActive = (run: SimRun) =>
  !["queued", "done", "stopped", "failed"].includes(run.phase);

/** Wall-clock for a run — live while it is going, frozen once it ends. */
export const elapsed = (run: SimRun, now: number) =>
  run.startedAt === null ? null : (run.endedAt ?? now) - run.startedAt;

/**
 * The pipeline as this lane should draw it.
 *
 * Statuses come from the audit trail like everywhere else; the one thing added
 * is the step currently executing, which by definition has not been written to
 * the trail yet — the request making it happen is still in flight.
 */
export function laneRuns(run: SimRun): AgentRun[] {
  return run.runs.map((agent) =>
    agent.key === run.step && agent.status !== "completed"
      ? { ...agent, status: "running" as const }
      : agent,
  );
}
