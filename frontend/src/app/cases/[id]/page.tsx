import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, casesApi, safe } from "@/lib/api";
import { shortId } from "@/lib/utils";
import { AppShell } from "@/components/layout/app-shell";
import { CaseView } from "@/features/case/case-view";

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let detail;
  try {
    detail = await casesApi.get(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const audit = await safe(casesApi.audit(id), []);

  const name = detail.demographics?.name || "Case";

  return (
    <AppShell
      title={name}
      subtitle={`Case ${shortId(id)}`}
      wide
      actions={
        <Link href="/clinic" className="hidden h-9 items-center rounded-md px-3 text-sm font-medium text-fg-muted hover:bg-sunken hover:text-fg sm:inline-flex">
          Back to queue
        </Link>
      }
    >
      <CaseView initialCase={detail} initialAudit={audit} />
    </AppShell>
  );
}