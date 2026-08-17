/**
 * Derives the agent-execution view from data the backend already records.
 *
 * There is no per-agent telemetry table: the durable trace is `AuditEvent`
 * rows plus the artefacts each agent wrote. So every run, status, artefact and
 * duration below is read back out of those, and anything the backend does not
 * record (the two intake agents write no audit row) is reported as unknown
 * rather than invented. Durations are the real elapsed time between one
 * pipeline event and the next, which on seeded rows is sub-millisecond.
 *
 * Only structured inputs, outputs, evidence ids and timings are surfaced —
 * never model reasoning.
 */

import type { AuditEvent, CaseDetail } from "./api";

export type RunStatus = "completed" | "running" | "waiting" | "failed" | "idle";

export type AgentRun = {
  key: string;
  name: string;
  /** One line on what the agent is responsible for. */
  role: string;
  /** Whether this step calls the language model at all. */
  engine: "llm" | "rules" | "deterministic" | "human";
  status: RunStatus;
  at: string | null;
  /** Real elapsed time since the previous recorded pipeline event, or null. */
  elapsedMs: number | null;
  inputs: string[];
  output: Record<string, unknown> | null;
  evidence: string[];
  note?: string;
};

type Meta = Pick<AgentRun, "key" | "name" | "role" | "engine">;

/** The pipeline as it actually runs in `workflow/graph.py`. */
export const PIPELINE: Meta[] = [
  {
    key: "intake",
    name: "Patient Intake",
    role: "Opens the session and records consent before anything is collected.",
    engine: "deterministic",
  },
  {
    key: "extractor",
    name: "Information Extractor",
    role: "Turns each patient message into typed facts, allergies and medications.",
    engine: "llm",
  },
  {
    key: "planner",
    name: "Question Planner",
    role: "Chooses the next question from the fields still missing.",
    engine: "llm",
  },
  {
    key: "records",
    name: "Medical Record Processor",
    role: "Stores uploads and extracts text. Never feeds triage.",
    engine: "deterministic",
  },
  {
    key: "prescreen",
    name: "AI Pre-Screening",
    role: "Applies the clinic's triage rules. No model is consulted.",
    engine: "rules",
  },
  {
    key: "navigator",
    name: "Care Navigator",
    role: "Maps symptoms to a department, doctor and appointment type.",
    engine: "deterministic",
  },
  {
    key: "summariser",
    name: "Clinical Summariser",
    role: "Writes the clinician-facing brief from recorded facts only.",
    engine: "llm",
  },
  {
    key: "review",
    name: "Human Review",
    role: "A clinician approves, edits or rejects. Nothing proceeds without it.",
    engine: "human",
  },
  {
    key: "final",
    name: "Final Summary",
    role: "Assembles the visit summary and a draft scheduling task.",
    engine: "llm",
  },
];

/** Audit action → the pipeline step that emitted it. */
const ACTION_STEP: Record<string, string> = {
  "intake.session_started": "intake",
  "intake.consent_recorded": "intake",
  "llm.response_streamed": "planner",
  "attachment.uploaded": "records",
  "triage.evaluated": "prescreen",
  "routing.recommended": "navigator",
  "summary.prescreening_generated": "summariser",
  "review.recorded": "review",
  "consultation.notes_recorded": "review",
  "visit.finalised": "final",
};

export const stepForAction = (action: string) => ACTION_STEP[action] ?? null;

const ordered = (audit: AuditEvent[]) =>
  [...audit].sort((a, b) => a.created_at.localeCompare(b.created_at));

/** Elapsed time from the previous audit row — the only timing that exists. */
function elapsedMap(audit: AuditEvent[]): Map<string, number> {
  const map = new Map<string, number>();
  const sorted = ordered(audit);
  sorted.forEach((event, index) => {
    if (index === 0) return;
    map.set(
      event.id,
      new Date(event.created_at).getTime() -
        new Date(sorted[index - 1].created_at).getTime(),
    );
  });
  return map;
}

/**
 * The per-case agent trace. `detail` supplies the artefacts each agent wrote;
 * `audit` supplies when it ran.
 */
