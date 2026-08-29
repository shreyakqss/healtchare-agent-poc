"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Tabs } from "@/components/ui/tabs";
import { Alert } from "@/components/ui/feedback";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { IntakeForm } from "@/features/intake/intake-form";
import { IntakeProgress } from "@/features/intake/intake-progress";
import { DocumentsPanel } from "@/features/intake/documents-panel";
import { VisitsPanel } from "@/features/intake/visits-panel";
import { PatientResults } from "@/features/intake/patient-results";
import { Composer } from "@/features/intake/composer";
import { DocumentPrompt } from "@/features/intake/document-prompt";
import { MessageList } from "@/features/intake/message-list";
import { useIntakeSession } from "@/features/intake/use-intake-session";
import type { ActiveIntake, PatientVisitItem } from "@/lib/api";

type Tab = "chat" | "documents" | "visits";

export function PatientPortal({
  initialRequiredFields, initialRequiredAttachmentKinds, initialApiOnline, initialLlmConfigured, initialGreeting,
  initialVisits, initialActiveIntake,
}: {
  initialRequiredFields: string[]; initialRequiredAttachmentKinds: string[];
  initialApiOnline: boolean; initialLlmConfigured: boolean; initialGreeting: string; initialVisits: PatientVisitItem[];
  initialActiveIntake: ActiveIntake | null;
}) {
  const [tab, setTab] = useState<Tab>("chat");
  const [checking, setChecking] = useState(false);
  const [documentsDismissed, setDocumentsDismissed] = useState(false);
  const { state, submitIdentity, send, retry, refreshCase, clearError, uploadDocument, skipDocument } =
    useIntakeSession(initialGreeting, initialActiveIntake);
  // A required kind is resolved by a file or by a logged skip - same rule the backend applies.
  const uploadedKinds = new Set(state.attachments.map((a) => a.kind));
  const pendingKinds = initialRequiredAttachmentKinds.filter(
    (k) => !uploadedKinds.has(k) && !(k in state.skippedKinds),
  );
  const showDocumentPrompt = !documentsDismissed && pendingKinds.length > 0;

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

      <Tabs<Tab> idPrefix="patient-portal" className="sticky top-14 z-20 mb-6 bg-canvas" value={tab} onChange={setTab}
        tabs={[{ id: "chat", label: "Intake form" }, { id: "documents", label: "Documents" }, { id: "visits", label: "My visits" }]} />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_260px]">
        <section
          id="patient-portal-panel-chat"
          role="tabpanel"
          aria-labelledby="patient-portal-tab-chat"
          className={cn("min-w-0", tab !== "chat" && "hidden")}
        >
          <div className="mx-auto flex max-w-2xl flex-col gap-5">
            {!state.identityComplete ? null : (
              <div className="flex h-[min(42rem,calc(100dvh-10rem))] min-h-96 flex-col overflow-hidden rounded-lg border border-line bg-sunken shadow-card">
                <div className="border-b border-line bg-surface px-4 py-3 sm:px-5">
                  <h3 className="text-sm font-semibold">Conversation</h3>
                  <p className="text-xs text-fg-muted">Scroll here to review your messages.</p>
                </div>
                <MessageList messages={state.messages} typing={state.awaitingFirstToken} />
                {!state.complete ? (
                  <div className="shrink-0 border-t border-line bg-surface p-3 sm:p-4">
                    {/* The documents the clinic asked for: shown up front rather than behind a
                        toggle, and dismissible. Attaching anything else is the composer's
                        paperclip, next to Send. */}
                    {showDocumentPrompt ? (
                      <div className="mb-3">
                        <DocumentPrompt
                          pendingKinds={pendingKinds}
                          onUpload={(file, kind) => void uploadDocument(file, kind)}
                          onSkip={(kind, reason) => void skipDocument(kind, reason)}
                          onHide={() => setDocumentsDismissed(true)}
                          busy={state.uploading}
                          disabled={!initialApiOnline}
                        />
                      </div>
                    ) : null}
                    <Composer
                      onSend={(t) => void send(t)}
                      busy={state.sending}
                      disabled={!initialApiOnline}
                      requireConsent={false}
                      consented
                      onConsentChange={() => undefined}
                      onAttach={(file, kind) => void uploadDocument(file, kind)}
                      uploading={state.uploading}
                    />
                  </div>
                ) : null}
              </div>
            )}

            {state.error ? (
              <Alert tone="danger" title={state.identityComplete ? "The assistant could not answer" : "Could not save your details"}>
                <p>{state.error}</p>
                <div className="mt-2 flex gap-2">
                  {state.identityComplete ? (
                    <Button size="sm" variant="secondary" onClick={() => void retry()} icon={<Icons.refresh size={14} />}>Try again</Button>
                  ) : null}
                  <Button size="sm" variant="ghost" onClick={clearError}>Dismiss</Button>
                </div>
              </Alert>
            ) : null}

            {state.complete ? (
              <div className="space-y-4">
                {pendingKinds.length > 0 ? (
                  <Alert tone="warning" title="One more step before the care team can start">
                    <p>Your answers are saved, but the clinic still needs the documents below (or a reason they are not available). Pre-screening starts as soon as each one is attached or skipped.</p>
                    <div className="mt-3">
                      <DocumentPrompt
                        pendingKinds={pendingKinds}
                        onUpload={(file, kind) => void uploadDocument(file, kind).then(() => refreshCase())}
                        onSkip={(kind, reason) => void skipDocument(kind, reason).then(() => refreshCase())}
                        onHide={() => undefined}
                        busy={state.uploading}
                        disabled={!initialApiOnline}
                      />
                    </div>
                  </Alert>
                ) : null}
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
            ) : !state.identityComplete ? (
              <IntakeForm
                onSubmit={(values) => void submitIdentity(values)}
                busy={state.submittingIdentity}
                disabled={!initialApiOnline}
              />
            ) : null}
          </div>
        </section>

        <section
          id="patient-portal-panel-documents"
          role="tabpanel"
          aria-labelledby="patient-portal-tab-documents"
          className={cn("min-w-0", tab !== "documents" && "hidden")}
        >
          <div className="mx-auto max-w-2xl space-y-5">
            <header>
              <h2 className="text-xl font-semibold tracking-tight">Your documents</h2>
              <p className="mt-1 text-sm text-fg-muted">
                Documents added during this visit and shared with your care team.
              </p>
            </header>
            <DocumentsPanel
              attachments={state.attachments}
              skippedKinds={state.skippedKinds}
            />
          </div>
        </section>

        <section
          id="patient-portal-panel-visits"
          role="tabpanel"
          aria-labelledby="patient-portal-tab-visits"
          className={cn("min-w-0", tab !== "visits" && "hidden")}
        >
          <div className="mx-auto max-w-2xl space-y-5">
            <header>
              <h2 className="text-xl font-semibold tracking-tight">My visits</h2>
              <p className="mt-1 text-sm text-fg-muted">Your approved plan and visit summary appear here once the care team has signed off.</p>
            </header>
            <VisitsPanel currentCaseId={state.caseId} initialVisits={initialVisits} />
          </div>
        </section>

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
