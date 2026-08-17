/**
 * Preview data, used only when the backend cannot be reached.
 *
 * The point is that the screens can be looked at — laid out, reviewed,
 * demonstrated — without Postgres, Ollama and uvicorn running. It is not a
 * mock layer and nothing routes through it when the API is up: each server
 * page tries the real call first and falls back here only on failure, setting
 * a `demo` flag that the views must display.
 *
 * **Two rules, both load-bearing:**
 *
 * 1. Every surface that renders this data says so, loudly and permanently.
 *    Invented patients in a clinical UI are dangerous precisely because they
 *    look exactly like real ones.
 * 2. Nothing can be written in preview mode. The views disable their actions
 *    rather than calling an API that is not there — a "saved" toast for a
 *    consultation that was never recorded would be worse than an error.
 *
 * Timestamps are fixed strings rather than computed from the clock: reading
 * the clock during render is what `react-hooks/purity` fails the build over,
 * and fixed values also keep server and client markup identical. The cost is
 * that relative times drift as the file ages, which is the right trade for
 * something only ever seen with the backend switched off.
 */

import type {
  CaseDetail,
  CaseListItem,
  ConsultationNote,
  HospitalConfig,
} from "./api";

/** Shown wherever preview data is rendered. Keep it short and unmissable. */
export const DEMO_NOTICE =
  "Preview data — the backend is offline. These patients are invented, and " +
  "nothing you do here is saved.";

export const DEMO_DEPARTMENTS: HospitalConfig["departments"] = [
  { id: "dept_general", name: "General Medicine", default: true },
  { id: "dept_cardio", name: "Cardiology" },
  { id: "dept_ortho", name: "Orthopaedics" },
];

export const DEMO_DOCTORS: HospitalConfig["doctors"] = [
  { id: "dr_rao", name: "Dr. Anita Rao", department_id: "dept_cardio" },
  { id: "dr_mehta", name: "Dr. Vikram Mehta", department_id: "dept_general" },
  { id: "dr_khan", name: "Dr. Sara Khan", department_id: "dept_ortho" },
];

export const DEMO_CONFIG: HospitalConfig = {
  hospital: { name: "Preview Clinic", id: "preview-clinic", timezone: "Asia/Kolkata" },
  hospital_id: "preview-clinic",
  departments: DEMO_DEPARTMENTS,
  doctors: DEMO_DOCTORS,
  appointment_types: [
    { id: "urgent_slot", label: "Urgent slot", duration_minutes: 20 },
    { id: "standard", label: "Standard", duration_minutes: 15 },
    { id: "teleconsult", label: "Teleconsultation", duration_minutes: 15 },
  ],
  required_intake_fields: [
    "reason_for_visit",
    "symptom",
    "duration",
    "name",
    "age",
    "gender",
    "history",
    "medication",
    "allergy",
    "contact_preference",
  ],
  triage_rules_version: "preview",
};

/* --- the five cases -------------------------------------------------------- */

type Seed = {
  id: string;
  session: string;
  name: string;
  age: number;
  sex: string;
  status: string;
  priority: string | null;
  department: string | null;
  doctor: string | null;
  complaint: string | null;
  created: string;
  updated: string | null;
};

/** One case per stage of the lifecycle, so every screen has something to show. */
const SEEDS: Seed[] = [
  {
    id: "aa11f2c4-0000-4000-8000-000000000001",
    session: "aa11f2c4-0000-4000-8000-0000000000s1",
    name: "Priya Nair",
    age: 51,
    sex: "female",
    status: "NEEDS_REVIEW",
    priority: "high",
    department: "Cardiology",
    doctor: "Dr. Anita Rao",
    complaint: "Chest tightness since this morning, worse on climbing stairs",
    created: "2026-08-12T08:14:00Z",
    updated: "2026-08-12T08:19:00Z",
  },
  {
    id: "aa11f2c4-0000-4000-8000-000000000002",
    session: "aa11f2c4-0000-4000-8000-0000000000s2",
    name: "Meera Iyer",
    age: 63,
    sex: "female",
    status: "APPROVED",
    priority: "medium",
    department: "General Medicine",
    doctor: "Dr. Vikram Mehta",
    complaint: "Persistent cough for three weeks, no fever",
    created: "2026-08-12T07:02:00Z",
    updated: "2026-08-12T07:41:00Z",
  },
  {
    id: "aa11f2c4-0000-4000-8000-000000000003",
    session: "aa11f2c4-0000-4000-8000-0000000000s3",
    name: "Arjun Desai",
    age: 34,
    sex: "male",
    status: "COMPLETED",
    priority: "low",
    department: "Orthopaedics",
    doctor: "Dr. Sara Khan",
    complaint: "Right ankle pain after a fall while running",
    created: "2026-08-11T15:20:00Z",
    updated: "2026-08-11T16:05:00Z",
  },
  {
    id: "aa11f2c4-0000-4000-8000-000000000004",
    session: "aa11f2c4-0000-4000-8000-0000000000s4",
    name: "Rohan Gupta",
    age: 28,
    sex: "male",
    status: "ANALYZING",
    priority: null,
    department: null,
    doctor: null,
    complaint: "Recurring headaches in the evenings",
    created: "2026-08-12T09:31:00Z",
    updated: "2026-08-12T09:32:00Z",
  },
  {
    id: "aa11f2c4-0000-4000-8000-000000000005",
    session: "aa11f2c4-0000-4000-8000-0000000000s5",
    name: "Fatima Sheikh",
    age: 45,
    sex: "female",
    status: "CREATED",
    priority: null,
    department: null,
    doctor: null,
    complaint: null,
    created: "2026-08-12T09:48:00Z",
    updated: null,
  },
];

