import type { CaseDetail } from "@/lib/api";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/feedback";
import { Icons } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

export function TranscriptTab({ detail }: { detail: CaseDetail }) {
  const msgs = detail.transcript;
  return (
    <Card>
      <CardHeader title="Intake conversation" description="Verbatim record. Facts on the next tab point back to these turn numbers." />
      <CardBody>
        {!msgs.length ? (
          <EmptyState icon={<Icons.bot size={20} />} title="No conversation recorded" />
        ) : (
          <ol className="mx-auto max-w-2xl space-y-4">
            {msgs.map((m) => {
              const patient = m.role === "patient";
              return (
                <li key={m.turn_index} className={cn("flex gap-3", patient && "flex-row-reverse")}>
                  <span className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                    patient ? "bg-brand-soft text-brand" : "bg-sunken text-fg-muted",
                  )} aria-hidden="true">
                    {patient ? <Icons.user size={15} /> : <Icons.bot size={15} />}
                  </span>
                  <div className={cn("max-w-[80%] space-y-1", patient && "text-right")}>
                    <div className={cn(
                      "inline-block rounded-lg px-3.5 py-2.5 text-left text-sm leading-6",
                      patient ? "bg-brand text-brand-fg" : "border border-line bg-surface",
                    )}>
                      {m.content}
                    </div>
                    <p className="text-[11px] text-fg-subtle">{patient ? "Patient" : "Assistant"} · turn {m.turn_index}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </CardBody>
    </Card>
  );
}