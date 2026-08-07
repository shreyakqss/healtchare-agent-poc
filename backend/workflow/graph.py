"""Three LangGraph StateGraphs, split at the two human-in-the-loop boundaries.

    intake_graph      one run per patient message
    prescreen_graph   intake complete -> NEEDS_REVIEW
    finalize_graph    clinician approved + notes recorded -> COMPLETED

ponytail: no checkpointer. Durable state is the Postgres tables the models
already define, and the human pause is a *graph boundary* rather than an
`interrupt()` — a doctor may return days later, and the admin dashboard has to
query case state with SQL regardless. Add `langgraph-checkpoint-postgres` (and
the psycopg 3 driver it needs) if mid-graph resume ever becomes necessary.

The DB session travels in the run config rather than in state: it is not
serialisable, and keeping it out of state means state stays checkpointable if
that day comes.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from agents.care_navigator import navigate_care
from agents.medical_record_processor import collect_attachments
from agents.question_planner import plan_next_question
from agents.summary_agent import summarise_prescreening
from agents.symptom_extractor import extract_facts
from agents.task_report_agent import finalise_visit
from agents.urgency_evaluator import evaluate_urgency
from models import IntakeSession, PatientCase
from workflow.states import CaseState
from workflow.transitions import apply_transition

logger = logging.getLogger(__name__)


def _db(config) -> Session:
    session = (config or {}).get("configurable", {}).get("db")
    if session is None:
        raise RuntimeError(
            "No database session in the run config. Invoke graphs with "
            'config={"configurable": {"db": db}}.'
        )
    return session


def _session_for_case(db: Session, case_id) -> IntakeSession | None:
    case = db.get(PatientCase, case_id)
    return db.get(IntakeSession, case.session_id) if case else None


# --- intake ----------------------------------------------------------------


async def node_extract_facts(state: CaseState, config) -> CaseState:
    db = _db(config)
    extracted = await extract_facts(
        db, state["case_id"], state.get("last_message", ""), state.get("turn_index", 0)
    )
    return {"extracted": extracted}


async def node_plan_question(state: CaseState, config) -> CaseState:
    db = _db(config)
    planned = await plan_next_question(
        db, state["case_id"], state.get("transcript", [])
    )
    return {
        "next_question": planned.question,
        "missing_fields": planned.missing_fields,
        "intake_complete": planned.complete,
    }


def build_intake_graph():
    builder = StateGraph(CaseState)
    builder.add_node("extract_facts", node_extract_facts)
    builder.add_node("plan_next_question", node_plan_question)
    builder.add_edge(START, "extract_facts")
    builder.add_edge("extract_facts", "plan_next_question")
    builder.add_edge("plan_next_question", END)
    return builder.compile()


# --- pre-screening ---------------------------------------------------------


async def node_process_records(state: CaseState, config) -> CaseState:
    db = _db(config)
    case_id = state["case_id"]
    session = _session_for_case(db, case_id)
    if session is not None:
        apply_transition(db, session, "ANALYZING", "system:prescreen", case_id)
    return {
        "attachments": collect_attachments(db, case_id),
        "status": "ANALYZING",
    }


async def node_evaluate_urgency(state: CaseState, config) -> CaseState:
    """Rules only. Never call an LLM from this node."""
    db = _db(config)
    result = evaluate_urgency(db, state["case_id"])
    return {
        "priority": result.priority,
        "rule_codes": getattr(result, "rule_codes", []),
        "warnings": result.warnings or [],
        "specialty_hint": getattr(result, "specialty_hint", None),
    }


async def node_navigate_care(state: CaseState, config) -> CaseState:
    db = _db(config)
    recommendation = navigate_care(
        db,
        state["case_id"],
        state["priority"],
        state.get("specialty_hint"),
    )
    return {
        "department_id": recommendation.department_id,
        "doctor_id": recommendation.doctor_id,
    }


async def node_summarise(state: CaseState, config) -> CaseState:
    db = _db(config)
    case_id = state["case_id"]
    summary = await summarise_prescreening(db, case_id)

    session = _session_for_case(db, case_id)
    if session is not None:
        apply_transition(db, session, "NEEDS_REVIEW", "system:prescreen", case_id)

    return {"summary_id": str(summary.id), "status": "NEEDS_REVIEW"}


def build_prescreen_graph():
    builder = StateGraph(CaseState)
    builder.add_node("process_records", node_process_records)
    builder.add_node("evaluate_urgency", node_evaluate_urgency)
    builder.add_node("navigate_care", node_navigate_care)
    builder.add_node("summarise", node_summarise)
    builder.add_edge(START, "process_records")
    builder.add_edge("process_records", "evaluate_urgency")
    builder.add_edge("evaluate_urgency", "navigate_care")
    builder.add_edge("navigate_care", "summarise")
    builder.add_edge("summarise", END)
    return builder.compile()


# --- finalisation ----------------------------------------------------------


async def node_final_summary(state: CaseState, config) -> CaseState:
    db = _db(config)
    summary, draft_task = await finalise_visit(db, state["case_id"])
    return {
        "summary_id": str(summary.id),
        "draft_task": draft_task,
        "status": "COMPLETED",
    }


def build_finalize_graph():
    builder = StateGraph(CaseState)
    builder.add_node("final_summary", node_final_summary)
    builder.add_edge(START, "final_summary")
    builder.add_edge("final_summary", END)
    return builder.compile()


# Compiled once at import; they are stateless and safe to share.
intake_graph = build_intake_graph()
prescreen_graph = build_prescreen_graph()
finalize_graph = build_finalize_graph()


def run_config(db: Session) -> dict:
    return {"configurable": {"db": db}}
