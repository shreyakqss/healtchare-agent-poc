import { API_ROOT, http, readSse } from "@/lib/api/client";
import type {
  AppointmentRequestResult, Attachment, AuditEvent, CaseDetail, CaseListItem, ClinicOverview, ConsultationNote,
  Health, HMSPatient, HMSPractitioner, HMSStatus, HospitalConfig, HospitalSummary, MessageResponse, Review,
  ReviewDecision, SessionResponse, Slot, TurnEvent,
} from "@/lib/api/types";

export { ApiError, safe } from "@/lib/api/client";
export type * from "@/lib/api/types";

export const intakeApi = {
  greeting: () => http.get<{ text: string }>("/intake-sessions/greeting"),
  start: (body: { mrn?: string; channel?: "web" | "kiosk" | "staff"; demographics?: Record<string, string> } = {}) =>
    http.post<SessionResponse>("/intake-sessions", body),
  /** Demo shortcut: fill a whole intake instantly and send it straight to pre-screening. */
  quickStart: (key: string) => http.post<SessionResponse>("/intake-sessions/quick-start", { key }),
  get: (sessionId: string) => http.get<SessionResponse>(`/intake-sessions/${sessionId}`),
  consent: (sessionId: string, granted: boolean) => http.post<SessionResponse>(`/intake-sessions/${sessionId}/consent`, { granted }),
  send: (sessionId: string, content: string) => http.post<MessageResponse>(`/intake-sessions/${sessionId}/messages`, { content }),
  async *stream(sessionId: string, content: string, signal?: AbortSignal): AsyncGenerator<TurnEvent> {
    const res = await fetch(`${API_ROOT}/intake-sessions/${sessionId}/messages/stream`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }), signal,
    });
    yield* readSse<TurnEvent>(res);
  },
};

export const casesApi = {
  list: () => http.get<CaseListItem[]>("/cases"),
  overview: () => http.get<ClinicOverview>("/cases/overview"),
  get: (caseId: string) => http.get<CaseDetail>(`/cases/${caseId}`),
  audit: (caseId: string) => http.get<AuditEvent[]>(`/cases/${caseId}/audit`),
  upload: (caseId: string, file: File, kind: string, uploadedBy = "patient") => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("uploaded_by", uploadedBy);
    return http.form<Attachment>(`/cases/${caseId}/attachments`, form);
  },
  fileUrl: (caseId: string, attachmentId: string) => `${API_ROOT}/cases/${caseId}/attachments/${attachmentId}/file`,
  prescreen: (caseId: string) => http.post<CaseDetail>(`/cases/${caseId}/prescreen`),
  review: (caseId: string, body: { decision: ReviewDecision; reviewer_id: string; reviewer_role?: string; edits?: Record<string, string>; comment?: string }) =>
    http.post<Review>(`/cases/${caseId}/review`, body),
  addNote: (caseId: string, body: { doctor_id: string; consultation_mode: "in_person" | "virtual"; notes: string; prescription?: string; follow_up_instructions?: string }) =>
    http.post<ConsultationNote>(`/cases/${caseId}/consultation-notes`, body),
  finalize: (caseId: string) => http.post<CaseDetail>(`/cases/${caseId}/finalize`),
};

export const hospitalApi = {
  config: () => http.get<HospitalConfig & { hospital_id: string }>("/hospital/config"),
  list: () => http.get<HospitalSummary[]>("/hospital/hospitals"),
  getJson: (id: string) => http.get<HospitalConfig>(`/hospital/hospitals/${id}/json`),
  saveJson: (id: string, cfg: HospitalConfig) => http.put<HospitalConfig>(`/hospital/hospitals/${id}/json`, cfg),
  getYaml: (id: string) => http.get<{ hospital_id: string; yaml: string }>(`/hospital/hospitals/${id}/yaml`),
  saveYaml: (id: string, yaml: string) => http.put<HospitalConfig>(`/hospital/hospitals/${id}/yaml`, { yaml }),
  create: (hospital_id: string, yaml?: string) => http.post<HospitalSummary>("/hospital/hospitals", { hospital_id, yaml }),
  activate: (id: string) => http.post<HospitalSummary>(`/hospital/hospitals/${id}/activate`),
  remove: (id: string) => http.del<void>(`/hospital/hospitals/${id}`),
};

export const hmsApi = {
  status: () => http.get<HMSStatus>("/hms/status"),
  searchPatients: (q: string) => http.get<HMSPatient[]>(`/hms/patients?q=${encodeURIComponent(q)}`),
  patient: (mrn: string) => http.get<HMSPatient>(`/hms/patients/${encodeURIComponent(mrn)}`),
  practitioners: () => http.get<HMSPractitioner[]>("/hms/practitioners"),
  slots: (departmentId: string, practitionerId?: string, limit = 5) =>
    http.get<Slot[]>(`/hms/slots?department_id=${departmentId}${practitionerId ? `&practitioner_id=${practitionerId}` : ""}&limit=${limit}`),
  requests: () => http.get<AppointmentRequestResult[]>("/hms/appointment-requests"),
};

export const healthApi = {
  get: async (): Promise<Health> => {
    const base = API_ROOT.replace(/\/api\/v1\/healthcare$/, "");
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    if (!res.ok) throw new Error("health failed");
    return (await res.json()) as Health;
  },
};