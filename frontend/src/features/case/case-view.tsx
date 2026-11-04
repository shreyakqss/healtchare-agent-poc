"use client";

import { useState } from "react";
import { casesApi, type CaseDetail, type HospitalIdentity } from "@/lib/api";
import { Tabs } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { useToast } from "@/components/ui/feedback";
import { CaseHeader } from "@/features/case/case-header";
import { OverviewTab } from "@/features/case/overview-tab";
import { TranscriptTab } from "@/features/case/transcript-tab";
import { RecordsTab } from "@/features/case/records-tab";
import { ReviewTab } from "@/features/case/review-tab";
import { DiagnosisTab } from "@/features/case/diagnosis-tab";
import type { Me } from "@/features/doctor/use-doctor";

type TabId = "overview" | "diagnosis" | "records" | "review" | "conversation";

export function CaseView({ initialCase, doctorContext, me, hospital }: {
  initialCase: CaseDetail; doctorContext: string; me: Me | null; hospital: HospitalIdentity | null;
}) {
  const [detail, setDetail] = useState(initialCase);
  const [tab, setTab] = useState<TabId>("overview");
  const [refreshing, setRefreshing] = useState(false);
  const toast = useToast();

  async function refresh() {
    setRefreshing(true);
    try {
      setDetail(await casesApi.get(detail.case_id));
    } catch (err) {
      toast.push({ tone: "danger", message: err instanceof Error ? err.message : "Could not refresh the case." });
    } finally {
      setRefreshing(false);
    }
  }

  const tabs: Array<{ id: TabId; label: string; count?: number }> = [
    { id: "overview", label: "Overview" },
    { id: "diagnosis", label: "AI Diagnosis", count: detail.ai_diagnosis ? (detail.ai_diagnosis.sections.differentials as unknown[] | undefined)?.length : undefined },
    // Only when the patient uploaded documents: otherwise the briefing already covers the facts.
    ...(detail.attachments.length ? [{ id: "records" as const, label: "Facts & records" }] : []),
    { id: "review", label: "Review & visit" },
    { id: "conversation", label: "Conversations" },
  ];

  return (
    <div className="space-y-5">
      <CaseHeader
        detail={detail}
        action={
          <Button variant="secondary" size="sm" onClick={refresh} loading={refreshing} icon={<Icons.refresh size={14} />}>
            Refresh
          </Button>
        }
      />

      <div className="-mx-4 overflow-x-auto px-4 scrollbar-thin sm:mx-0 sm:px-0">
        <Tabs idPrefix="case-detail" tabs={tabs} value={tab} onChange={setTab} className="min-w-max sm:min-w-0" />
      </div>

      <div
        id={`case-detail-panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`case-detail-tab-${tab}`}
        className="animate-in"
        key={tab}
      >
        {tab === "overview" && <OverviewTab detail={detail} />}
        {tab === "diagnosis" && <DiagnosisTab detail={detail} doctorContext={doctorContext} onChanged={(s) => setDetail({ ...detail, ai_diagnosis: s })} onOpenReport={() => setTab("review")} />}
        {tab === "records" && <RecordsTab detail={detail} />}
        {tab === "review" && <ReviewTab detail={detail} me={me} onChanged={refresh} hospital={hospital} />}
        {tab === "conversation" && <TranscriptTab detail={detail} />}
      </div>
    </div>
  );
}
