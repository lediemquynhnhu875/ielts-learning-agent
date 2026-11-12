"""Weakness profile derived from a validated Speaking assessment.

Everything here is computed from an assessment that already passed evidence
validation; no band, score or recommendation is produced in this module. The
next-band descriptor is quoted from the configured rubric corpus rather than
written as advice, so the Planning Agent receives rubric text with provenance
instead of generated coaching.

Nothing is written to the group's shared database: this only shapes what another
agent can read. `write_target` stays null until that integration exists.
"""

import math

from ielts_agent.agents.speaking.assessment import CRITERIA
from ielts_agent.agents.speaking.database import attempt_id, stable_id


SCHEMA_VERSION = "speaking-weakness-profile-1.0"


def next_band_descriptor(criterion, band, descriptors):
    """The descriptor one whole band above the assigned band, quoted verbatim."""
    if type(band) not in (int, float) or not math.isfinite(band):
        return None
    target = min(9, math.floor(band) + 1)
    chunk = next((d for d in descriptors if d.get("criterion") == criterion and d.get("band") == target), None)
    if not chunk:
        return None
    return {"band": target, "chunk_id": chunk["chunk_id"], "text": chunk["text"],
            "version": chunk.get("version"), "source_url": chunk.get("source_url"),
            "page": chunk.get("page")}


def weakness_profile(state, answers, grading=None):
    """Ranked criteria, evidence and rubric targets for the Planning Agent."""
    grading = grading or {}
    assessment = grading.get("assessment") or state.get("assessment") or {}
    descriptors = grading.get("descriptor_chunks", [])
    profile = {
        "schema_version": SCHEMA_VERSION,
        "learner_id": stable_id(state["learner_id"]), "session_id": stable_id(state["session_id"]),
        "attempt_id": attempt_id(state), "thread_id": state.get("thread_id"),
        "run_id": stable_id(assessment["run_id"]) if assessment.get("run_id") else None,
        "mode": state["mode"], "assessment_status": assessment.get("status"),
        "overall_band": assessment.get("overall_band"),
        "status": "unavailable", "reason": None,
        "criteria": [], "weakest_criteria": [], "recurring_flags": [],
        "corrections": [], "limitations": assessment.get("limitations"),
        "disclaimer": assessment.get("disclaimer"),
        "write_target": None,
    }
    turns = {a["answer_id"]: index for index, a in enumerate(answers, 1)}
    counted = {}
    for answer in answers:
        for flag in answer.get("flags", []):
            counted.setdefault(flag, []).append(turns[answer["answer_id"]])
    profile["recurring_flags"] = [{"flag": flag, "turn_numbers": sorted(found), "turn_count": len(found)}
                                  for flag, found in sorted(counted.items())]
    if not assessment:
        profile["reason"] = "Phiên chưa được chấm."
        return profile
    if assessment.get("status") == "pending_teacher":
        profile["status"] = "pending_teacher"
        profile["reason"] = "Hai bản chấm chưa thống nhất hoặc chưa hợp lệ; chờ giáo viên trước khi lập kế hoạch luyện."
        return profile
    scored = [row for row in assessment.get("criteria", [])
              if row.get("status") == "assessed" and type(row.get("band")) in (int, float)]
    if not scored:
        profile["reason"] = "Chưa có tiêu chí nào được chấm hợp lệ."
        return profile
    order = sorted(scored, key=lambda row: (row["band"], CRITERIA.index(row["criterion"])))
    for rank, row in enumerate(order, 1):
        profile["criteria"].append({
            "criterion": row["criterion"], "band": row["band"], "rank": rank,
            "comment": row.get("comment"), "descriptor_refs": row.get("descriptor_refs", []),
            "evidence": [{"turn_number": turns.get(span.get("answer_id")), "answer_id": span.get("answer_id"),
                          "quote": span.get("quote"), "t_start_s": span.get("t_start_s")}
                         for span in row.get("evidence", [])],
            "next_band_descriptor": next_band_descriptor(row["criterion"], row["band"], descriptors),
        })
    lowest = order[0]["band"]
    profile["weakest_criteria"] = [row["criterion"] for row in order if row["band"] == lowest]
    profile["corrections"] = assessment.get("corrections", [])
    profile["not_assessed"] = [row["criterion"] for row in assessment.get("criteria", [])
                               if row.get("status") != "assessed"]
    profile["status"] = "ready"
    return profile
