import type { CaseListItem, CaseStatus, Doctor, Priority } from "@/lib/api/types";

export const TERMINAL: CaseStatus[] = ["COMPLETED", "REJECTED"];
const PRIORITY_RANK: Record<Priority, number> = { high: 0, medium: 1, low: 2 };

export interface QueueFilters {
  search: string;
  status: CaseStatus | "";
  priority: Priority | "";
  department: string;
}

export const EMPTY_FILTERS: QueueFilters = { search: "", status: "", priority: "", department: "" };

export function patientName(c: CaseListItem): string {
  return c.demographics?.name?.trim() || "";
}

export function ageSex(c: CaseListItem): string {
  const parts = [c.demographics?.age, c.demographics?.sex].filter(Boolean);
  return parts.join(" · ");
}

export function isOpen(c: CaseListItem): boolean {
  return !TERMINAL.includes(c.status);
}

export function sortQueue(cases: CaseListItem[]): CaseListItem[] {
  return [...cases].sort((a, b) => {
    const ra = a.status === "NEEDS_REVIEW" ? 0 : 1;
    const rb = b.status === "NEEDS_REVIEW" ? 0 : 1;
    if (ra !== rb) return ra - rb;
    const pa = a.priority ? PRIORITY_RANK[a.priority] : 3;
    const pb = b.priority ? PRIORITY_RANK[b.priority] : 3;
    if (pa !== pb) return pa - pb;
    return (b.updated_at ?? b.created_at).localeCompare(a.updated_at ?? a.created_at);
  });
}

export function filterQueue(cases: CaseListItem[], f: QueueFilters): CaseListItem[] {
  const q = f.search.trim().toLowerCase();
  return cases.filter((c) => {
    if (f.status && c.status !== f.status) return false;
    if (f.priority && c.priority !== f.priority) return false;
    if (f.department && c.department_id !== f.department) return false;
    if (q) {
      const hay = [patientName(c), c.chief_complaint ?? "", c.hms_patient_id ?? ""].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export interface PatientGroup {
  key: string;
  name: string;
  mrn: string | null;
  cases: CaseListItem[];
}

/** Group by HMS id, then by stated name. Unnamed cases are never merged. */
export function groupPatients(cases: CaseListItem[]): PatientGroup[] {
  const map = new Map<string, PatientGroup>();
  for (const c of cases) {
    const name = patientName(c);
    const key = c.hms_patient_id ? `mrn:${c.hms_patient_id}` : name ? `name:${name.toLowerCase()}` : `case:${c.case_id}`;
    const g = map.get(key);
    if (g) {
      g.cases.push(c);
      if (!g.name && name) g.name = name;
    } else {
      map.set(key, { key, name, mrn: c.hms_patient_id, cases: [c] });
    }
  }
  return [...map.values()]
    .map((g) => ({ ...g, cases: [...g.cases].sort((a, b) => b.created_at.localeCompare(a.created_at)) }))
    .sort((a, b) => b.cases[0].created_at.localeCompare(a.cases[0].created_at));
}

export interface DoctorLoad {
  doctor: Doctor;
  open: number;
  awaiting: number;
  completed: number;
}

export function doctorLoads(doctors: Doctor[], cases: CaseListItem[]): DoctorLoad[] {
  return doctors.map((doctor) => {
    const mine = cases.filter((c) => c.doctor_id === doctor.id);
    return {
      doctor,
      open: mine.filter(isOpen).length,
      awaiting: mine.filter((c) => c.status === "NEEDS_REVIEW").length,
      completed: mine.filter((c) => c.status === "COMPLETED").length,
    };
  });
}

export function countHighOpen(cases: CaseListItem[]): number {
  return cases.filter((c) => c.priority === "high" && isOpen(c)).length;
}

export function countStatus(cases: CaseListItem[], status: CaseStatus): number {
  return cases.filter((c) => c.status === status).length;
}