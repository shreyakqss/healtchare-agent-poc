from dataclasses import dataclass

from app.domain.routing import by_earliest, doctor_choice, least_loaded, one_per_time, route, with_doctor

CONFIG = {
    "departments": [{"id": "general", "name": "General", "default": True}, {"id": "cardio", "name": "Cardiology"}],
    "doctors": [{"id": "d1", "name": "Dr One", "department_id": "cardio"}],
    "specialty_map": {"cardio": ["chest pain", "palpitations"]},
    "appointment_types": [{"id": "urgent_slot", "label": "Urgent"}, {"id": "routine_followup", "label": "Routine"}],
    "priority_appointment_map": {"high": "urgent_slot", "low": "routine_followup"},
}


@dataclass
class F:
    kind: str
    value: str
    normalized: str = ""


def test_rule_hint_beats_keywords():
    d = route([F("symptom", "headache")], CONFIG, "high", specialty_hint="cardio")
    assert d.department["id"] == "cardio" and d.basis == "rule_hint" and d.doctor["id"] == "d1"
    assert d.appointment_type["id"] == "urgent_slot"


def test_keyword_match():
    d = route([F("reason_for_visit", "Palpitations at night")], CONFIG, "low")
    assert d.department["id"] == "cardio" and d.matched_keywords == ["palpitations"]


def test_clinic_term_routes_a_paraphrase():
    d = route([F("symptom", "my heart keeps fluttering", "palpitations")], CONFIG, "low")
    assert d.department["id"] == "cardio" and d.matched_keywords == ["palpitations"]


def test_default_department_without_doctor():
    d = route([F("symptom", "sore toe")], CONFIG, "low")
    assert d.department["id"] == "general" and d.doctor is None and d.basis == "default"
    assert "default department" in d.rationale

def test_route_offers_every_doctor_in_the_department():
    config = {**CONFIG, "doctors": [*CONFIG["doctors"], {"id": "d2", "name": "Dr Two", "department_id": "cardio"}]}
    d = route([F("symptom", "chest pain")], config, "low")
    assert [doc["id"] for doc in d.doctors] == ["d1", "d2"]


def _slot(pid: str, hour: int, taken: bool = False) -> dict:
    return {"id": f"{pid}-{hour}", "practitioner_id": pid, "start": f"2030-01-07T{hour:02d}:00:00+00:00", "taken": taken}


def test_earliest_time_wins_and_fewer_open_cases_breaks_a_tie():
    slots = [_slot("busy", 10), _slot("busy", 9), _slot("idle", 10)]
    ordered = by_earliest(slots, {"busy": 3})
    assert [s["id"] for s in ordered] == ["busy-9", "idle-10", "busy-10"]  # earliest beats load


def test_any_doctor_view_keeps_one_time_each_preferring_the_cases_own_then_a_free_one():
    slots = [_slot("a", 9, taken=True), _slot("b", 9), _slot("a", 10), _slot("b", 10), _slot("a", 11, taken=True)]
    assert [s["id"] for s in one_per_time(slots, keep_id="b-10")] == ["b-9", "b-10", "a-11"]


def test_with_no_free_time_the_least_loaded_doctor_is_assigned():
    doctors = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert least_loaded(doctors, {"a": 2, "b": 1, "c": 1})["id"] == "b"
    assert least_loaded([], {}) is None


def test_urgent_patients_get_no_doctor_choice():
    assert not doctor_choice("high")
    assert doctor_choice("medium") and doctor_choice("low") and doctor_choice(None)


def test_rationale_names_how_the_doctor_was_assigned_and_survives_a_name_with_a_period():
    config = {**CONFIG, "doctors": [{"id": "d1", "name": "Dr. One", "department_id": "cardio"},
                                    {"id": "d2", "name": "Dr. Two", "department_id": "cardio"}]}
    d = route([F("symptom", "chest pain")], config, "low")
    d.doctor, d.assigned_by = d.doctors[1], "earliest"
    assert d.rationale.endswith("Assigned to Dr. Two (earliest free time among the department's 2 doctors).")
    changed = with_doctor(d.rationale, "Dr. One", "the patient's choice")
    assert changed.endswith("Advisory only - staff may accept or override. Assigned to Dr. One (the patient's choice).")
    assert changed.count("Assigned to") == 1



def test_red_flag_routes_by_keyword_and_gives_no_doctor_choice():
    facts = [type("F", (), {"kind": "symptom", "value": "severe chest pain", "normalized": ""})()]
    assert route(facts, CONFIG, "high").department["id"] == "cardio"
    assert not doctor_choice("low", emergency=True)


CLINIC = {
    **CONFIG,
    "departments": [
        {"id": "general_medicine", "name": "General Medicine", "default": True},
        {"id": "cardiology", "name": "Cardiology"}, {"id": "pulmonology", "name": "Pulmonology"},
        {"id": "orthopedics", "name": "Orthopedics"}, {"id": "dermatology", "name": "Dermatology"},
        {"id": "ent", "name": "ENT"},
    ],
    "specialty_map": {
        "cardiology": ["chest pain", "palpitations", "heart", "chest tightness"],
        "pulmonology": ["shortness of breath", "breathlessness", "wheezing", "persistent cough", "asthma"],
        "orthopedics": ["joint pain", "back pain", "knee"],
        "dermatology": ["rash", "skin", "itching"],
        "ent": ["sore throat", "ear pain"],
    },
    "infection_routing": {"signs": ["fever", "chills"], "departments": ["pulmonology", "orthopedics", "dermatology"]},
}


def _dept(*facts: F) -> str:
    return route(list(facts), CLINIC, "low").department["id"]


