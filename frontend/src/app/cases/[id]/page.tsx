import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { serverApi } from "@/lib/api/server";
import { shortId } from "@/lib/utils";
import { AppShell } from "@/components/layout/app-shell";
import { CaseView } from "@/features/case/case-view";
import { resolveMe } from "@/features/doctor/use-doctor";

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
  const [audit, config, roster] = await Promise.all([
    serverApi.clinician.audit(id),
    serverApi.clinician.config().catch(() => null),
    serverApi.clinician.roster().catch(() => null),
  ]);
  // Best-effort: the roster/config calls above never block the case page if they fail.
  const me = resolveMe(user.hms_username, roster?.doctors ?? [], config?.departments ?? []);
  const specialty = roster?.doctors.find((d) => d.id === me?.id)?.specialty;
  const doctorContext = me
    ? `${me.name}${specialty ? `, ${specialty}` : ""} - ${me.department_name}`
    : (user.display_name ?? "Doctor");

  const name = detail.demographics?.name || "Visit";

  return (
    <AppShell
      title={name}
      subtitle={`Visit ${shortId(id)}`}
      wide
      user={user}
      actions={
        <Link href="/doctor" className="hidden h-9 items-center rounded-md px-3 text-sm font-medium text-fg-muted hover:bg-sunken hover:text-fg sm:inline-flex">
          Back to queue
        </Link>
      }
    >
      <CaseView initialCase={detail} initialAudit={audit} doctorContext={doctorContext} me={me} hospital={config?.hospital ?? null} />
    </AppShell>
  );
}
