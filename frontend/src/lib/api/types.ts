/** Mirrors backend/app/schemas/responses.py. Keep in step by hand - there is no codegen. */

export type CaseStatus =
  | "CREATED" | "INGESTING" | "ANALYZING" | "NEEDS_REVIEW" | "APPROVED" | "COMPLETED" | "REJECTED" | "FAILED";
export type Priority = "high" | "medium" | "low";
export type ReviewDecision = "approve" | "edit" | "reject";

export interface AuthUser {
  user_id: string;
  subject: string;
  username: string | null;
  email: string | null;
  display_name: string | null;
  roles: Array<"patient" | "clinician" | "admin">;
  clinic_id: string | null;
  hms_username: string | null;
}

export interface LinkedPatientRecord {
  name: string;
  birth_date: string | null;
  gender: string;
  phone: string | null;
  email: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  contact_preference: string | null;
}

export interface SessionResponse {
  session_id: string;
  case_id: string;
  status: CaseStatus;
  consent_status: "PENDING" | "GRANTED" | "DECLINED";
  demographics: Record<string, string>;
  hms_linked: boolean;
  missing_fields: string[];
  captured_fields: Record<string, string[]>;
  required_attachment_kinds: string[];
  pending_attachment_kinds: string[];
  past_attachments: Attachment[];
}

export interface TranscriptMessage { role: "patient" | "assistant"; content: string; turn_index: number }

export interface IdentityFormRequest {
  name: string;
  birth_date: string;
  gender: string;
  phone?: string;
  email?: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  contact_preference: string;
}

export interface MessageResponse {
  session_id: string;
  case_id: string;
  turn_index: number;
  reply: string;
  asks_field: string | null;
  missing_fields: string[];
  intake_complete: boolean;
  transcript: TranscriptMessage[];
  captured_fields: Record<string, string[]>;
}

export type TurnEvent =
  | { type: "token"; text: string }
  | { type: "done"; response: MessageResponse }
  | { type: "error"; status: number; detail: string };

export interface AttachmentSkipResponse {
  ok: boolean;
}

/** Every clinician action carries the clinician's own HMS login; the backend verifies it per action. */
export interface ClinicianCredentials { username: string; password: string }

export interface ReviewRequest {
  decision: ReviewDecision; reviewer_username: string; reviewer_password: string;
  edits?: Record<string, string>; comment?: string;
}
export interface ConsultationNoteRequest {
  doctor_username: string; doctor_password: string; consultation_mode: "in_person" | "virtual";
  notes: string; prescription?: string; follow_up_instructions?: string;
  tests_ordered?: string; referral_notes?: string; patient_report?: string;
}
export interface FinalizeRequest { finalizer_username: string; finalizer_password: string }

export interface Fact { id: string; kind: string; value: string; source: "patient" | "hms"; source_turn: number; confidence: number }
export interface Entry { id: string; kind: "allergy" | "medication"; name: string; reaction_or_dose: string | null; source: "patient" | "hms"; source_turn: number }
export interface Attachment {
  id: string; case_id: string; kind: string; filename: string; mime_type: string; size_bytes: number;
  has_text: boolean; extracted_text: string | null; uploaded_by: string; created_at: string;
}
export interface TriageRuleRef { code: string; priority: Priority; action: string; explanation: string; version: string }
export interface Triage {
  priority: Priority; rule_codes: string[]; rules: TriageRuleRef[];
  warnings: Array<{ type: string; allergy?: string; medication?: string; message: string }>;
  evidence: Array<{ rule_code: string; matched_on: string; keyword?: string; text: string; fact_kind: string; days?: number; threshold_days?: number }>;
  created_at: string;
}
export interface Slot {
  id: string; practitioner_id: string; department_id: string; start: string; end: string;
  /** Another patient holds this time: shown greyed out, not pickable. Patient view only. */
  taken?: boolean;
  /** Whose time this is: the options span every doctor in the department. */
  doctor_name?: string | null;
}
export interface Routing {
  department_id: string; department_name: string; doctor_id: string | null; doctor_name: string | null;
  appointment_type_id: string; appointment_type_label: string; rationale: string; matched_keywords: string[];
  suggested_slot: Slot | null; slot_options: Slot[]; selected_slot_id: string | null;
}
export interface PatientRouting {
  department_id: string; department_name: string; doctor_id: string | null; doctor_name: string | null;
  appointment_type_id: string; appointment_type_label: string;
  suggested_slot: Slot | null; slot_options: Slot[]; selected_slot_id: string | null;
  /** The patient may pick which of the department's doctors to see. Off for urgent or approved
   * cases: then slot_options are already only the times they may pick. */
  doctor_choice?: boolean;
  /** The patient confirmed a doctor and time; until then the earliest is only suggested. */
  slot_confirmed?: boolean;
  slot_passed?: boolean;
  /** The doctor's weekly consulting hours, clinic-local; empty when the hospital publishes none. */
  doctor_hours?: WeeklyHours[];
  hours_by_doctor?: Record<string, WeeklyHours[]>;
}
/** Days (mon, tue, ...) sharing the same hours, e.g. times [["10:00", "13:00"], ["16:00", "19:00"]]. */
export interface WeeklyHours { days: string[]; times: [string, string][] }
export interface Summary {
  id: string; kind: "prescreening" | "final_visit"; sections: Record<string, unknown>;
  evidence: unknown[]; missing_information: string[]; generated_by: "llm" | "fallback"; created_at: string;
}
export interface Review { id: string; decision: ReviewDecision; reviewer_id: string; reviewer_role: string; edits: Record<string, string>; comment: string | null; created_at: string }
export interface ConsultationNote {
  id: string; doctor_id: string; doctor_name: string | null; consultation_mode: "in_person" | "virtual";
  notes: string; prescription: string | null; follow_up_instructions: string | null;
  tests_ordered: string | null; referral_notes: string | null;
  patient_report: string | null; created_at: string;
}
export interface CareTask { id: string; task_type: string; status: string; priority: Priority; payload: Record<string, unknown>; hms_reference: string | null; notes: string | null; created_at: string }
export interface Discrepancy {
  id: string; field_or_topic: string; patient_stated: string; document_says: string;
  source_kind: "document" | "hms"; attachment_id: string | null; severity: "info" | "review";
  requested_document_kind: string | null; generated_by: "llm" | "fallback" | "heuristic"; created_at: string;
}
export interface AuditEvent { id: string; actor: string; action: string; payload: Record<string, unknown>; created_at: string }