export const DEMO_CASES: CaseListItem[] = SEEDS.map((seed) => ({
  case_id: seed.id,
  session_id: seed.session,
  status: seed.status,
  priority: seed.priority,
  department: seed.department,
  doctor_name: seed.doctor,
  chief_complaint: seed.complaint,
  demographics: { name: seed.name, age: seed.age, sex: seed.sex, preview: true },
  created_at: seed.created,
  updated_at: seed.updated,
}));

/* --- full detail per case -------------------------------------------------- */

const note = (
  id: string,
  doctorId: string,
  notes: string,
  prescription: string | null,
  followUp: string | null,
  mode: ConsultationNote["consultation_mode"],
  at: string,
): ConsultationNote => ({
  id,
  doctor_id: doctorId,
  notes,
  follow_up_instructions: followUp,
  consultation_mode: mode,
  prescription,
  created_at: at,
});

const DETAILS: Record<string, Partial<CaseDetail>> = {
  // High priority, waiting on a clinician. Nothing released.
  [SEEDS[0].id]: {
    transcript: [
      { role: "assistant", content: "What brings you in today?" },
      {
        role: "patient",
        content: "I've had a tight feeling in my chest since this morning.",
      },
      { role: "assistant", content: "Does anything make it worse?" },
      { role: "patient", content: "Climbing the stairs. I'm Priya Nair, 51, female." },
    ],
    facts: [
      { id: "f1", kind: "reason_for_visit", value: "Chest tightness", source_turn: 1, confidence: 0.9 },
      { id: "f2", kind: "symptom", value: "Tightness worse on exertion", source_turn: 3, confidence: 0.88 },
      { id: "f3", kind: "duration", value: "Since this morning", source_turn: 1, confidence: 0.9 },
      { id: "f4", kind: "name", value: "Priya Nair", source_turn: 3, confidence: 0.95 },
      { id: "f5", kind: "age", value: "51", source_turn: 3, confidence: 0.95 },
      { id: "f6", kind: "history", value: "Hypertension, diagnosed 2021", source_turn: 3, confidence: 0.8 },
    ],
    allergies_medications: [
      { id: "am1", kind: "medication", name: "Amlodipine 5 MG Oral Tablet", reaction_or_dose: "once daily", source_turn: 3 },
      { id: "am2", kind: "allergy", name: "Penicillin V", reaction_or_dose: "rash", source_turn: 3 },
    ],
    triage: {
      priority: "high",
      rule_ids: ["r1"],
      rule_codes: ["TR-HIGH-001"],
      warnings: [],
      evidence: [{ rule_code: "TR-HIGH-001", matched_on: "symptom", keyword: "chest" }],
    },
    routing: {
      specialty: "Cardiology",
      appointment_type: "urgent_slot",
      rationale: "Chest symptoms matched the cardiology keyword map.",
      department_id: "dept_cardio",
      doctor_id: "dr_rao",
      doctor_name: "Dr. Anita Rao",
    },
  },

  // Approved, awaiting the consultation itself.
  [SEEDS[1].id]: {
    transcript: [
      { role: "assistant", content: "What brings you in today?" },
      { role: "patient", content: "A cough that won't go away, about three weeks now." },
    ],
    facts: [
      { id: "f7", kind: "reason_for_visit", value: "Persistent cough", source_turn: 1, confidence: 0.92 },
      { id: "f8", kind: "duration", value: "3 weeks", source_turn: 1, confidence: 0.9 },
      { id: "f9", kind: "name", value: "Meera Iyer", source_turn: 1, confidence: 0.9 },
    ],
    allergies_medications: [
      { id: "am3", kind: "allergy", name: "Sulfa drugs", reaction_or_dose: "hives", source_turn: 1 },
    ],
    triage: {
      priority: "medium",
      rule_ids: ["r2"],
      rule_codes: ["TR-MED-004"],
      warnings: [],
      evidence: [{ rule_code: "TR-MED-004", fact_kind: "duration", days: 21, threshold_days: 14 }],
    },
    routing: {
      specialty: "General Medicine",
      appointment_type: "standard",
      rationale: "No specialty keyword matched; routed to the default department.",
      department_id: "dept_general",
      doctor_id: "dr_mehta",
      doctor_name: "Dr. Vikram Mehta",
    },
    review: {
      id: "rev2",
      decision: "approve",
      reviewer_role: "doctor:dr_mehta",
      edits: {},
      created_at: "2026-08-12T07:41:00Z",
    },
  },

  // The whole loop, finished — notes, a prescription, a released summary.
  [SEEDS[2].id]: {
    transcript: [
      { role: "assistant", content: "What brings you in today?" },
      { role: "patient", content: "I rolled my right ankle running yesterday." },
    ],
    facts: [
      { id: "f10", kind: "reason_for_visit", value: "Right ankle pain after a fall", source_turn: 1, confidence: 0.94 },
      { id: "f11", kind: "duration", value: "1 day", source_turn: 1, confidence: 0.9 },
      { id: "f12", kind: "name", value: "Arjun Desai", source_turn: 1, confidence: 0.93 },
    ],
    allergies_medications: [],
    triage: {
      priority: "low",
      rule_ids: ["r3"],
      rule_codes: ["TR-LOW-001"],
      warnings: [],
      evidence: [{ rule_code: "TR-LOW-001", matched_on: "fallback" }],
    },
    routing: {
      specialty: "Orthopaedics",
      appointment_type: "teleconsult",
      rationale: "Ankle injury matched the orthopaedics keyword map.",
      department_id: "dept_ortho",
      doctor_id: "dr_khan",
      doctor_name: "Dr. Sara Khan",
    },
    review: {
      id: "rev3",
      decision: "approve",
      reviewer_role: "doctor:dr_khan",
      edits: {},
      created_at: "2026-08-11T15:44:00Z",
    },
    consultation_notes: [
      note(
        "n1",
        "dr_khan",
        "Lateral ligament sprain, grade 1. No bony tenderness, weight-bearing " +
          "is possible. No imaging indicated at this stage.",
        "Ibuprofen 400 mg, three times daily with food, for five days.",
        "Return in ten days if it is not settling, or sooner if you cannot put weight on it.",
        "virtual",
        "2026-08-11T15:58:00Z",
      ),
    ],
    final_summary: {
      id: "sum3",
      kind: "final_visit",
      sections: {
        visit_reason: "Right ankle pain after a fall while running",
        consultation_overview:
          "Reviewed by teleconsultation. Examination findings were consistent " +
          "with a mild lateral ligament sprain.",
        doctor_notes_summary:
          "Rest, ice and elevation advised, with a short course of anti-inflammatories.",
        follow_up_instructions: [
          "Return in ten days if the pain is not settling.",
          "Come back sooner if you cannot put weight on the ankle.",
        ],
        administrative_notes: "",
        draft_care_task: { status: "draft", priority: "low" },
      },
      evidence: [],
      missing_information: [],
      created_at: "2026-08-11T16:05:00Z",
    },
  },

  // Mid-pipeline: the agents are still running, so there is nothing yet.
  [SEEDS[3].id]: {
    transcript: [
      { role: "assistant", content: "What brings you in today?" },
      { role: "patient", content: "Headaches most evenings for the past month." },
    ],
    facts: [
      { id: "f13", kind: "reason_for_visit", value: "Evening headaches", source_turn: 1, confidence: 0.9 },
      { id: "f14", kind: "name", value: "Rohan Gupta", source_turn: 1, confidence: 0.9 },
    ],
    missing_fields: ["allergy", "medication", "contact_preference"],
  },

  // Just opened. Consent recorded, nothing said yet.
  [SEEDS[4].id]: {
    transcript: [],
    facts: [],
    missing_fields: [
      "reason_for_visit",
      "symptom",
      "duration",
      "name",
      "age",
      "gender",
      "history",
      "medication",
      "allergy",
      "contact_preference",
    ],
  },
};

/** Every field `CaseDetail` requires, so a view can read it without guards. */
function detailFor(seed: Seed): CaseDetail {
  const extra = DETAILS[seed.id] ?? {};
  return {
    case_id: seed.id,
    session_id: seed.session,
    status: seed.status,
    consent_status: "GRANTED",
    demographics: { name: seed.name, age: seed.age, sex: seed.sex, preview: true },
    transcript: [],
    facts: [],
    allergies_medications: [],
    attachments: [],
    triage: null,
    routing: null,
    prescreening_summary: null,
    review: null,
    consultation_notes: [],
    final_summary: null,
    missing_fields: [],
    ...extra,
  };
}

export const DEMO_DETAILS: Record<string, CaseDetail> = Object.fromEntries(
  SEEDS.map((seed) => [seed.id, detailFor(seed)]),
);

/** The visits a preview "patient" has, newest first. */
export const DEMO_VISITS: CaseDetail[] = [
  DEMO_DETAILS[SEEDS[0].id],
  DEMO_DETAILS[SEEDS[2].id],
];
