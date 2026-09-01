import { useState } from "react";
import { FIELD_LABEL } from "@/lib/constants";
import { Icons } from "@/components/ui/icons";
import { cn, progressWidth } from "@/lib/utils";

export function IntakeProgress({ requiredFields, missingFields, capturedFields, complete, fallbackMode }: {
  requiredFields: string[]; missingFields: string[] | null; capturedFields: Record<string, string[]>;
  complete: boolean; fallbackMode: boolean;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const started = missingFields !== null;
  const done = requiredFields.filter((f) => started && !missingFields.includes(f)).length;
  const anyCaptured = Object.keys(capturedFields).length > 0;

  function toggle(field: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(field)) next.delete(field); else next.add(field);
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="progress-title">
        <div className="flex items-baseline justify-between">
          <h2 id="progress-title" className="text-sm font-semibold">Your intake</h2>
          {requiredFields.length ? <span className="tabular text-xs text-fg-muted">{done}/{requiredFields.length}</span> : null}
        </div>
        {requiredFields.length ? (
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-sunken" aria-hidden="true">
            <div className={cn("h-full rounded-full bg-brand transition-[width] duration-300", progressWidth(done, requiredFields.length))} />
          </div>
        ) : null}
        <ul className="mt-3 space-y-1.5">
          {requiredFields.map((f) => {
            const ticked = started && !missingFields.includes(f);
            const values = capturedFields[f];
            const text = values?.length ? values.join(", ") : null;
            const isExpanded = expanded.has(f);
            return (
              <li key={f}>
                <div className="flex items-start gap-2.5 text-sm">
                  <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border", ticked ? "border-brand bg-brand text-brand-fg" : "border-line-strong text-transparent")} aria-hidden="true">
                    <Icons.check size={12} />
                  </span>
                  {text ? (
                    <button
                      type="button"
                      onClick={() => toggle(f)}
                      aria-expanded={isExpanded}
                      className="flex min-w-0 flex-1 items-center gap-1 text-left"
                    >
                      <span className={ticked ? "text-fg" : "text-fg-muted"}>{FIELD_LABEL[f] ?? f}</span>
                      <span className="sr-only">{ticked ? ", collected" : ", still needed"}</span>
                      <Icons.chevronRight
                        size={14}
                        className={cn("shrink-0 text-fg-subtle transition-transform", isExpanded && "rotate-90")}
                        aria-hidden="true"
                      />
                    </button>
                  ) : (
                    <span className="min-w-0">
                      <span className={ticked ? "text-fg" : "text-fg-muted"}>{FIELD_LABEL[f] ?? f}</span>
                      <span className="sr-only">{ticked ? ", collected" : ", still needed"}</span>
                    </span>
                  )}
                </div>
                {text && isExpanded ? (
                  <p title={text} className="ml-7 mt-0.5 truncate text-xs text-fg-subtle">{text}</p>
                ) : null}
              </li>
            );
          })}
          {!requiredFields.length ? <li className="text-sm text-fg-muted">Checklist unavailable.</li> : null}
        </ul>
        {complete ? <p className="mt-3 text-xs text-success">All set. Your answers are with the care team.</p> : null}
      </section>

      {anyCaptured ? (
        <p className="flex items-start gap-2 text-xs leading-5 text-fg-subtle">
          <Icons.info size={14} className="mt-0.5 shrink-0" />
          See something wrong above? Just tell me in the chat and I will fix it.
        </p>
      ) : null}

      {fallbackMode ? (
        <p className="flex items-start gap-2 text-xs leading-5 text-fg-subtle">
          <Icons.info size={14} className="mt-0.5 shrink-0" />
          The AI assistant is running in fallback mode, so questions are simpler than usual. Your answers are still recorded.
        </p>
      ) : null}
    </div>
  );
}
