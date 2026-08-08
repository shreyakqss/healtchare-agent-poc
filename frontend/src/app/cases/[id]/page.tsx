import Link from "next/link";
import { ApiError, api, type AuditEvent, type CaseDetail } from "@/lib/api";
import { Banner, icons } from "@/lib/ui";
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
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-xs text-faint hover:text-dim"
        >
          <icons.chevron className="rotate-180 text-[14px]" />
          Patient queue
        </Link>
        <div className="mt-6">
          <Banner tone="error">
            {err instanceof ApiError ? err.message : String(err)}
          </Banner>
        </div>
      </div>
    );
  }

  return <CaseView caseId={id} initialDetail={detail} initialAudit={audit} />;
}
