/** Mirrors backend/app/schemas/responses.py. Keep in step by hand - there is no codegen. */

export type CaseStatus =
  | "CREATED" | "INGESTING" | "ANALYZING" | "NEEDS_REVIEW" | "APPROVED" | "COMPLETED" | "REJECTED" | "FAILED";
export type Priority = "high" | "medium" | "low";
export type ReviewDecision = "approve" | "edit" | "reject";

export interface SessionResponse {
  session_id: string;
  case_id: string;
  status: CaseStatus;
  consent_status: "PENDING" | "GRANTED" | "DECLINED";
  demographics: Record<string, string>;
  hms_linked: boolean;
  missing_fields: string[];
}

export interface TranscriptMessage { role: "patient" | "assistant"; content: string; turn_index: number }

export interface MessageResponse {
  session_id: string;
  case_id: string;
  turn_index: number;
  reply: string;
  asks_field: string | null;
  missing_fields: string[];
  intake_complete: boolean;
  transcript: TranscriptMessage[];
}

export type TurnEvent =
  | { type: "token"; text: string }
  | { type: "done"; response: MessageResponse }
  | { type: "error"; status: number; detail: string };

export interface Fact { id: string; kind: string; value: string; source: "patient" | "hms"; source_turn: number; confidence: number }
export interface Entry { id: string; kind: "allergy" | "medication"; name: string; reaction_or_dose: string | null; source: "patient" | "hms"; source_turn: number }
export interface Attachment {
  id: string; kind: string; filename: string; mime_type: string; size_bytes: number;
  has_text: boolean; extracted_text: string | null; uploaded_by: string; created_at: string;
}
export interface TriageRuleRef { code: string; priority: Priority; action: string; explanation: string; version: string }
export interface Triage {
  priority: Priority; rule_codes: string[]; rules: TriageRuleRef[];
  warnings: Array<{ type: string; allergy?: string; medication?: string; message: string }>;
  evidence: Array<{ rule_code: string; matched_on: string; keyword?: string; text: string; fact_kind: string; days?: number; threshold_days?: number }>;
  created_at: string;
}
export interface Slot { id: string; practitioner_id: string; department_id: string; start: string; end: string }
export interface Routing {
  department_id: string; department_name: string; doctor_id: string | null; doctor_name: string | null;
  appointment_type_id: string; appointment_type_label: string; rationale: string; matched_keywords: string[];
  suggested_slot: Slot | null;
}
export interface Summary {
  id: string; kind: "prescreening" | "final_visit"; sections: Record<string, unknown>;
  evidence: unknown[]; missing_information: string[]; generated_by: "llm" | "fallback"; created_at: string;
}
export interface Review { id: string; decision: ReviewDecision; reviewer_id: string; reviewer_role: string; edits: Record<string, string>; comment: string | null; created_at: string }
export interface ConsultationNote {
  id: string; doctor_id: string; doctor_name: string | null; consultation_mode: "in_person" | "virtual";
  notes: string; prescription: string | null; follow_up_instructions: string | null; created_at: string;
}
export interface CareTask { id: string; task_type: string; status: string; priority: Priority; payload: Record<string, unknown>; hms_reference: string | null; notes: string | null; created_at: string }
export interface AuditEvent { id: string; actor: string; action: string; payload: Record<string, unknown>; created_at: string }

export interface CaseListItem {
  case_id: string; session_id: string; status: CaseStatus; priority: Priority | null;
  department_id: string | null; department_name: string | null; doctor_id: string | null; doctor_name: string | null;
  chief_complaint: string | null; demographics: Record<string, string>; hms_patient_id: string | null;
  review_decision: ReviewDecision | null; missing_count: number; created_at: string; updated_at: string | null;
}

export interface CaseDetail {
  case_id: string; session_id: string; status: CaseStatus; consent_status: string; channel: string; hospital_id: string;
  demographics: Record<string, string>; hms_patient_id: string | null; transcript: TranscriptMessage[];
  facts: Fact[]; allergies_medications: Entry[]; attachments: Attachment[]; missing_fields: string[];
  triage: Triage | null; routing: Routing | null; prescreening_summary: Summary | null; review: Review | null;
  consultation_notes: ConsultationNote[]; final_summary: Summary | null; care_tasks: CareTask[]; created_at: string;
}

export interface ClinicOverview {
  total: number; by_status: Record<string, number>; by_priority: Record<string, number>;
  by_department: Record<string, number>; awaiting_review: number; completed_today: number;
}

/* Hospital configuration (mirrors data/hospitals/*.yaml) */
export interface Department { id: string; name: string; default?: boolean }
export interface Doctor { id: string; name: string; department_id: string; working_days?: string[] }
export interface AppointmentType { id: string; label: string; duration_minutes?: number }
export interface TriageRuleConfig {
  code: string; priority: Priority;
  condition: { any_symptom?: string[]; all_symptoms?: string[]; any_history?: string[]; min_duration_days?: number; allergy_conflict?: boolean };
  action: string; explanation: string; specialty_hint?: string;
}
export interface HospitalConfig {
  hospital: { id: string; name: string; timezone?: string };
  appointment_types: AppointmentType[];
  departments: Department[];
  doctors: Doctor[];
  specialty_map: Record<string, string[]>;
  triage_rules: { version: string; rules: TriageRuleConfig[] };
  priority_appointment_map: Record<Priority, string>;
  required_intake_fields: string[];
}
export interface HospitalSummary { id: string; name: string; active: boolean; departments: number; doctors: number; rules: number }

/* HMS */
export interface HMSPatient { mrn: string; name: string; age: number; sex: string; phone: string | null; conditions: string[]; medications: string[]; allergies: string[]; last_visit: string | null }
export interface HMSPractitioner { id: string; name: string; department_id: string; working_days: string[] }
export interface HMSStatus { provider: string; connected: boolean; patients: number; practitioners: number; pending_requests: number }
export interface AppointmentRequestResult { reference: string; status: string; slot: Slot | null }

export interface Health { status: string; version: string; hospital: string; llm: { configured: boolean; model: string }; hms: HMSStatus }