export interface CaseListItem {
  case_id: string; session_id: string; status: CaseStatus; priority: Priority | null;
  department_id: string | null; department_name: string | null; doctor_id: string | null; doctor_name: string | null;
  chief_complaint: string | null; demographics: Record<string, string>; hms_patient_id: string | null;
  review_decision: ReviewDecision | null; missing_count: number; appointment_start: string | null;
  created_at: string; updated_at: string | null;
  /** A red-flag rule matched: the patient was told to seek emergency care now. */
  emergency?: boolean;
}
export interface ActiveIntake extends SessionResponse {
  identity_complete: boolean;
  intake_complete: boolean;
  transcript: TranscriptMessage[];
  attachments: Attachment[];
  skipped_attachment_kinds: string[];
}

export interface PastVisitItem {
  case_id: string;
  visit_at: string;
  status: CaseStatus;
  review_decision: string | null;
  chief_complaint: string | null;
  department_name: string | null;
  doctor_id: string | null;
  doctor_name: string | null;
}

/** One patient on the doctor's "Past patients" list, their visits newest first. */
export interface PastPatientItem {
  patient_key: string;
  hms_patient_id: string | null;
  name: string | null;
  age: string | null;
  sex: string | null;
  last_visit_at: string;
  visit_count: number;
  visits: PastVisitItem[];
}

/** Admin > Patients: administrative facts only - no clinical field, never opens a case. */
export interface AdminPatientVisit {
  status: CaseStatus;
  department_name: string | null;
  doctor_name: string | null;
  appointment_start: string | null;
  appointment_booked: boolean;
  created_at: string;
}

export interface AdminPatientItem {
  hms_patient_id: string;
  name: string | null;
  age: string | null;
  sex: string | null;
  visit_count: number;
  visits: AdminPatientVisit[];
}

export interface PatientVisitItem {
  case_id: string; status: CaseStatus; review_decision: ReviewDecision | null;
  department_name: string | null; doctor_name: string | null;
  created_at: string; updated_at: string | null;
}

export interface AssistantTurn { role: "doctor" | "assistant"; content: string }
export interface AssistantReply { reply: string }

/** For a patient whose answers matched a red-flag rule: call an ambulance now. */
export interface EmergencyAdvice { ambulance_number: string; emergency_number: string; flagged_at: string }
export interface PatientCase {
  case_id: string; status: CaseStatus; review_decision: ReviewDecision | null;
  emergency?: EmergencyAdvice | null;
  routing: PatientRouting | null; final_summary: Record<string, unknown> | null;
  consultation_mode: "in_person" | "virtual" | null;
  appointment_reference: string | null; has_letterhead?: boolean; created_at: string;
}

export interface CaseDetail {
  case_id: string; session_id: string; status: CaseStatus; consent_status: string; channel: string; hospital_id: string;
  demographics: Record<string, string>; hms_patient_id: string | null; transcript: TranscriptMessage[];
  emergency_flagged_at?: string | null;
  facts: Fact[]; allergies_medications: Entry[]; attachments: Attachment[]; missing_fields: string[];
  required_attachment_kinds: string[]; pending_attachment_kinds: string[];
  triage: Triage | null; routing: Routing | null; discrepancies: Discrepancy[]; prescreening_summary: Summary | null; review: Review | null;
  consultation_notes: ConsultationNote[]; final_summary: Summary | null; care_tasks: CareTask[]; created_at: string;
}

