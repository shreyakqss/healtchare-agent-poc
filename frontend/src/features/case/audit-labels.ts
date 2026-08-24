import type { AuditEvent } from "@/lib/api/types";
import { ACTOR_LABEL, STATUS_LABEL } from "@/lib/constants";
import type { CaseStatus } from "@/lib/api/types";

export function actorLabel(actor: string): string {
  if (ACTOR_LABEL[actor]) return ACTOR_LABEL[actor];
  const [role, id] = actor.split(":");
  if (role === "doctor" && id) return `Dr ${id.replace(/^dr_/, "").replace(/_/g, " ")}`;
  if (role === "staff" && id) return `Staff · ${id}`;
  if (role === "clinician" && id) return `Clinician · ${id}`;
  if (role === "system") return id ? id.replace(/_/g, " ") : "System";
  return actor;
}

export function isSystemActor(actor: string): boolean {
  return actor.startsWith("system:");
}

function s(v: unknown): string {
  return v === undefined || v === null ? "" : String(v);
}

function status(v: unknown): string {
  const key = s(v) as CaseStatus;
  return STATUS_LABEL[key] ?? key;
}

/** Readable one-liner for an audit row. Never invents values that are not in the payload. */
export function describeEvent(e: AuditEvent): string {
  const p = e.payload ?? {};
  switch (e.action) {
    case "intake.session_started":
      return `Intake session started${p.channel ? ` via ${s(p.channel)}` : ""}${p.hms_linked ? " · linked to hospital record" : ""}`;
    case "hms.record_linked":
      return `Hospital record ${s(p.mrn)} linked · ${s(p.conditions)} conditions, ${s(p.medications)} medications, ${s(p.allergies)} allergies imported`;
    case "consent.recorded":
      return p.granted ? "Consent granted" : "Consent declined";
    case "status.changed":
      return `Status ${status(p.from)} → ${status(p.to)}`;
    case "intake.turn_processed": {
      const ex = (p.extraction ?? {}) as Record<string, unknown>;
      const parts = [
        `Turn ${s(p.turn_index)} processed`,
        p.duration_ms !== undefined ? `${s(p.duration_ms)} ms` : null,
        p.planner ? `planner: ${s(p.planner)}` : null,
        ex.mode ? `extraction: ${s(ex.mode)}` : null,
        p.intake_complete ? "intake complete" : null,
      ].filter(Boolean);
      return parts.join(" · ");
    }
    case "intake.seeded":
      return `Demo intake seeded (${s(p.facts)} facts)`;
    case "attachment.uploaded":
      return `Uploaded ${s(p.filename)} (${s(p.kind).replace(/_/g, " ")})${p.text_extracted ? " · text extracted" : " · stored only"}`;
    case "records.processed":
      return `Records processed: ${s(p.documents)} documents, ${s(p.images)} images · not interpreted`;
    case "triage.evaluated":
      return `Priority ${s(p.priority)} set by rule ${(Array.isArray(p.rule_codes) ? p.rule_codes : []).join(", ")}${Number(p.warnings) > 0 ? ` · ${s(p.warnings)} warning(s)` : ""}`;
    case "routing.recommended":
      return `Routed to ${s(p.department_id).replace(/_/g, " ")}${p.doctor_id ? ` · ${s(p.doctor_id)}` : ""} · ${s(p.appointment_type).replace(/_/g, " ")} (${s(p.basis)})`;
    case "summary.prescreening_generated":
      return `Clinician briefing generated (${s(p.generated_by)})${p.missing_information ? ` · ${s(p.missing_information)} missing item(s)` : ""}`;
    case "review.recorded":
      return `Review recorded: ${s(p.decision)}${Array.isArray(p.edited_fields) && p.edited_fields.length ? ` · edited ${p.edited_fields.join(", ")}` : ""}`;
    case "consultation.recorded":
      return `Consultation recorded (${s(p.mode).replace(/_/g, " ")})`;
    case "summary.final_generated":
      return `Visit summary generated (${s(p.generated_by)})`;
    case "care_task.drafted":
      return `Care task drafted: ${s(p.task_type).replace(/_/g, " ")}${p.hms_reference ? ` · HMS ref ${s(p.hms_reference)}` : ""}`;
    case "workflow.failed":
      return `Workflow failed: ${s(p.error)}`;
    default:
      return e.action.replace(/[._]/g, " ");
  }
}