def test_fever_with_cough_and_breathlessness_is_general_medicine_not_cardiology():
    # the Prashant Tomar case: chest infection, no chest pain
    d = route([
        F("reason_for_visit", "fever", "fever"), F("symptom", "sometimes difficulty in breathing", "breathlessness"),
        F("symptom", "coughing", "persistent cough"), F("negative", "no chest pain", "chest pain"),
    ], CLINIC, "high")
    assert d.department["id"] == "general_medicine" and d.basis == "infection"
    assert "infection" in d.rationale


def test_breathlessness_without_fever_is_pulmonology():
    assert _dept(F("symptom", "wheezing at night"), F("symptom", "short of breath", "breathlessness")) == "pulmonology"


def test_fever_with_joint_pain_or_rash_is_general_medicine():
    assert _dept(F("symptom", "fever"), F("symptom", "joint pain")) == "general_medicine"
    assert _dept(F("symptom", "fever"), F("symptom", "red rash on arms", "rash")) == "general_medicine"


def test_fever_with_sore_throat_stays_ent():
    assert _dept(F("symptom", "fever"), F("symptom", "sore throat")) == "ent"


def test_chest_pain_is_cardiology_and_best_match_beats_map_order():
    assert _dept(F("symptom", "chest pain on walking")) == "cardiology"
    # one cardiology word vs two pulmonology ones: pulmonology, though cardiology is listed first
    assert _dept(F("symptom", "chest tightness"), F("symptom", "wheezing"), F("symptom", "breathlessness")) == "pulmonology"


def test_whole_words_only_and_past_history_does_not_route():
    assert _dept(F("symptom", "heartburn after meals")) == "general_medicine"
    assert _dept(F("reason_for_visit", "knee pain"), F("history", "asthma")) == "orthopedics"


def test_denied_symptoms_never_route():
    assert _dept(F("symptom", "headache"), F("negative", "no chest pain", "chest pain")) == "general_medicine"


from app.domain.routing import accept_ai_pick  # noqa: E402

AI_CLINIC = {**CLINIC, "ai_routing": {"enabled": True, "protected": ["cardiology"], "policy": []}}


def test_ai_pick_used_when_valid_and_grounded():
    facts = [F("symptom", "chest tightness"), F("symptom", "fever"), F("symptom", "stomach upset")]
    rules = route(facts, AI_CLINIC, "high")
    assert accept_ai_pick(rules, "general_medicine", ["symptom: fever", "stomach upset"], facts, AI_CLINIC) == "used"


def test_ai_pick_rejected_for_unknown_department_or_invented_facts():
    facts = [F("symptom", "sore throat")]
    rules = route(facts, AI_CLINIC, "low")
    assert accept_ai_pick(rules, "neurology", ["sore throat"], facts, AI_CLINIC) == "invalid"
    assert accept_ai_pick(rules, "general_medicine", ["high fever"], facts, AI_CLINIC) == "invalid"


def test_heart_symptoms_without_fever_stay_in_cardiology():
    facts = [F("symptom", "chest pain on walking")]
    rules = route(facts, AI_CLINIC, "high")
    assert accept_ai_pick(rules, "general_medicine", ["chest pain on walking"], facts, AI_CLINIC) == "protected"
    assert accept_ai_pick(rules, "cardiology", ["chest pain on walking"], facts, AI_CLINIC) == "used"


def test_rationale_shows_ai_reason_and_rules_alternative():
    d = route([F("symptom", "fever")], AI_CLINIC, "low", specialty_hint="general_medicine")
    d.basis, d.ai_status, d.ai_reason, d.rules_department = "ai", "used", "Fever with cough, likely chest infection", "Pulmonology"
    assert "AI router: Fever with cough" in d.rationale and "rules suggested Pulmonology" in d.rationale
    d2 = route([F("symptom", "chest pain")], AI_CLINIC, "high")
    d2.ai_status = "unavailable"
    assert "AI router was unavailable" in d2.rationale


TIE_CONFIG = {
    "departments": [{"id": "general", "name": "General", "default": True},
                    {"id": "pulmo", "name": "Pulmonology"}, {"id": "cardio", "name": "Cardiology"},
                    {"id": "derm", "name": "Dermatology"}],
    "doctors": [{"id": "g1", "name": "Dr G", "department_id": "general"},
                {"id": "p1", "name": "Dr P", "department_id": "pulmo"},
                {"id": "c1", "name": "Dr C", "department_id": "cardio"}],
    "specialty_map": {"cardio": ["breathlessness", "heart failure"], "pulmo": ["breathlessness", "asthma"],
                      "derm": ["rash"]},
    "appointment_types": [{"id": "routine_followup", "label": "Routine"}],
}


def test_history_breaks_a_tie_only():
    # Breathlessness matches both; a history of asthma tips it to Pulmonology (Cardiology comes first otherwise).
    tied = route([F("symptom", "breathlessness")], TIE_CONFIG, "low")
    assert tied.department["id"] == "cardio"
    d = route([F("symptom", "breathlessness"), F("history", "asthma")], TIE_CONFIG, "low")
    assert d.department["id"] == "pulmo"


def test_history_alone_never_routes():
    d = route([F("symptom", "knee pain"), F("history", "asthma")], TIE_CONFIG, "low")
    assert d.department["id"] == "general" and d.basis == "default"


def test_department_without_doctors_falls_back_to_default():
    d = route([F("symptom", "itchy rash")], TIE_CONFIG, "low")
    assert d.department["id"] == "general" and d.unstaffed == "Dermatology" and d.doctors
    assert "Dermatology has no doctor rostered, so General sees the case" in d.rationale
    assert d.rationale.startswith("Routed to Dermatology")
