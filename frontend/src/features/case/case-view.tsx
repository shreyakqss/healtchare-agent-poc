"use client";

import { useState } from "react";
import { casesApi, type AuditEvent, type CaseDetail } from "@/lib/api";
import { Tabs } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Icons } from "@/components/ui/icons";
import { useToast } from "@/components/ui/feedback";
import { CaseHeader } from "@/features/case/case-header";
import { OverviewTab } from "@/features/case/overview-tab";
import { TranscriptTab } from "@/features/case/transcript-tab";
import { RecordsTab } from "@/features/case/records-tab";
import { ReviewTab } from "@/features/case/review-tab";
import { AuditTab } from "@/features/case/audit-tab";
import { TraceTab } from "@/features/case/trace-tab";

type TabId = "overview" | "conversation" | "records" | "review" | "audit" | "trace";

export function CaseView({ initialCase, initialAudit }: { initialCase: CaseDetail; initialAudit: AuditEvent[] }) {
  const [detail, setDetail] = useState(initialCase);
  const [audit, setAudit] = useState(initialAudit);
  const [tab, setTab] = useState<TabId>("overview");
  const [refreshing, setRefreshing] = useState(false);
  const toast = useToast();

  async function refresh() {
    setRefreshing(true);
    try {
      const [d, a] = await Promise.all([casesApi.get(detail.case_id), casesApi.audit(detail.case_id)]);
      setDetail(d);
      setAudit(a);
    } catch (err) {
      toast.push({ tone: "danger", message: err instanceof Error ? err.message : "Could not refresh the case." });
    } finally {
      setRefreshing(false);
    }
  }

  const tabs: Array<{ id: TabId; label: string; count?: number }> = [
    { id: "overview", label: "Overview" },
    { id: "conversation", label: "Conversation", count: detail.transcript.length },
    { id: "records", label: "Facts & records", count: detail.facts.length + detail.allergies_medications.length + detail.attachments.length },
    { id: "review", label: "Review & visit" },
    { id: "audit", label: "Audit trail", count: audit.length },
    { id: "trace", label: "Agent trace" },
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
        {tab === "conversation" && <TranscriptTab detail={detail} />}
        {tab === "records" && <RecordsTab detail={detail} />}
        {tab === "review" && <ReviewTab detail={detail} />}
        {tab === "audit" && <AuditTab events={audit} />}
        {tab === "trace" && <TraceTab detail={detail} events={audit} />}
      </div>
    </div>
  );
}