/* Hospital configuration (mirrors data/hospitals/*.yaml) */
export interface Department { id: string; name: string; default?: boolean }
export interface Doctor { id: string; name: string; department_id: string; working_days?: string[]; username?: string | null }
export interface AppointmentType { id: string; label: string; duration_minutes?: number }
export interface TriageRuleConfig {
  code: string; priority: Priority;
  condition: { any_symptom?: string[]; all_symptoms?: string[]; any_history?: string[]; min_duration_days?: number; allergy_conflict?: boolean };
  action: string; explanation: string; specialty_hint?: string;
}
/** `/hospital/config` returns the clinic's own details from the hospital system's facility
 * record (`source: "hms"`), falling back to the YAML block (`source: "config"`). The admin
 * editor loads the raw YAML instead, so what it saves is never the overlaid copy. */
export interface HospitalIdentity {
  id: string;
  name: string;
  timezone?: string;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
  address?: HMSAddress | null;
  source?: "hms" | "config";
  has_letterhead?: boolean;
}

export interface HospitalConfig {
  hospital: HospitalIdentity;
  appointment_types: AppointmentType[];
  departments: Department[];
  doctors: Doctor[];
  specialty_map: Record<string, string[]>;
  triage_rules: { version: string; rules: TriageRuleConfig[] };
  priority_appointment_map: Record<Priority, string>;
  required_intake_fields: string[];
  required_attachment_kinds?: string[];
}
export interface IntakeConfig {
  hospital: Pick<HospitalIdentity, "id" | "name" | "timezone">;
  required_intake_fields: string[];
  required_attachment_kinds: string[];
  llm_configured: boolean;
}
export interface HospitalSummary { id: string; name: string; active: boolean; departments: number; doctors: number; rules: number; has_letterhead: boolean }

/** GET /hospital/roster - the doctors a case can be routed to (live HMS practitioners where known, YAML elsewhere). */
/** `username` is the clinician's hospital-system login. `id` is a practitioner record id and is
 * never a valid credential, so it must never be offered as one. Null for YAML-only doctors. */
export interface RosterDoctor { id: string; name: string; department_id: string; specialty: string | null; working_days: string[]; username: string | null }
export interface Roster { source: "hms" | "config"; doctors: RosterDoctor[] }

/* HMS */
export interface HMSAddress { line1: string; line2: string | null; city: string; state: string; postal_code: string; country: string }
export interface HMSPatient {
  mrn: string; name: string; age: number; sex: string; birth_date: string | null;
  phone: string | null; email: string | null; address: HMSAddress | null;
  contact_preference: string | null;
  conditions: string[]; medications: string[]; allergies: string[]; last_visit: string | null;
}
export interface HMSPractitioner { id: string; name: string; department_id: string; specialty: string | null; working_days: string[]; username: string | null }
export interface HMSStatus { provider: string; connected: boolean; patients: number; practitioners: number; pending_requests: number }
export interface HMSDocument { reference: string; title: string; content_type: string; created: string | null }
export interface AppointmentRequestResult { reference: string; status: string; slot: Slot | null }

export interface Health { status: string; version: string }

/* ---------- Admin > Doctors ---------- */
export interface AdminDoctor {
  id: number; practitioner_id: string; name: string; username: string; npi: string;
  specialty_code: string; specialty: string; department_id: string | null; active: boolean;
  /** null when the login system could not be asked. */
  has_login: boolean | null;
  hours: WeeklyHours[]; hours_until: string | null;
  /** Active and has hours to continue. */
  can_extend: boolean;
}
export interface DoctorRemovalCheck {
  doctor: { id: number; name: string; username: string; active: boolean };
  /** "delete" when the doctor was never used, else "deactivate" (history is kept). */
  mode: "delete" | "deactivate";
  blocked_by_open_cases: number;
  last_in_department: boolean;
  history: { encounters: number; forms: number; appointments: number; cases: number; notes: number };
}
export interface DoctorRemoval { result: "deleted" | "deactivated"; doctor: AdminDoctor | null }
export interface DoctorDepartmentOption {
  department_id: string; department_name: string; specialties: { code: string; title: string }[];
}
export interface AdminDoctors {
  clinic: { id: string; name: string; today: string }; doctors: AdminDoctor[]; departments: DoctorDepartmentOption[];
}
export interface NewDoctorRequest {
  title: string; first_name: string; last_name: string; email: string; phone: string;
  username: string; password: string; department_id: string; specialty_code: string; licence: string;
  days: string[]; ranges: [string, string][]; start_date: string; weeks: number;
}
/** Admin > Doctors > Edit. Name, NPI, username and department are fixed at onboarding and not part of it. */
export interface DoctorDetails {
  title: string; email: string; phone: string; licence: string; department_id: string | null; specialty_code: string;
}
export interface UpdateDoctorRequest { title: string; email: string; phone: string; licence: string; specialty_code: string }
export interface ChangeHoursRequest { days: string[]; ranges: [string, string][]; start_date: string; weeks: number }
export interface HoursChangePreview {
  problems: string[]; hours: WeeklyHours[]; hours_until: string | null;
  /** Clinic-local times patients already hold that the new hours leave out (their holds are kept). */
  held_outside: string[];
}
export interface DoctorPreview {
  problems: string[]; clinic: { id: string; name: string }; hours: WeeklyHours[]; blocks: number; hours_until: string | null;
}
