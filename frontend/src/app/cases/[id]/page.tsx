import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { shortId } from "@/lib/utils";
import { AppShell } from "@/components/layout/app-shell";
import { CaseView } from "@/features/case/case-view";

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const user = await requireRole("clinician", `/cases/${id}`);

  let detail;
  try {
    detail = await serverApi.clinician.case(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const audit = await serverApi.clinician.audit(id);

  const name = detail.demographics?.name || "Case";

  return (
    <AppShell
      title={name}
      subtitle={`Case ${shortId(id)}`}
      wide
      user={user}
      actions={
        <Link href="/doctor" className="hidden h-9 items-center rounded-md px-3 text-sm font-medium text-fg-muted hover:bg-sunken hover:text-fg sm:inline-flex">
          Back to queue
        </Link>
      }
    >
      <CaseView initialCase={detail} initialAudit={audit} />
    </AppShell>
  );
}
