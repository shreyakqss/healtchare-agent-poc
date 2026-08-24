"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Tabs } from "@/components/ui/tabs";
import { Alert } from "@/components/ui/feedback";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { MessageList } from "@/features/intake/message-list";
import { Composer } from "@/features/intake/composer";
import { IntakeProgress } from "@/features/intake/intake-progress";
import { RecordLink } from "@/features/intake/record-link";
import { SamplePatientPicker } from "@/features/intake/sample-patient-picker";
import { DocumentsPanel } from "@/features/intake/documents-panel";
import { VisitsPanel } from "@/features/intake/visits-panel";
import { PatientResults } from "@/features/intake/patient-results";
import { useIntakeSession } from "@/features/intake/use-intake-session";

type Tab = "chat" | "documents" | "visits";

export function PatientPortal({ initialGreeting, initialRequiredFields, initialClinicName, initialApiOnline, initialLlmConfigured }: {
  initialGreeting: string; initialRequiredFields: string[]; initialClinicName: string; initialApiOnline: boolean; initialLlmConfigured: boolean;
}) {
  const [tab, setTab] = useState<Tab>("chat");
  const [consented, setConsented] = useState(false);
  const [checking, setChecking] = useState(false);
  const [prefill, setPrefill] = useState<{ text: string; key: number } | null>(null);
  const [composerKey, setComposerKey] = useState(0);
  const { state, send, retry, ensureSession, setLinkedPatient, refreshCase, clearError, quickStart } = useIntakeSession(initialGreeting);
  const started = state.sessionId !== null;

  async function checkUpdates() {
    setChecking(true);
    try { await refreshCase(); } finally { setChecking(false); }
  }

  return (
    <div className="mx-auto max-w-6xl">
      {!initialApiOnline ? (
        <Alert tone="danger" title="The clinic service is not reachable right now" className="mb-5">
          You can read this page, but the assistant cannot answer until the service is back.
        </Alert>
      ) : null}

      <Tabs<Tab> className="mb-6" value={tab} onChange={setTab}
        tabs={[{ id: "chat", label: "Conversation" }, { id: "documents", label: "Documents" }, { id: "visits", label: "My visits" }]} />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
        {/* Never unmounted: switching tabs only hides it, so the transcript and any in-flight stream survive. */}
        <section className={cn("min-w-0", tab !== "chat" && "hidden")} aria-label="Conversation with the intake assistant">
          <div className="mx-auto flex max-w-2xl flex-col gap-5">
            <header>
              <h2 className="text-xl font-semibold tracking-tight">Tell us what brings you in</h2>
              <p className="mt-1 text-sm text-fg-muted">{initialClinicName} · a clinician reviews everything before any decision is made.</p>
            </header>

            <SamplePatientPicker
              locked={started}
              onPrefill={(opening, record) => {
                if (record) setLinkedPatient(record);
                setPrefill({ text: opening, key: composerKey + 1 });
                setComposerKey((k) => k + 1);
              }}
              onQuickStart={quickStart}
            />

            <RecordLink linked={state.linkedPatient} onLink={setLinkedPatient} locked={started} />

            <div className="min-h-[40vh]">
              <MessageList messages={state.messages} typing={state.awaitingFirstToken} />
            </div>

            {state.error ? (
              <Alert tone="danger" title="The assistant could not answer">
                <p>{state.error}</p>
                <div className="mt-2 flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => void retry()} icon={<Icons.refresh size={14} />}>Try again</Button>
                  <Button size="sm" variant="ghost" onClick={clearError}>Dismiss</Button>
                </div>
              </Alert>
            ) : null}

            {state.complete ? (
              <div className="space-y-4">
                <div className="rounded-lg border border-line bg-surface p-5 shadow-card">
                  <div className="flex items-start gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-success-soft text-success" aria-hidden="true"><Icons.checkCircle size={18} /></span>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-base font-semibold">Your answers are with the care team</h3>
                      <p className="mt-1 text-sm leading-6 text-fg-muted">
                        A clinician will review them shortly. You can close this page (your visit is saved under “My visits”), or check back here for updates.
                      </p>
                      <div className="mt-3">
                        <Button size="sm" variant="secondary" loading={checking} icon={<Icons.refresh size={14} />} onClick={() => void checkUpdates()}>Check for updates</Button>
                      </div>
                    </div>
                  </div>
                </div>
                {state.lastCase ? <PatientResults detail={state.lastCase} /> : null}
              </div>
            ) : (
              <Composer key={composerKey} onSend={(t) => void send(t)} busy={state.sending} disabled={!initialApiOnline}
                requireConsent={!started} consented={consented} onConsentChange={setConsented} initialText={prefill?.text} />
            )}
          </div>
        </section>

        {tab === "documents" ? (
          <section className="min-w-0" aria-label="Documents">
            <div className="mx-auto max-w-2xl space-y-5">
              <header>
                <h2 className="text-xl font-semibold tracking-tight">Your documents</h2>
                <p className="mt-1 text-sm text-fg-muted">Optional. Add anything you would bring to the appointment.</p>
              </header>
              {!started ? <Alert tone="info">Uploading a document opens your intake and records your consent, the same as sending a first message.</Alert> : null}
              <DocumentsPanel ensureSession={ensureSession} />
            </div>
          </section>
        ) : null}

        {tab === "visits" ? (
          <section className="min-w-0" aria-label="My visits">
            <div className="mx-auto max-w-2xl space-y-5">
              <header>
                <h2 className="text-xl font-semibold tracking-tight">My visits</h2>
                <p className="mt-1 text-sm text-fg-muted">Your approved plan and visit summary appear here once the care team has signed off.</p>
              </header>
              <VisitsPanel currentCaseId={state.caseId} />
            </div>
          </section>
        ) : null}

        <aside className="lg:sticky lg:top-20 lg:self-start" aria-label="Intake progress">
          <div className="rounded-lg border border-line bg-surface p-5 shadow-card">
            <IntakeProgress requiredFields={initialRequiredFields} missingFields={state.missingFields} complete={state.complete}
              fallbackMode={initialApiOnline && !initialLlmConfigured} />
          </div>
        </aside>
      </div>
    </div>
  );
}