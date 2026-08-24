/** Derive the agent pipeline view from audit rows + case fields. Pure; nothing is invented. */

import type { AuditEvent, CaseDetail } from "@/lib/api/types";

export type StageStatus = "done" | "pending" | "skipped" | "failed";

export interface StageView {
  id: string;
  name: string;
  kind: "llm" | "rules" | "human" | "system";
  status: StageStatus;
  output: string | null;
  latencyMs: number | null; // gap from the previous audit event, when it exists
  detail?: string[];
}

function byAction(events: AuditEvent[], action: string): AuditEvent[] {
  return events.filter((e) => e.action === action);
}

function gapBefore(events: AuditEvent[], event: AuditEvent | undefined): number | null {
  if (!event) return null;
  const idx = events.findIndex((e) => e.id === event.id);
  if (idx <= 0) return null;
  return new Date(event.created_at).getTime() - new Date(events[idx - 1].created_at).getTime();
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function deriveStages(detail: CaseDetail, rawEvents: AuditEvent[]): StageView[] {
  const events = [...rawEvents].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const failed = byAction(events, "workflow.failed");

  // Intake assistant
  const turns = byAction(events, "intake.turn_processed");
  const durations = turns.map((t) => num(t.payload.duration_ms)).filter((d): d is number => d !== null);
  const planner = { llm: 0, fallback: 0, code: 0 };
  const extraction = { llm: 0, fallback: 0 };
  for (const t of turns) {
    const p = String(t.payload.planner ?? "");
    if (p === "llm" || p === "fallback" || p === "code") planner[p] += 1;
    const ex = (t.payload.extraction ?? {}) as Record<string, unknown>;
    const m = String(ex.mode ?? "");
    if (m === "llm" || m === "fallback") extraction[m] += 1;
  }
  const seeded = byAction(events, "intake.seeded").length > 0;
  const intake: StageView = {
    id: "intake",
    name: "Intake assistant",
    kind: "llm",
    status: turns.length || seeded ? "done" : detail.transcript.length ? "done" : "pending",
    output: turns.length
      ? `${turns.length} turn${turns.length === 1 ? "" : "s"} · ${detail.facts.length} facts recorded`
      : seeded
        ? `Seeded demo intake · ${detail.facts.length} facts`
        : null,
    latencyMs: durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null,
    detail: turns.length
      ? [
          `Planner: ${planner.llm} model, ${planner.fallback} fallback, ${planner.code} scripted`,
          `Extraction: ${extraction.llm} model, ${extraction.fallback} fallback`,
        ]
      : undefined,
  };

  // HMS connector
  const hms = byAction(events, "hms.record_linked")[0];
  const hmsStage: StageView = {
    id: "hms",
    name: "HMS connector",
    kind: "system",
    status: hms ? "done" : "skipped",
    output: hms
      ? `Record ${String(hms.payload.mrn)} · ${String(hms.payload.conditions)} conditions, ${String(hms.payload.medications)} medications, ${String(hms.payload.allergies)} allergies`
      : "No hospital record linked",
    latencyMs: gapBefore(events, hms),
  };

  // Record processor
  const rec = byAction(events, "records.processed")[0];
  const records: StageView = {
    id: "records",
    name: "Record processor",
    kind: "system",
    status: rec ? "done" : "pending",
    output: rec ? `${String(rec.payload.documents)} documents, ${String(rec.payload.images)} images · not interpreted` : null,
    latencyMs: gapBefore(events, rec),
  };

  // Urgency evaluator
  const tri = byAction(events, "triage.evaluated")[0];
  const urgency: StageView = {
    id: "urgency",
    name: "Urgency evaluator",
    kind: "rules",
    status: tri ? "done" : "pending",
    output: detail.triage
      ? `Priority ${detail.triage.priority} · ${detail.triage.rule_codes.join(", ")}${detail.triage.warnings.length ? ` · ${detail.triage.warnings.length} warning(s)` : ""}`
      : null,
    latencyMs: gapBefore(events, tri),
    detail: ["Rule engine only, zero model calls"],
  };

  // Care navigator
  const rou = byAction(events, "routing.recommended")[0];
  const navigator: StageView = {
    id: "navigator",
    name: "Care navigator",
    kind: "rules",
    status: rou ? "done" : "pending",
    output: detail.routing
      ? `${detail.routing.department_name}${detail.routing.doctor_name ? ` · ${detail.routing.doctor_name}` : ""} · ${detail.routing.appointment_type_label}`
      : null,
    latencyMs: gapBefore(events, rou),
    detail: rou ? [`Basis: ${String(rou.payload.basis ?? "–")}`] : undefined,
  };

  // Summary writer
  const sum = byAction(events, "summary.prescreening_generated")[0];
  const summary: StageView = {
    id: "summary",
    name: "Summary writer",
    kind: "llm",
    status: sum ? "done" : "pending",
    output: detail.prescreening_summary
      ? `Briefing ${detail.prescreening_summary.generated_by === "llm" ? "drafted by model" : "plain listing (fallback)"} · ${detail.prescreening_summary.missing_information.length} missing item(s)`
      : null,
    latencyMs: gapBefore(events, sum),
  };

  // Human review
  const review: StageView = {
    id: "review",
    name: "Human review",
    kind: "human",
    status: detail.review ? "done" : "pending",
    output: detail.review
      ? `${detail.review.decision} by ${detail.review.reviewer_id}${Object.keys(detail.review.edits).length ? ` · ${Object.keys(detail.review.edits).length} edit(s)` : ""}`
      : detail.status === "NEEDS_REVIEW"
        ? "Awaiting a clinician"
        : null,
    latencyMs: null, // human time is not a system latency
  };

  // Visit reporter
  const fin = byAction(events, "summary.final_generated")[0];
  const reporter: StageView = {
    id: "reporter",
    name: "Visit reporter",
    kind: "llm",
    status: fin ? "done" : detail.review?.decision === "reject" ? "skipped" : "pending",
    output: detail.final_summary
      ? `Visit summary ${detail.final_summary.generated_by === "llm" ? "drafted by model" : "assembled from notes (fallback)"}`
      : detail.review?.decision === "reject" ? "Case rejected" : null,
    latencyMs: gapBefore(events, fin),
  };

  // Task agent
  const task = byAction(events, "care_task.drafted")[0];
  const taskStage: StageView = {
    id: "task",
    name: "Task agent",
    kind: "system",
    status: task ? "done" : detail.review?.decision === "reject" ? "skipped" : "pending",
    output: detail.care_tasks.length
      ? `${detail.care_tasks[0].task_type.replace(/_/g, " ")} · draft${detail.care_tasks[0].hms_reference ? ` · HMS ${detail.care_tasks[0].hms_reference}` : ""}`
      : null,
    latencyMs: gapBefore(events, task),
  };

  const stages = [intake, hmsStage, records, urgency, navigator, summary, review, reporter, taskStage];

  if (failed.length) {
    const last = failed[failed.length - 1];
    const firstPending = stages.find((s) => s.status === "pending");
    if (firstPending) {
      firstPending.status = "failed";
      firstPending.output = String(last.payload.error ?? "Workflow failed");
    }
  }
  return stages;
}

export function formatLatency(ms: number | null): string {
  if (ms === null) return "not recorded";
  if (ms < 1) return "<1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}