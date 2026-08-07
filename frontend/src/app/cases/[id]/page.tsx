import Link from "next/link";
import { ApiError, api, type AuditEvent, type CaseDetail } from "@/lib/api";
import CaseView from "./case-view";

// Live case state — never prerendered.
export const dynamic = "force-dynamic";

// `params` is a Promise in this Next.js version — await it before use.
export default async function CasePage({ params }: PageProps<"/cases/[id]">) {
  const { id } = await params;

  let detail: CaseDetail;
  let audit: AuditEvent[];
  try {
    [detail, audit] = await Promise.all([api.getCase(id), api.audit(id)]);
  } catch (err) {
    return (
      <div>
        <Link href="/dashboard" className="text-sm underline">
          ← Back to dashboard
        </Link>
        <p className="mt-6 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
          {err instanceof ApiError ? err.message : String(err)}
        </p>
      </div>
    );
  }

  return <CaseView caseId={id} initialDetail={detail} initialAudit={audit} />;
}
