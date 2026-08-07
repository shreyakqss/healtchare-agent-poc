/**
 * Thin typed wrapper over the backend API.
 *
 * Types mirror backend/schemas/response.py. If you change one, change both.
 */

const BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1/healthcare";

export type SessionResponse = {
  session_id: string;
  case_id: string;
  status: string;
  consent_status: string;
};

export type TranscriptTurn = { role: string; content: string };

export type MessageResponse = {
  session_id: string;
  case_id: string;
  turn_index: number;
  next_question: string;
  missing_fields: string[];
  intake_complete: boolean;
  transcript: TranscriptTurn[];
};

export type Attachment = {
  id: string;
  kind: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  has_extracted_text: boolean;
  interpreted: boolean;
  created_at: string;
};

export type Fact = {
  id: string;
  kind: string;
  value: string;
  source_turn: number;
  confidence: number;
};

export type AllergyMedication = {
  id: string;
  kind: string;
  name: string;
  reaction_or_dose: string | null;
  source_turn: number;
};

export type EvidenceItem = {
  rule_code?: string;
  matched_on?: string;
  keyword?: string;
  text?: string;
  fact_kind?: string;
  days?: number;
  threshold_days?: number;
};

export type Triage = {
  priority: string;
  rule_ids: string[];
  rule_codes: string[];
  warnings: { type?: string; message?: string }[];
  evidence: EvidenceItem[];
};

export type Routing = {
  specialty: string;
  appointment_type: string;
  rationale: string;
  department_id: string | null;
  doctor_id: string | null;
  doctor_name: string | null;
};

export type Summary = {
  id: string;
  kind: string;
  sections: Record<string, unknown>;
  evidence: EvidenceItem[];
  missing_information: string[];
  created_at: string;
};

export type Review = {
  id: string;
  decision: string;
  reviewer_role: string;
  edits: Record<string, unknown>;
  created_at: string;
};

export type ConsultationNote = {
  id: string;
  doctor_id: string;
  notes: string;
  follow_up_instructions: string | null;
  created_at: string;
};

export type CaseDetail = {
  case_id: string;
  session_id: string;
  status: string;
  consent_status: string;
  demographics: Record<string, unknown>;
  transcript: TranscriptTurn[];
  facts: Fact[];
  allergies_medications: AllergyMedication[];
  attachments: Attachment[];
  triage: Triage | null;
  routing: Routing | null;
  prescreening_summary: Summary | null;
  review: Review | null;
  consultation_notes: ConsultationNote[];
  final_summary: Summary | null;
  missing_fields: string[];
};

export type CaseListItem = {
  case_id: string;
  session_id: string;
  status: string;
  priority: string | null;
  department: string | null;
  doctor_name: string | null;
  chief_complaint: string | null;
  created_at: string;
  updated_at: string | null;
};

export type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type HospitalConfig = {
  hospital: { name?: string; id?: string };
  departments: { id: string; name: string }[];
  doctors: { id: string; name: string; department_id: string }[];
  appointment_types: { id: string; label: string }[];
  required_intake_fields: string[];
  triage_rules_version: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      // Every read here is live case state; nothing is safe to cache.
      cache: "no-store",
      headers: {
        ...(init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      "Could not reach the backend. Is `uvicorn main:app --reload` running?",
      0,
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body; keep the generic message */
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  startSession: (demographics: Record<string, unknown> = {}) =>
    request<SessionResponse>("/intake-sessions", {
      method: "POST",
      body: JSON.stringify({ demographics }),
    }),

  recordConsent: (sessionId: string, granted: boolean) =>
    request<SessionResponse>(`/intake-sessions/${sessionId}/consent`, {
      method: "POST",
      body: JSON.stringify({ granted }),
    }),

  sendMessage: (sessionId: string, content: string) =>
    request<MessageResponse>(`/intake-sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  uploadAttachment: (caseId: string, file: File, kind: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return request<Attachment>(`/cases/${caseId}/attachments`, {
      method: "POST",
      body: form,
    });
  },

  listCases: () => request<CaseListItem[]>("/cases"),
  getCase: (caseId: string) => request<CaseDetail>(`/cases/${caseId}`),

  prescreen: (caseId: string) =>
    request<CaseDetail>(`/cases/${caseId}/prescreen`, { method: "POST" }),

  review: (
    caseId: string,
    decision: "approve" | "edit" | "reject",
    reviewerRole: string,
    edits: Record<string, unknown> = {},
  ) =>
    request<Review>(`/cases/${caseId}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, reviewer_role: reviewerRole, edits }),
    }),

  addConsultationNote: (
    caseId: string,
    body: {
      doctor_id: string;
      notes: string;
      follow_up_instructions?: string | null;
    },
  ) =>
    request<ConsultationNote>(`/cases/${caseId}/consultation-notes`, {
      method: "POST",
      body: JSON.stringify({ ...body, attachment_ids: [] }),
    }),

  finalize: (caseId: string) =>
    request<CaseDetail>(`/cases/${caseId}/finalize`, { method: "POST" }),

  audit: (caseId: string) => request<AuditEvent[]>(`/cases/${caseId}/audit`),

  hospitalConfig: () => request<HospitalConfig>("/hospital/config"),

  attachmentUrl: (caseId: string, attachmentId: string) =>
    `${BASE}/cases/${caseId}/attachments/${attachmentId}/file`,
};

export const PRIORITY_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-800 ring-red-300 dark:bg-red-950 dark:text-red-200 dark:ring-red-800",
  medium:
    "bg-amber-100 text-amber-900 ring-amber-300 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-800",
  low: "bg-emerald-100 text-emerald-900 ring-emerald-300 dark:bg-emerald-950 dark:text-emerald-200 dark:ring-emerald-800",
};

export const STATUS_STYLES: Record<string, string> = {
  CREATED: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  INGESTING: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  ANALYZING: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
  NEEDS_REVIEW: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  APPROVED: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  COMPLETED: "bg-zinc-900 text-white dark:bg-zinc-200 dark:text-zinc-900",
  REJECTED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
};
