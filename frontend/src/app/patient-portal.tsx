"use client";

import { useState } from "react";
import { ApiError, api, type CaseDetail, type VoiceStatus } from "@/lib/api";
import { DEMO_NOTICE, DEMO_VISITS } from "@/lib/demo";
import { rememberCase, rememberedCases } from "@/lib/patient-history";
import { DemoBanner, Dot, icons } from "@/lib/ui";
import PatientChat from "./patient-chat";
import PatientRecords from "./patient-records";
import PatientResults from "./patient-results";

/**
 * The patient's whole surface: a sidebar and three screens.
 *
 * | Tab | What it is |
 * |---|---|
 * | Chat | a live conversation, open on arrival — no start step |
 * | My records | past visits, uploaded documents, stated medicines/allergies |
 * | My results | what a clinician has written or approved |
 *
 * **The chat is never unmounted.** Switching tabs mid-conversation would
 * otherwise throw away the transcript, the streaming reply and the session id,
 * so it is hidden with a class instead. The other two are cheap and are
 * mounted on demand.
 *
 * **Nothing fetches on mount.** The React Compiler's `set-state-in-effect`
 * rule fails the build on fetch-on-mount, and it is the right rule here
 * anyway: the visit list is loaded by the click that opens the tab needing it,
 * which is also when it is most likely to be current.
 */

type Tab = "chat" | "records" | "results";

const TABS: { key: Tab; label: string; hint: string; Icon: (typeof icons)["users"] }[] = [
  {
    key: "chat",
    label: "Chat",
    hint: "Talk to the assistant",
    Icon: icons.stethoscope,
  },
  {
    key: "records",
    label: "My records",
    hint: "Visits and documents",
    Icon: icons.file,
  },
  {
    key: "results",
    label: "My results",
    hint: "From your clinician",
    Icon: icons.heart,
  },
];

