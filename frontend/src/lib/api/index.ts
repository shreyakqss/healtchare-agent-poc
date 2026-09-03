import { API_ROOT, http, readCookie, readSse } from "@/lib/api/client";
import type {
  AppointmentRequestResult, AssistantReply, AssistantTurn, Attachment, AttachmentSkipResponse, AuditEvent, CaseDetail,
  CaseListItem, ConsultationNote, ConsultationNoteRequest, FinalizeRequest, HMSPractitioner, HMSStatus, HospitalConfig,
  HospitalSummary, IdentityFormRequest, IntakeConfig, LinkedPatientRecord, MessageResponse, PatientCase, PatientVisitItem,
  Review, ReviewRequest, Roster, SessionResponse, Slot, TurnEvent,
} from "@/lib/api/types";

export { ApiError } from "@/lib/api/client";
export type * from "@/lib/api/types";

export const intakeApi = {
  greeting: () => http.get<{ text: string }>("/intake-sessions/greeting"),
  linkedRecord: () => http.get<LinkedPatientRecord | null>("/intake-sessions/linked-record"),
  start: (body: Record<string, never> = {}) =>
    http.post<SessionResponse>("/intake-sessions", body),
  get: (sessionId: string) => http.get<SessionResponse>(`/intake-sessions/${sessionId}`),
  consent: (sessionId: string, granted: boolean) => http.post<SessionResponse>(`/intake-sessions/${sessionId}/consent`, { granted }),
  submitIdentity: (sessionId: string, payload: IdentityFormRequest) =>
    http.post<SessionResponse>(`/intake-sessions/${sessionId}/identity`, payload),
  send: (sessionId: string, content: string) => http.post<MessageResponse>(`/intake-sessions/${sessionId}/messages`, { content }),
  async *stream(sessionId: string, content: string, signal?: AbortSignal): AsyncGenerator<TurnEvent> {
    const csrf = readCookie("careflow_csrf");
    const res = await fetch(`${API_ROOT}/intake-sessions/${sessionId}/messages/stream`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(csrf ? { "x-csrf-token": csrf } : {}) },
      body: JSON.stringify({ content }),
      signal,
    });
    yield* readSse<TurnEvent>(res);
  },
};

export const casesApi = {
  list: () => http.get<CaseListItem[]>("/cases"),
  get: (caseId: string) => http.get<CaseDetail>(`/cases/${caseId}`),
  patientList: () => http.get<PatientVisitItem[]>("/cases/my-visits"),
  patientGet: (caseId: string) => http.get<PatientCase>(`/cases/${caseId}/patient-view`),
  selectSlot: (caseId: string, slotId: string) => http.post<PatientCase>(`/cases/${caseId}/appointment-slot`, { slot_id: slotId }),
  audit: (caseId: string) => http.get<AuditEvent[]>(`/cases/${caseId}/audit`),
  upload: (caseId: string, file: File, kind: string, uploadedBy = "patient") => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("uploaded_by", uploadedBy);
    return http.form<Attachment>(`/cases/${caseId}/attachments`, form);
  },
  fileUrl: (caseId: string, attachmentId: string) => `${API_ROOT}/cases/${caseId}/attachments/${attachmentId}/file`,
  skipAttachment: (caseId: string, kind: string, reason?: string) =>
    http.post<AttachmentSkipResponse>(`/cases/${caseId}/attachments/skip`, { kind, reason }),
  prescreen: (caseId: string) => http.post<CaseDetail>(`/cases/${caseId}/prescreen`),
  review: (caseId: string, body: ReviewRequest) => http.post<Review>(`/cases/${caseId}/review`, body),
  addNote: (caseId: string, body: ConsultationNoteRequest) => http.post<ConsultationNote>(`/cases/${caseId}/consultation-notes`, body),
  finalize: (caseId: string, body: FinalizeRequest) => http.post<CaseDetail>(`/cases/${caseId}/finalize`, body),
  assistantChat: (caseId: string, message: string, doctorContext: string, transcript: AssistantTurn[]) =>
    http.post<AssistantReply>(`/cases/${caseId}/assistant`, { message, doctor_context: doctorContext, transcript }),
};

export const hospitalApi = {
  intakeConfig: () => http.get<IntakeConfig>("/hospital/intake-config"),
  config: () => http.get<HospitalConfig & { hospital_id: string }>("/hospital/config"),
  roster: () => http.get<Roster>("/hospital/roster"),
  list: () => http.get<HospitalSummary[]>("/hospital/hospitals"),
  getJson: (id: string) => http.get<HospitalConfig>(`/hospital/hospitals/${id}/json`),
  saveJson: (id: string, cfg: HospitalConfig) => http.put<HospitalConfig>(`/hospital/hospitals/${id}/json`, cfg),
  getYaml: (id: string) => http.get<{ hospital_id: string; yaml: string }>(`/hospital/hospitals/${id}/yaml`),
  saveYaml: (id: string, yaml: string) => http.put<HospitalConfig>(`/hospital/hospitals/${id}/yaml`, { yaml }),
  create: (hospital_id: string, yaml?: string) => http.post<HospitalSummary>("/hospital/hospitals", { hospital_id, yaml }),
  activate: (id: string) => http.post<HospitalSummary>(`/hospital/hospitals/${id}/activate`),
  remove: (id: string) => http.del<void>(`/hospital/hospitals/${id}`),
  uploadLetterhead: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return http.form<HospitalSummary>(`/hospital/hospitals/${id}/letterhead`, form);
  },
  letterheadUrl: (id: string) => `${API_ROOT}/hospital/hospitals/${id}/letterhead/file`,
};

export const hmsApi = {
  status: () => http.get<HMSStatus>("/hms/status"),
  practitioners: () => http.get<HMSPractitioner[]>("/hms/practitioners"),
  slots: (departmentId: string, practitionerId?: string, limit = 5) =>
    http.get<Slot[]>(`/hms/slots?department_id=${departmentId}${practitionerId ? `&practitioner_id=${practitionerId}` : ""}&limit=${limit}`),
  requests: () => http.get<AppointmentRequestResult[]>("/hms/appointment-requests"),
};