export function buildPipeline(detail: CaseDetail, audit: AuditEvent[]): AgentRun[] {
  const sorted = ordered(audit);
  const elapsed = elapsedMap(audit);
  const last = (action: string) =>
    [...sorted].reverse().find((event) => event.action === action) ?? null;

  const status = detail.status;
  const patientTurns = detail.transcript.filter((turn) => turn.role === "patient");
  const consent = last("intake.consent_recorded");
  const triage = last("triage.evaluated");
  const routing = last("routing.recommended");
  const summary = last("summary.prescreening_generated");
  const review = last("review.recorded");
  const finalised = last("visit.finalised");
  const upload = last("attachment.uploaded");
  const streamed = last("llm.response_streamed");
  const streamedNum = (key: string) =>
    typeof streamed?.payload?.[key] === "number"
      ? (streamed.payload[key] as number)
      : null;

  const runs: Record<string, Partial<AgentRun>> = {
    intake: {
      status: consent ? "completed" : "running",
      at: consent?.created_at ?? null,
      elapsedMs: consent ? (elapsed.get(consent.id) ?? null) : null,
      inputs: ["patient:consent"],
      output: consent
        ? { consent_status: consent.payload.consent_status, session_id: detail.session_id }
        : null,
    },
    extractor: {
      // No audit row is written per extraction; the durable evidence is the
      // fact rows themselves, so runs are counted from patient turns.
      status: patientTurns.length ? "completed" : "idle",
      at: null,
      elapsedMs: null,
      inputs: [`transcript:${patientTurns.length} patient turns`],
      output: patientTurns.length
        ? {
            runs: patientTurns.length,
            facts_extracted: detail.facts.length,
            fact_kinds: [...new Set(detail.facts.map((f) => f.kind))],
            allergies_medications: detail.allergies_medications.length,
          }
        : null,
      evidence: detail.facts.slice(0, 6).map((f) => `fact:${f.kind}@turn${f.source_turn}`),
      note:
        "Extraction and planning run as one graph, so only their combined " +
        "duration is recorded (see intake.turn_processed in the timeline). " +
        "It is not split across the two rather than guessed at.",
    },
    planner: {
      status:
        detail.missing_fields.length === 0 && patientTurns.length
          ? "completed"
          : patientTurns.length
            ? "waiting"
            : "idle",
      at: streamed?.created_at ?? null,
      // The one agent the patient reads, so the one agent that streams — and
      // streaming is what gives it a measured duration of its own: the time
      // spent generating, from the first chunk to the last.
      elapsedMs: streamedNum("generation_ms"),
      inputs: ["transcript", "hospital:required_intake_fields"],
      output: patientTurns.length
        ? {
            runs: patientTurns.length,
            still_missing: detail.missing_fields,
            intake_complete: detail.missing_fields.length === 0,
            first_chunk_ms: streamedNum("ttft_ms"),
            chunks: streamedNum("chunks"),
            characters: streamedNum("characters"),
            speech_segments: streamedNum("speech_segments"),
          }
        : null,
      note:
        "Timings are for the last reply. Time to first chunk runs from the " +
        "start of the turn, so it includes extraction — that is the wait the " +
        "patient sits through. The extractor's own share of it is not " +
        "recorded, and is not guessed at.",
    },
    records: {
      status: detail.attachments.length ? "completed" : "idle",
      at: upload?.created_at ?? null,
      elapsedMs: upload ? (elapsed.get(upload.id) ?? null) : null,
      inputs: detail.attachments.map((a) => `upload:${a.filename}`),
      output: detail.attachments.length
        ? {
            stored: detail.attachments.length,
            text_extracted: detail.attachments.filter((a) => a.has_extracted_text).length,
            interpreted: 0,
          }
        : null,
      note: "Attachment content is deliberately withheld from triage.",
    },
    prescreen: {
      status: triage ? "completed" : status === "ANALYZING" ? "running" : "idle",
      at: triage?.created_at ?? null,
      elapsedMs: triage ? (elapsed.get(triage.id) ?? null) : null,
      inputs: ["facts", "allergies_medications", "hospital:triage_rules"],
      output: triage
        ? {
            priority: triage.payload.priority,
            engine: triage.payload.engine,
            rule_codes: triage.payload.rule_codes,
            warnings: triage.payload.warning_count,
          }
        : null,
      evidence: detail.triage?.rule_codes ?? [],
    },
    navigator: {
      status: routing ? "completed" : status === "ANALYZING" ? "running" : "idle",
      at: routing?.created_at ?? null,
      elapsedMs: routing ? (elapsed.get(routing.id) ?? null) : null,
      inputs: ["triage:priority", "hospital:specialty_map"],
      output: routing
        ? {
            department: detail.routing?.specialty ?? routing.payload.department_id,
            doctor: detail.routing?.doctor_name ?? routing.payload.doctor_id,
            appointment_type: routing.payload.appointment_type,
            matched_keywords: routing.payload.matched_keywords,
          }
        : null,
    },
    summariser: {
      status: summary ? "completed" : status === "ANALYZING" ? "running" : "idle",
      at: summary?.created_at ?? null,
      elapsedMs: summary ? (elapsed.get(summary.id) ?? null) : null,
      inputs: ["facts", "triage", "routing"],
      output: summary
        ? {
            sections: Object.keys(detail.prescreening_summary?.sections ?? {}),
            missing_information: detail.prescreening_summary?.missing_information ?? [],
          }
        : null,
      evidence: (detail.prescreening_summary?.evidence ?? [])
        .map((item) => item.rule_code ?? item.fact_kind ?? "")
        .filter(Boolean),
    },
    review: {
      status: review
        ? "completed"
        : status === "NEEDS_REVIEW"
          ? "waiting"
          : status === "REJECTED"
            ? "failed"
            : "idle",
      at: review?.created_at ?? null,
      elapsedMs: review ? (elapsed.get(review.id) ?? null) : null,
      inputs: ["prescreening_summary", "triage", "routing"],
      output: review
        ? {
            decision: review.payload.decision,
            reviewer: review.actor,
            edited_fields: review.payload.edited_fields,
            consultation_notes: detail.consultation_notes.length,
          }
        : null,
    },
    final: {
      status: finalised
        ? "completed"
        : status === "APPROVED"
          ? "waiting"
          : status === "FAILED"
            ? "failed"
            : "idle",
      at: finalised?.created_at ?? null,
      elapsedMs: finalised ? (elapsed.get(finalised.id) ?? null) : null,
      inputs: ["consultation_notes", "prescreening_summary"],
      output: finalised
        ? {
            sections: Object.keys(detail.final_summary?.sections ?? {}),
            draft_task: finalised.payload.draft_task,
            notes_read: finalised.payload.note_count,
          }
        : null,
    },
  };

  return PIPELINE.map((meta) => ({
    ...meta,
    status: "idle",
    at: null,
    elapsedMs: null,
    inputs: [],
    output: null,
    evidence: [],
    ...runs[meta.key],
  }));
}

