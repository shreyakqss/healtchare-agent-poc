import "server-only";

import { cookies } from "next/headers";
import { parseError, WORKSPACE_CASES } from "@/lib/api/client";
import type {
  Attachment,
  AuditEvent,
  ActiveIntake,
  CaseDetail,
  CaseListItem,
  Health,
  AdminDoctors,
  AdminPatientItem,
  WeeklyHours,
  HMSStatus,
  HospitalConfig,
  HospitalSummary,
  IntakeConfig,
  LinkedPatientRecord,
  PatientCase,
  PastPatientItem,
  PatientVisitItem,
  Roster,
} from "@/lib/api/types";

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");
const API_ROOT = `${BACKEND_URL}/api/v1/healthcare`;

export async function serverRequest<T>(path: string, root = API_ROOT): Promise<T> {
  const cookieStore = await cookies();
  const session = cookieStore.get("careflow_session")?.value;
  const response = await fetch(`${root}${path}`, {
    cache: "no-store",
    headers: session ? { Cookie: `careflow_session=${session}` } : undefined,
  });
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
}

export const backendRoot = BACKEND_URL;

export const serverApi = {
  health: () => serverRequest<Health>("/health", BACKEND_URL),
  patient: {
    config: () => serverRequest<IntakeConfig>("/hospital/intake-config"),
    greeting: () => serverRequest<{ text: string }>("/intake-sessions/greeting"),
    visits: () => serverRequest<PatientVisitItem[]>("/cases/my-visits"),
    activeIntake: () => serverRequest<ActiveIntake | null>("/intake-sessions/active"),
    pastAttachments: () => serverRequest<Attachment[]>("/intake-sessions/past-attachments"),
    linkedRecord: () => serverRequest<LinkedPatientRecord | null>("/intake-sessions/linked-record"),
    case: (id: string) => serverRequest<PatientCase>(`/cases/${encodeURIComponent(id)}/patient-view`),
  },
  clinician: {
    cases: () => serverRequest<CaseListItem[]>(`/cases?limit=${WORKSPACE_CASES}`),
    pastPatients: () => serverRequest<PastPatientItem[]>("/cases/past-patients"),
    case: (id: string) => serverRequest<CaseDetail>(`/cases/${encodeURIComponent(id)}`),
    audit: (id: string) => serverRequest<AuditEvent[]>(`/cases/${encodeURIComponent(id)}/audit`),
    config: () => serverRequest<HospitalConfig & { hospital_id: string }>("/hospital/config"),
    roster: () => serverRequest<Roster>("/hospital/roster"),
    myHours: () => serverRequest<WeeklyHours[]>("/hospital/my-hours"),
  },
  admin: {
    hospitals: () => serverRequest<HospitalSummary[]>("/hospital/hospitals"),
    config: () => serverRequest<HospitalConfig & { hospital_id: string }>("/hospital/config"),
    hms: () => serverRequest<HMSStatus>("/hms/status"),
    doctors: () => serverRequest<AdminDoctors>("/admin/doctors"),
    patients: () => serverRequest<AdminPatientItem[]>("/admin/patients"),
  },
};
