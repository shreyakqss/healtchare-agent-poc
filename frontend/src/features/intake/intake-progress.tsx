import { FIELD_LABEL } from "@/lib/constants";
import { Icons } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

const NEXT_STEPS = [
  { title: "Answer a few questions", body: "The assistant asks only for what is still missing." },
  { title: "A clinician reviews", body: "Nothing is decided automatically." },
  { title: "You get your plan", body: "Department, doctor and next step, once approved." },
];

export function IntakeProgress({ requiredFields, missingFields, complete, fallbackMode }: {
  requiredFields: string[]; missingFields: string[] | null; complete: boolean; fallbackMode: boolean;
}) {
  const started = missingFields !== null;
  const done = requiredFields.filter((f) => started && !missingFields.includes(f)).length;

  return (
    <div className="space-y-6">
      <section aria-labelledby="progress-title">
        <div className="flex items-baseline justify-between">
          <h2 id="progress-title" className="text-sm font-semibold">Your intake</h2>
          {requiredFields.length ? <span className="tabular text-xs text-fg-muted">{done}/{requiredFields.length}</span> : null}
        </div>
        {requiredFields.length ? (
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-sunken" aria-hidden="true">
            <div className="h-full rounded-full bg-brand transition-[width] duration-300" style={{ width: `${(done / requiredFields.length) * 100}%` }} />
          </div>
        ) : null}
        <ul className="mt-3 space-y-1.5">
          {requiredFields.map((f) => {
            const ticked = started && !missingFields.includes(f);
            return (
              <li key={f} className="flex items-center gap-2.5 text-sm">
                <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full border", ticked ? "border-brand bg-brand text-brand-fg" : "border-line-strong text-transparent")} aria-hidden="true">
                  <Icons.check size={12} />
                </span>
                <span className={ticked ? "text-fg" : "text-fg-muted"}>{FIELD_LABEL[f] ?? f}</span>
                <span className="sr-only">{ticked ? ", collected" : ", still needed"}</span>
              </li>
            );
          })}
          {!requiredFields.length ? <li className="text-sm text-fg-muted">Checklist unavailable.</li> : null}
        </ul>
        {complete ? <p className="mt-3 text-xs text-success">All set. Your answers are with the care team.</p> : null}
      </section>

      <section aria-labelledby="next-title">
        <h2 id="next-title" className="text-sm font-semibold">What happens next</h2>
        <ol className="mt-3 space-y-3">
          {NEXT_STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sunken text-[11px] font-semibold text-fg-muted" aria-hidden="true">{i + 1}</span>
              <div>
                <p className="text-sm font-medium leading-6">{s.title}</p>
                <p className="text-xs leading-5 text-fg-muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {fallbackMode ? (
        <p className="flex items-start gap-2 text-xs leading-5 text-fg-subtle">
          <Icons.info size={14} className="mt-0.5 shrink-0" />
          The AI assistant is running in fallback mode, so questions are simpler than usual. Your answers are still recorded.
        </p>
      ) : null}
    </div>
  );
}