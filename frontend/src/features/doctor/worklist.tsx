import type { CaseListItem } from "@/lib/api";
import type { Me } from "@/features/doctor/use-doctor";

export type Bucket = "review" | "consult" | "completed" | "other";

export function bucketOf(c: CaseListItem): Bucket {
  if (c.status === "NEEDS_REVIEW") return "review";
  if (c.status === "APPROVED") return "consult";
  if (c.status === "COMPLETED") return "completed";
  return "other";
}

export function isMine(c: CaseListItem, me: Me): boolean {
  return c.doctor_id === me.id || (c.department_id === me.department_id && !c.doctor_id);
}