export default function PatientPortal({
  clinicName,
  voice,
}: {
  clinicName: string;
  /** Null when the backend could not be reached; voice is then simply absent. */
  voice: VoiceStatus | null;
}) {
  const [tab, setTab] = useState<Tab>("chat");
  /** Null until a tab that needs it has been opened at least once. */
  const [visits, setVisits] = useState<CaseDetail[] | null>(null);
  const [visitsBusy, setVisitsBusy] = useState(false);
  const [visitsError, setVisitsError] = useState<string | null>(null);
  /** Bumped when the live chat opens a visit, so the sidebar count follows. */
  const [liveCase, setLiveCase] = useState<string | null>(null);
  /** True once a load has failed outright and preview visits are on screen. */
  const [demo, setDemo] = useState(false);

  /**
   * Load the full detail of every visit this browser remembers.
   *
   * One request per visit because there is no batch endpoint; the list is a
   * handful of cases for one person, so that is fine. A visit that fails to
   * load is dropped rather than failing the screen — a deleted or reseeded
   * case should not hide the others.
   */
  async function loadVisits() {
    setVisitsBusy(true);
    setVisitsError(null);
    try {
      const remembered = rememberedCases();
      if (remembered.length === 0) {
        // Nothing on this device and no backend to ask: show the preview
        // visits so the screens can be looked at, clearly labelled.
        const reachable = await api.listCases().then(
          () => true,
          () => false,
        );
        if (reachable) {
          setVisits([]);
          setDemo(false);
        } else {
          setVisits(DEMO_VISITS);
          setDemo(true);
        }
        return;
      }
      const settled = await Promise.allSettled(
        remembered.map((entry) => api.getCase(entry.caseId)),
      );
      const loaded = settled
        .filter(
          (result): result is PromiseFulfilledResult<CaseDetail> =>
            result.status === "fulfilled",
        )
        .map((result) => result.value);
      if (loaded.length === 0) {
        setVisits(DEMO_VISITS);
        setDemo(true);
        return;
      }
      setVisits(loaded);
      setDemo(false);
    } catch (err) {
      setVisitsError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setVisitsBusy(false);
    }
  }

  /** Open a tab, loading what it needs the first time it is asked for. */
  function open(next: Tab) {
    setTab(next);
    if (next !== "chat" && visits === null) void loadVisits();
  }

  // Only once the list is actually loaded. Guessing from the one open visit
  // would show "1" to someone who has five, which is worse than no badge.
  const visitCount = visits?.length ?? null;

  return (
    <div className="grid items-stretch gap-5 lg:h-[calc(100vh-10rem)] lg:grid-cols-[15rem_minmax(0,1fr)]">
      {/* --- sidebar ------------------------------------------------------ */}
      <aside className="flex flex-col gap-4 lg:min-h-0 lg:overflow-y-auto">
        <div className="rounded-md border border-line bg-surface/80 p-4">
          <p className="eyebrow">{clinicName}</p>
          <p className="mt-1 text-sm font-semibold tracking-tight text-text">
            Your care
          </p>
          <p className="mt-1.5 text-[11px] leading-4 text-faint">
            Everything you tell us is read by a clinician before anything
            happens.
          </p>
        </div>

        <nav className="rounded-md border border-line bg-surface/80 p-1.5">
          <ul className="space-y-0.5">
            {TABS.map(({ key, label, hint, Icon }) => {
              const active = tab === key;
              return (
                <li key={key}>
                  <button
                    onClick={() => open(key)}
                    aria-current={active ? "page" : undefined}
                    className={`flex w-full items-center gap-3 rounded px-3 py-2.5 text-left transition-colors ${
                      active
                        ? "bg-accent/10 text-text"
                        : "text-dim hover:bg-raised/60 hover:text-text"
                    }`}
                  >
                    <Icon
                      className={`shrink-0 text-[17px] ${
                        active ? "text-accent" : "text-faint"
                      }`}
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {label}
                      </span>
                      <span className="block truncate text-[11px] text-faint">
                        {hint}
                      </span>
                    </span>
                    {key !== "chat" && visitCount !== null && visitCount > 0 && (
                      <span className="nums ml-auto rounded bg-raised px-1.5 py-0.5 text-[10px] text-dim">
                        {visitCount}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="rounded-md border border-line bg-surface/80 p-4">
          <p className="eyebrow flex items-center gap-1.5">
            <icons.shield className="text-[13px]" />
            What this is
          </p>
          <ul className="mt-2 space-y-2 text-[11px] leading-4 text-faint">
            <li>It organises what you say. It does not diagnose you.</li>
            <li>A clinician reviews everything before any next step.</li>
            <li>You can decline any question and stop at any time.</li>
          </ul>
          {liveCase && (
            <p className="mt-3 flex items-center gap-2 border-t border-line-soft pt-3 text-[11px] text-dim">
              <Dot tone="info" live />
              A visit is open
            </p>
          )}
        </div>
      </aside>

      {/* --- screen -------------------------------------------------------
          The chat stays mounted so a conversation survives a tab switch. */}
      <div className="min-h-0 lg:overflow-y-auto">
        <div className={tab === "chat" ? "h-full" : "hidden"}>
          <PatientChat
            voice={voice}
            onSessionStarted={(caseId, sessionId) => {
              setLiveCase(caseId);
              rememberCase({
                caseId,
                sessionId,
                startedAt: new Date().toISOString(),
              });
              // Anything already loaded is now stale by one visit.
              setVisits(null);
            }}
            onSubmitted={() => setVisits(null)}
          />
        </div>

        {tab === "records" && (
          <div className="space-y-5">
            {demo && <DemoBanner>{DEMO_NOTICE}</DemoBanner>}
            <PatientRecords
              visits={visits}
              busy={visitsBusy}
              error={visitsError}
              readOnly={demo}
              onRefresh={() => void loadVisits()}
            />
          </div>
        )}

        {tab === "results" && (
          <div className="space-y-5">
            {demo && <DemoBanner>{DEMO_NOTICE}</DemoBanner>}
            <PatientResults
              visits={visits}
              busy={visitsBusy}
              error={visitsError}
              onRefresh={() => void loadVisits()}
            />
          </div>
        )}
      </div>
    </div>
  );
}
