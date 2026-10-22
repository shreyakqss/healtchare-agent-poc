import type { ReactNode } from "react";
import type { CaseDetail, CaseStatus } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { Avatar, Steps } from "@/components/ui/data";
import { Badge, PriorityBadge, StatusBadge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { formatDateTime, titleCase } from "@/lib/utils";

const LIFECYCLE: CaseStatus[] = ["CREATED", "INGESTING", "ANALYZING", "NEEDS_REVIEW", "APPROVED", "COMPLETED"];
const STEP_LABELS = ["Created", "Intake", "Pre-screening", "Review", "Reviewed", "Completed"];

export function CaseHeader({ detail, action }: { detail: CaseDetail; action?: ReactNode }) {
  const d = detail.demographics ?? {};
  const name = d.name || "Unnamed patient";
  const who = [d.age ? `${d.age} y` : null, d.sex ? titleCase(d.sex) : null].filter(Boolean).join(" · ");
  const idx = LIFECYCLE.indexOf(detail.status);
  const terminalBad = detail.status === "REJECTED" || detail.status === "FAILED";

  return (
    <Card>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <Avatar name={name} size="lg" />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold leading-6">{name}</h2>
                <StatusBadge status={detail.status} />
                <PriorityBadge priority={detail.triage?.priority ?? null} />
                {detail.emergency_flagged_at ? (
                  <Badge tone="danger"><Icons.alert size={12} /> Emergency advice given</Badge>
                ) : null}
              </div>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-fg-muted">
                <span>{who || "Demographics not yet collected"}</span>
                {detail.hms_patient_id ? (
                  <Badge tone="info"><Icons.link size={12} /> {detail.hms_patient_id}</Badge>
                ) : null}
              </p>
              <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-subtle">
                <span>
                  {detail.routing ? (
                    <>
                      {detail.routing.department_name}
                      {detail.routing.doctor_name ? <> → {detail.routing.doctor_name}</> : null}
                    </>
                  ) : "Not yet routed"}
                </span>
                <span suppressHydrationWarning>Created {formatDateTime(detail.created_at)}</span>
                <span>Channel: {titleCase(detail.channel)}</span>
              </p>
            </div>
          </div>
          {action}
        </div>

        {terminalBad ? (
          <Alert tone="danger" title={detail.status === "REJECTED" ? "Visit rejected by the reviewing clinician" : "A workflow step failed"}>
            {detail.status === "REJECTED"
              ? "No patient-facing output is released. The audit trail records the decision."
              : "See the audit trail for the error. Pre-screening may be re-run from this state."}
          </Alert>
        ) : (
          <div className="overflow-x-auto scrollbar-thin">
            <Steps steps={STEP_LABELS} current={idx < 0 ? 0 : idx} />
          </div>
        )}
      </CardBody>
    </Card>
  );
}