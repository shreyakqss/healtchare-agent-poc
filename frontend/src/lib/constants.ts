import type { CaseStatus, Priority } from "@/lib/api/types";

export const STATUS_LABEL: Record<CaseStatus, string> = {
  CREATED: "New",
  INGESTING: "Intake in progress",
  ANALYZING: "Pre-screening",
  NEEDS_REVIEW: "Awaiting review",
  APPROVED: "Approved",
  COMPLETED: "Completed",
  REJECTED: "Rejected",
  FAILED: "Failed",
};

export const STATUS_ORDER: CaseStatus[] = [
  "CREATED", "INGESTING", "ANALYZING", "NEEDS_REVIEW", "APPROVED", "COMPLETED", "REJECTED", "FAILED",
];

export const PRIORITY_LABEL: Record<Priority, string> = { high: "High", medium: "Medium", low: "Low" };

export const FIELD_LABEL: Record<string, string> = {
  reason_for_visit: "Reason for visit",
  symptom: "Symptoms",
  duration: "Duration",
  name: "Name",
  age: "Age",
  gender: "Gender",
  history: "Medical history",
  medication: "Medications",
  allergy: "Allergies",
  contact_preference: "Contact preference",
  condition: "Condition",
};

export const ACTOR_LABEL: Record<string, string> = {
  "system:intake": "Intake assistant",
  "system:hms": "HMS connector",
  "system:record_processor": "Record processor",
  "system:urgency_evaluator": "Urgency evaluator",
  "system:care_navigator": "Care navigator",
  "system:summary_writer": "Summary writer",
  "system:visit_reporter": "Visit reporter",
  "system:task_agent": "Task agent",
  "system:prescreen": "Pre-screening workflow",
  "system:finalize": "Finalisation workflow",
  "system:seed": "Demo seed",
  patient: "Patient",
};

/** Mirrors backend `services/attachments.py::ATTACHMENT_KINDS`. */
export const ATTACHMENT_KINDS = [
  { id: "lab_report", label: "Lab report" },
  { id: "radiology", label: "Radiology report" },
  { id: "prescription", label: "Prescription" },
  { id: "referral", label: "Referral letter" },
  { id: "discharge_summary", label: "Discharge summary" },
  { id: "other", label: "Other document" },
] as const;

export function attachmentKindLabel(kind: string): string {
  return ATTACHMENT_KINDS.find((k) => k.id === kind)?.label ?? kind;
}