/* --- execution timeline --------------------------------------------------- */

export type TimelineEntry = {
  id: string;
  at: string;
  offsetMs: number;
  deltaMs: number;
  label: string;
  actor: string;
  step: string | null;
  detail: string;
};

const ACTION_LABEL: Record<string, string> = {
  "intake.session_started": "Case created",
  "intake.consent_recorded": "Consent recorded",
  "intake.turn_processed": "Intake turn processed",
  "llm.response_streamed": "Assistant reply streamed",
  "attachment.uploaded": "Medical record ingested",
  "status.changed": "Status transition",
  "triage.evaluated": "Triage rules evaluated",
  "routing.recommended": "Care routing decided",
  "summary.prescreening_generated": "Pre-screening summary written",
  "review.recorded": "Clinician review recorded",
  "consultation.notes_recorded": "Consultation notes added",
  "visit.finalised": "Visit finalised",
  // Voice is an input channel, so its events sit in the same trail as the
  // agents they feed rather than in a log of their own.
  "voice.input_received": "Voice input received",
  "voice.transcribed": "Speech-to-text completed",
  "voice.stt_failed": "Speech-to-text failed",
  "voice.synthesised": "Text-to-speech completed",
  "voice.tts_failed": "Text-to-speech failed",
};

/** Audit rows as a trace: absolute time, offset from case start, and delta. */
export function timeline(audit: AuditEvent[]): TimelineEntry[] {
  const sorted = ordered(audit);
  const start = sorted.length ? new Date(sorted[0].created_at).getTime() : 0;
  return sorted.map((event, index) => {
    const at = new Date(event.created_at).getTime();
    return {
      id: event.id,
      at: event.created_at,
      offsetMs: at - start,
      deltaMs: index ? at - new Date(sorted[index - 1].created_at).getTime() : 0,
      label: ACTION_LABEL[event.action] ?? event.action,
      actor: event.actor,
      step: stepForAction(event.action),
      detail: summarisePayload(event),
    };
  });
}

function summarisePayload(event: AuditEvent): string {
  const payload = event.payload ?? {};
  const parts = Object.entries(payload)
    .filter(([, value]) => value !== null && value !== "" && !Array.isArray(value))
    .slice(0, 3)
    .map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`);
  return parts.join(" · ");
}
