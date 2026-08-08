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

/**
 * One frame of a turn in progress. Mirrors `TurnEvent` in
 * backend/schemas/response.py.
 *
 * `token` is the reply arriving for the screen, `segment` is the same text cut
 * into speakable phrases, and `done` is the canonical turn — text and speech
 * come from one generation, never from two calls.
 */
export type TurnEvent =
  | { type: "token"; text: string }
  | { type: "segment"; index: number; text: string }
  | { type: "done"; response: MessageResponse }
  | { type: "error"; status: number; detail: string };

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
  demographics: Record<string, unknown>;
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
  hospital: { name?: string; id?: string; timezone?: string };
  hospital_id: string;
  departments: { id: string; name: string; default?: boolean }[];
  doctors: { id: string; name: string; department_id: string }[];
  appointment_types: { id: string; label: string; duration_minutes?: number }[];
  required_intake_fields: string[];
  triage_rules_version: string;
};

/** One configured clinic. `id` is the YAML file stem. */
export type HospitalSummary = {
  id: string;
  name: string;
  departments: number;
  doctors: number;
  rules: number;
  active: boolean;
};

/**
 * The whole hospital YAML, parsed — what the visual builder edits.
 *
 * Mirrors `backend/data/hospitals/*.yaml`. Unknown keys are preserved on save
 * because the builder edits this object in place rather than rebuilding it, so
 * a clinic can carry fields the UI does not yet expose.
 */
export type HospitalDoc = {
  hospital?: { id?: string; name?: string; timezone?: string; location?: string };
  appointment_types?: { id: string; label: string; duration_minutes?: number }[];
  departments?: { id: string; name: string; default?: boolean }[];
  doctors?: {
    id: string;
    name: string;
    department_id: string;
    specialty?: string;
    working_days?: string[];
  }[];
  specialty_map?: Record<string, string[]>;
  triage_rules?: {
    version?: string;
    rules?: TriageRuleDoc[];
  };
  priority_appointment_map?: Record<string, string>;
  required_intake_fields?: string[];
  [key: string]: unknown;
};

export type TriageRuleDoc = {
  code: string;
  priority: string;
  condition: {
    any_symptom?: string[];
    any_history?: string[];
    min_duration_days?: number;
    allergy_conflict?: boolean;
  };
  action?: string;
  explanation?: string;
  specialty_hint?: string;
};

/** Whether the local voice models are installed. Probed before offering voice. */
export type VoiceStatus = {
  available: boolean;
  detail: string | null;
  stt_model: string;
  tts_model: string;
  loaded?: { stt: boolean; tts: boolean };
};

export type TranscriptResponse = {
  transcript: string;
  stt_ms: number;
  model: string;
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

  /**
   * One patient turn, watched as it is written.
   *
   * `onEvent` fires per frame — tokens for the screen, segments for speech —
   * and the resolved value is the canonical turn, which is what should be
   * stored in component state. Read with `fetch` rather than `EventSource`
   * because this is a POST and carries a body.
   *
   * `channel` records how the patient produced the turn and is never branched
   * on: a transcribed turn takes exactly this path, which is also the path the
   * future patient simulator will use. The backend keeps a plain
   * `POST /messages` for callers with no use for a stream; nothing in this UI
   * is one, so there is no wrapper for it here.
   */
  streamMessage: async (
    sessionId: string,
    content: string,
    channel: "text" | "voice",
    onEvent: (event: TurnEvent) => void,
  ): Promise<MessageResponse> => {
    const response = await fetch(
      `${BASE}/intake-sessions/${sessionId}/messages/stream`,
      {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, channel }),
      },
    ).catch(() => {
      throw new ApiError(
        "Could not reach the backend. Is `uvicorn main:app --reload` running?",
        0,
      );
    });
    if (!response.ok || !response.body) {
      throw new ApiError(`The assistant could not be reached (${response.status}).`, response.status);
    }

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    let result: MessageResponse | null = null;

    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;

        // SSE frames are separated by a blank line. Keepalive comments start
        // with ":" and are skipped by only reading "data:" lines.
        let end = buffer.indexOf("\n\n");
        for (; end !== -1; end = buffer.indexOf("\n\n")) {
          const frame = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          const data = frame
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim())
            .join("");
          if (!data) continue;

          const event = JSON.parse(data) as TurnEvent;
          if (event.type === "error") throw new ApiError(event.detail, event.status);
          if (event.type === "done") result = event.response;
          onEvent(event);
        }
      }
    } finally {
      // Hanging up mid-stream tells the backend to stop generating.
      await reader.cancel().catch(() => {});
    }

    if (!result) {
      throw new ApiError("The assistant did not finish its reply.", 0);
    }
    return result;
  },

  voiceStatus: () => request<VoiceStatus>("/voice/status"),

  /** Speech -> text. The transcript is then sent through `streamMessage`. */
  transcribe: (audio: Blob, caseId: string) => {
    const form = new FormData();
    form.append("audio", audio, "turn.wav");
    form.append("case_id", caseId);
    return request<TranscriptResponse>("/voice/transcribe", {
      method: "POST",
      body: form,
    });
  },

  /**
   * Assistant text -> spoken WAV. Returns the audio, not JSON.
   *
   * `segment` is which phrase of a streamed reply this is; it is recorded on
   * the audit event so time-to-first-audio can be read back afterwards.
   */
  speech: async (text: string, caseId: string, segment?: number): Promise<Blob> => {
    const response = await fetch(`${BASE}/voice/speech`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, case_id: caseId, segment }),
    }).catch(() => {
      throw new ApiError("Could not reach the backend.", 0);
    });
    if (!response.ok) {
      let detail = `Speech synthesis failed (${response.status})`;
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        /* non-JSON error body; keep the generic message */
      }
      throw new ApiError(detail, response.status);
    }
    return response.blob();
  },

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

  listHospitals: () => request<HospitalSummary[]>("/hospital/hospitals"),

  hospitalYaml: (hospitalId: string) =>
    request<{ hospital_id: string; yaml_text: string }>(
      `/hospital/hospitals/${hospitalId}/yaml`,
    ),

  saveHospitalYaml: (hospitalId: string, yamlText: string) =>
    request<HospitalSummary>(`/hospital/hospitals/${hospitalId}/yaml`, {
      method: "PUT",
      body: JSON.stringify({ yaml_text: yamlText }),
    }),

  /** Structured view of a clinic's config — the visual builder's read model. */
  hospitalJson: (hospitalId: string) =>
    request<{ hospital_id: string; config: HospitalDoc }>(
      `/hospital/hospitals/${hospitalId}/json`,
    ),

  saveHospitalJson: (hospitalId: string, config: HospitalDoc) =>
    request<HospitalSummary>(`/hospital/hospitals/${hospitalId}/json`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),

  createHospital: (hospitalId: string) =>
    request<HospitalSummary>("/hospital/hospitals", {
      method: "POST",
      body: JSON.stringify({ hospital_id: hospitalId }),
    }),

  activateHospital: (hospitalId: string) =>
    request<HospitalSummary>(`/hospital/hospitals/${hospitalId}/activate`, {
      method: "POST",
    }),

  deleteHospital: (hospitalId: string) =>
    request<void>(`/hospital/hospitals/${hospitalId}`, { method: "DELETE" }),

  attachmentUrl: (caseId: string, attachmentId: string) =>
    `${BASE}/cases/${caseId}/attachments/${attachmentId}/file`,
};
