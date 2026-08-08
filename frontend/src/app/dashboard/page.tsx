import { ApiError, api, type CaseListItem } from "@/lib/api";
import DashboardView from "./dashboard-view";

// Live case state — never prerendered.
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let cases: CaseListItem[] = [];
  let error: string | null = null;

  try {
    cases = await api.listCases();
  } catch (err) {
    error = err instanceof ApiError ? err.message : String(err);
  }

  return <DashboardView initialCases={cases} initialError={error} />;
}
