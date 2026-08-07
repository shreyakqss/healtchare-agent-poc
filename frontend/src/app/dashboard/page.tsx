import { ApiError, api, type CaseListItem } from "@/lib/api";
import CaseTable from "./case-table";

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

  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Staff dashboard</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Incoming patients, assigned department and doctor, and case progress.
        </p>
      </div>
      <CaseTable initialCases={cases} initialError={error} />
    </div>
  );
}
