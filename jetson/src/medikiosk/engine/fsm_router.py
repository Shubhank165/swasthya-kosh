"""
MediKiosk – 4-Phase Clinical FSM Router
========================================
Implements the deterministic Finite State Machine that drives each patient
session through the four clinical phases:

  INIT → TRIAGE_GATE → [EMERGENCY | FRAMEWORK_ROUTE] → ENTROPY_LOOP → COMPLETE

Phase 1 (TRIAGE_GATE)  : NHS Pathways-style ABCD red-flag evaluation.
                          Any red flag → EMERGENCY, session terminates.
Phase 2 (FRAMEWORK_ROUTE): Route chief complaint to SOCRATES/OLD_CARTS/
                          SAMPLE/COCA/ROTS via routing_rules table.
Phase 3 (ENTROPY_LOOP) : DXplain-style entropy engine selects next question.
Phase 4 (PROXY_ELICIT) : FHIR proxy tag collection for unknown history.

Author : MediKiosk Engineering Team
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from medikiosk.engine.config import (
    DB_PATH,
    EMERGENCY_STATUS,
    URGENT_STATUS,
    ROUTINE_STATUS,
    FSM_STATE_INIT,
    FSM_STATE_TRIAGE,
    FSM_STATE_FRAMEWORK,
    FSM_STATE_ENTROPY_LOOP,
    FSM_STATE_PROXY_ELICIT,
    FSM_STATE_COMPLETE,
    FSM_STATE_EMERGENCY,
    PROXY_TAGS,
    MAX_QUESTIONS,
)
from medikiosk.engine.db import fetch_all, fetch_one, execute_write, execute_many, row_to_dict
from medikiosk.engine.math_engine import EntropyEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hard-coded Triage Node IDs (Phase 1 – evaluated before DB entropy loop)
# These must match the node IDs inserted by master_clinical_database.py
# ---------------------------------------------------------------------------
TRIAGE_NODES_ORDER = [
    "T001",  # Airway obstruction
    "T002",  # Severe respiratory distress
    "T003",  # Circulatory collapse / shock
    "T004",  # Altered consciousness (GCS < 14)
    "T005",  # Uncontrolled external hemorrhage
    "T006",  # Anaphylaxis signs
    "T007",  # Active seizure
    "T008",  # Stroke (FAST positive)
    "T009",  # Crushing chest pain (possible MI)
    "T010",  # Major trauma (RTA / fall from height)
    "T011",  # Active suicidal ideation with plan
    "T012",  # Obstetric emergency (heavy bleed / severe pain in pregnancy)
]

# Any TRUE answer to these nodes triggers EMERGENCY
RED_FLAG_NODES = set(TRIAGE_NODES_ORDER)


class ClinicalFSM:
    """
    The MediKiosk Finite State Machine.

    One ClinicalFSM instance is created per web-worker process and is
    shared across concurrent requests (all state is in the DB, not in RAM).
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.engine  = EntropyEngine(db_path=db_path)

    # =======================================================================
    # PUBLIC API
    # =======================================================================

    def start_session(
        self,
        chief_complaint: str,
        demographics: dict,
        patient_token: Optional[str] = None,
    ) -> dict:
        """
        Initialise a new patient session and return the first triage node.

        Steps:
          1. Generate session_id (UUID-v4)
          2. Persist session record to patient_sessions
          3. Return the first triage node

        Args:
            chief_complaint: Raw patient complaint string
            demographics   : {age, sex, language}
            patient_token  : Optional anonymous patient identifier

        Returns:
            {
              "session_id": str,
              "fsm_state":  str,
              "triage_status": str,
              "next_node":  dict,
              "message":    str,
            }
        """
        session_id = str(uuid.uuid4())
        now        = datetime.now(timezone.utc).isoformat()

        initial_state = {
            "answers":       {},
            "scores":        {},
            "asked":         [],
            "triage_index":  0,   # Index into TRIAGE_NODES_ORDER
            "top_prob_prev": 0.0,
            "demographics":  demographics,
            "proxy_history": [],
        }

        execute_write(
            """
            INSERT INTO patient_sessions
              (session_id, created_at, updated_at, patient_token,
               chief_complaint, fsm_state, triage_status,
               questions_asked, state_json, proxy_history)
            VALUES (?,?,?,?,?, ?,?,?,?,?)
            """,
            (
                session_id, now, now, patient_token,
                chief_complaint, FSM_STATE_TRIAGE, ROUTINE_STATUS,
                0, json.dumps(initial_state), "[]",
            ),
            db_path=self.db_path,
        )

        first_node = self._fetch_node(TRIAGE_NODES_ORDER[0])
        logger.info("Session started: %s | complaint: %s", session_id, chief_complaint)

        return {
            "session_id":    session_id,
            "fsm_state":     FSM_STATE_TRIAGE,
            "triage_status": ROUTINE_STATUS,
            "next_node":     first_node,
            "message":       "Session initialised. Beginning safety triage.",
        }

    # -----------------------------------------------------------------------

    def submit_answer(
        self,
        session_id: str,
        node_id: str,
        raw_answer: Any,
        answer_type: str = "DIRECT",
        proxy_tag: Optional[str] = None,
    ) -> dict:
        """
        Accept a patient answer, advance the FSM, and return the next node.

        Args:
            session_id  : Active session UUID
            node_id     : The node being answered
            raw_answer  : Patient's answer value
            answer_type : DIRECT | PROXY | SKIP
            proxy_tag   : FHIR proxy tag if answer_type == PROXY

        Returns:
            {
              "session_id": str,
              "fsm_state":  str,
              "triage_status": str,
              "questions_asked": int,
              "next_node":  dict | None,
              "completed":  bool,
              "message":    str,
            }
        """
        session = self._load_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if session["completed"]:
            return self._build_response(session, None, completed=True,
                                        msg="Session already completed.")

        state = json.loads(session["state_json"])
        fsm   = session["fsm_state"]

        # Handle PROXY answer: store tag, treat as NULL for scoring
        if answer_type == "PROXY" and proxy_tag:
            state.setdefault("proxy_history", []).append(proxy_tag)
            scoring_answer = None
        elif answer_type == "SKIP":
            scoring_answer = None
        else:
            scoring_answer = raw_answer

        # -- Phase 1: TRIAGE ------------------------------------------------
        if fsm == FSM_STATE_TRIAGE:
            return self._handle_triage(session, state, node_id, scoring_answer)

        # -- Phase 2: FRAMEWORK_ROUTE (no patient answer required here) ------
        # This state is transitioned to automatically after triage; the
        # framework-assignment node is internal, not presented to the patient.

        # -- Phase 3: ENTROPY_LOOP ------------------------------------------
        if fsm in (FSM_STATE_FRAMEWORK, FSM_STATE_ENTROPY_LOOP):
            return self._handle_entropy(session, state, node_id, scoring_answer)

        # -- Phase 4: PROXY_ELICIT ------------------------------------------
        if fsm == FSM_STATE_PROXY_ELICIT:
            return self._handle_proxy(session, state, node_id, scoring_answer)

        return self._build_response(session, None, completed=True,
                                    msg="Session in terminal state.")

    # -----------------------------------------------------------------------

    def get_next_node(self, session_id: str) -> Optional[dict]:
        """
        Fetch the next pending question node without advancing state.
        Useful for GET /session/{id}/next polling.
        """
        session = self._load_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        state = json.loads(session["state_json"])
        fsm   = session["fsm_state"]

        if fsm == FSM_STATE_TRIAGE:
            idx = state.get("triage_index", 0)
            if idx < len(TRIAGE_NODES_ORDER):
                return self._fetch_node(TRIAGE_NODES_ORDER[idx])
        elif fsm in (FSM_STATE_ENTROPY_LOOP, FSM_STATE_FRAMEWORK):
            fw  = session.get("framework", "SOCRATES")
            nxt = self.engine.get_next_best_question(state, fw)
            if nxt:
                return self._fetch_node(nxt)
        elif fsm == FSM_STATE_PROXY_ELICIT:
            nxt = self.engine.get_next_best_question(state, "PMH")
            if nxt:
                return self._fetch_node(nxt)
        return None

    # =======================================================================
    # PRIVATE PHASE HANDLERS
    # =======================================================================

    def _handle_triage(
        self, session: dict, state: dict, node_id: str, answer: Any
    ) -> dict:
        """
        Phase 1 handler: evaluate red flags one by one.

        If the patient answers TRUE to any red-flag node:
          --> Set triage_status = EMERGENCY
          --> Set fsm_state = EMERGENCY
          --> Mark session complete

        Otherwise:
          --> Advance to next triage node
          --> When all triage nodes done --> route to Phase 2
        """
        # Store answer
        state.setdefault("answers", {})[node_id] = answer
        state.setdefault("asked", []).append(node_id)

        # Check red flag
        if node_id in RED_FLAG_NODES and self._is_positive(answer):
            logger.warning("RED FLAG triggered: %s | session %s", node_id, session["session_id"])
            self._persist_session(
                session["session_id"], state,
                fsm_state=FSM_STATE_EMERGENCY,
                triage_status=EMERGENCY_STATUS,
                questions_asked=len(state["asked"]),
                completed=True,
            )
            return {
                "session_id":     session["session_id"],
                "fsm_state":      FSM_STATE_EMERGENCY,
                "triage_status":  EMERGENCY_STATUS,
                "questions_asked":len(state["asked"]),
                "next_node":      None,
                "completed":      True,
                "message":        "EMERGENCY ALERT: Immediate clinical intervention required. "
                                  "Dispatch nurse / physician NOW.",
            }

        # Advance triage index
        idx = state.get("triage_index", 0) + 1
        state["triage_index"] = idx

        if idx < len(TRIAGE_NODES_ORDER):
            # More triage nodes to ask
            next_nid  = TRIAGE_NODES_ORDER[idx]
            next_node = self._fetch_node(next_nid)
            self._persist_session(
                session["session_id"], state,
                fsm_state=FSM_STATE_TRIAGE,
                triage_status=ROUTINE_STATUS,
                questions_asked=len(state["asked"]),
            )
            return {
                "session_id":     session["session_id"],
                "fsm_state":      FSM_STATE_TRIAGE,
                "triage_status":  ROUTINE_STATUS,
                "questions_asked":len(state["asked"]),
                "next_node":      next_node,
                "completed":      False,
                "message":        "Safety triage in progress.",
            }

        # All triage nodes passed --> route to framework
        return self._transition_to_framework(session, state)

    # -----------------------------------------------------------------------

    def _transition_to_framework(
        self, session: dict, state: dict
    ) -> dict:
        """
        Phase 2: Route chief complaint to a clinical framework.
        The routing result is written to the session and we immediately
        serve the first entropy-selected question.
        """
        complaint = (session.get("chief_complaint") or "").lower().strip()
        framework = self._route_complaint(complaint)

        logger.info("Session %s routed to framework: %s", session["session_id"], framework)

        self._persist_session(
            session["session_id"], state,
            fsm_state=FSM_STATE_ENTROPY_LOOP,
            triage_status=ROUTINE_STATUS,
            framework=framework,
            questions_asked=len(state["asked"]),
        )

        # Re-load with updated framework
        session["framework"] = framework
        return self._serve_next_entropy_node(session, state, framework)

    # -----------------------------------------------------------------------

    def _handle_entropy(
        self, session: dict, state: dict, node_id: str, answer: Any
    ) -> dict:
        """Phase 3: Entropy loop handler."""
        framework = session.get("framework", "SOCRATES")

        # Record previous top probability
        _, prev_top_prob = self.engine.get_top_probability(state)

        # Update scores
        state = self.engine.update_scores(state, node_id, answer)

        # Get new top probability
        _, new_top_prob  = self.engine.get_top_probability(state)

        # Check termination
        should_stop, reason = self.engine.check_termination(
            state, prev_top_prob, new_top_prob
        )

        state["top_prob_prev"] = new_top_prob
        q_asked = len(state.get("asked", []))

        if should_stop:
            logger.info("Session %s entropy loop ended: %s", session["session_id"], reason)
            # Check if PMH proxy elicitation is needed
            return self._transition_to_proxy_or_complete(session, state, reason)

        self._persist_session(
            session["session_id"], state,
            fsm_state=FSM_STATE_ENTROPY_LOOP,
            questions_asked=q_asked,
        )
        return self._serve_next_entropy_node(session, state, framework)

    # -----------------------------------------------------------------------

    def _handle_proxy(
        self, session: dict, state: dict, node_id: str, answer: Any
    ) -> dict:
        """Phase 4: Proxy history elicitation handler."""
        state = self.engine.update_scores(state, node_id, answer)
        q_asked = len(state.get("asked", []))
        clinical_asked = len([n for n in state.get("asked", []) if not n.startswith("T0")])

        # Check for more PMH nodes
        if clinical_asked < MAX_QUESTIONS:
            nxt = self.engine.get_next_best_question(state, "PMH")
            if nxt:
                next_node = self._fetch_node(nxt)
                self._persist_session(
                    session["session_id"], state,
                    fsm_state=FSM_STATE_PROXY_ELICIT,
                    questions_asked=q_asked,
                )
                return {
                    "session_id":     session["session_id"],
                    "fsm_state":      FSM_STATE_PROXY_ELICIT,
                    "triage_status":  session["triage_status"],
                    "questions_asked":q_asked,
                    "next_node":      self._enrich_node(next_node, state),
                    "completed":      False,
                    "message":        "Please answer a few questions about your medical history.",
                }

        # All done
        return self._complete_session(session, state)

    # -----------------------------------------------------------------------

    def _transition_to_proxy_or_complete(
        self, session: dict, state: dict, reason: str
    ) -> dict:
        """After entropy loop: ask PMH proxy questions or complete."""
        clinical_asked = len([n for n in state.get("asked", []) if not n.startswith("T0")])
        if clinical_asked < MAX_QUESTIONS:
            nxt = self.engine.get_next_best_question(state, "PMH")
            if nxt:
                next_node = self._fetch_node(nxt)
                q_asked   = len(state.get("asked", []))
                self._persist_session(
                    session["session_id"], state,
                    fsm_state=FSM_STATE_PROXY_ELICIT,
                    questions_asked=q_asked,
                )
                return {
                    "session_id":     session["session_id"],
                    "fsm_state":      FSM_STATE_PROXY_ELICIT,
                    "triage_status":  session["triage_status"],
                    "questions_asked":q_asked,
                    "next_node":      self._enrich_node(next_node, state),
                    "completed":      False,
                    "message":        "Please answer a few questions about your medical history.",
                }
        return self._complete_session(session, state)

    # -----------------------------------------------------------------------

    def _serve_next_entropy_node(
        self, session: dict, state: dict, framework: str
    ) -> dict:
        """Pick the next best question and return it."""
        nxt = self.engine.get_next_best_question(state, framework)
        q_asked = len(state.get("asked", []))

        if nxt is None:
            return self._complete_session(session, state)

        next_node = self._fetch_node(nxt)
        return {
            "session_id":     session["session_id"],
            "fsm_state":      FSM_STATE_ENTROPY_LOOP,
            "triage_status":  session["triage_status"],
            "questions_asked":q_asked,
            "next_node":      self._enrich_node(next_node, state),
            "completed":      False,
            "message":        f"Question {q_asked + 1} of up to {MAX_QUESTIONS}.",
        }

    # -----------------------------------------------------------------------

    def _complete_session(self, session: dict, state: dict) -> dict:
        """Finalise the session and compute the differential diagnosis."""
        diff = self.engine.build_differential(state)
        now  = datetime.now(timezone.utc).isoformat()
        q_asked = len(state.get("asked", []))

        execute_write(
            """
            UPDATE patient_sessions SET
              fsm_state=?, questions_asked=?, state_json=?,
              top_syndromes=?, proxy_history=?,
              completed=1, completed_at=?, updated_at=?
            WHERE session_id=?
            """,
            (
                FSM_STATE_COMPLETE,
                q_asked,
                json.dumps(state),
                json.dumps(diff),
                json.dumps(state.get("proxy_history", [])),
                now, now,
                session["session_id"],
            ),
            db_path=self.db_path,
        )

        top = diff[0]["name"] if diff else "Undetermined"
        return {
            "session_id":     session["session_id"],
            "fsm_state":      FSM_STATE_COMPLETE,
            "triage_status":  session["triage_status"],
            "questions_asked":q_asked,
            "next_node":      None,
            "completed":      True,
            "message":        f"Assessment complete. Leading differential: {top}.",
        }

    # =======================================================================
    # ROUTING LOGIC
    # =======================================================================

    def _route_complaint(self, complaint: str) -> str:
        """
        Map the chief complaint to a clinical framework.

        Strategy:
          1. Query routing_rules for keyword matches (ordered by priority)
          2. First match wins
          3. Default to SOCRATES if no match found
        """
        if not complaint:
            return "SOCRATES"

        rows = fetch_all(
            "SELECT complaint_keyword, framework FROM routing_rules "
            "ORDER BY priority ASC",
            db_path=self.db_path,
        )

        complaint_lower = complaint.lower()
        for row in rows:
            kw = row["complaint_keyword"].lower()
            if kw in complaint_lower:
                return row["framework"]

        # Default
        return "SOCRATES"

    # =======================================================================
    # DB HELPERS
    # =======================================================================

    def _load_session(self, session_id: str) -> Optional[dict]:
        row = fetch_one(
            "SELECT * FROM patient_sessions WHERE session_id=?",
            (session_id,),
            db_path=self.db_path,
        )
        return row_to_dict(row)

    def _fetch_node(self, node_id: str) -> Optional[dict]:
        row = fetch_one(
            "SELECT * FROM nodes WHERE node_id=?",
            (node_id,),
            db_path=self.db_path,
        )
        if row is None:
            return None
        nd = dict(row)
        # Parse JSON options
        if nd.get("ui_options"):
            try:
                nd["ui_options"] = json.loads(nd["ui_options"])
            except (json.JSONDecodeError, TypeError):
                pass
        return nd

    def _enrich_node(self, node: Optional[dict], state: dict) -> Optional[dict]:
        """Attach session context to a node response (questions asked, remaining)."""
        if node is None:
            return None
        q_asked = len(state.get("asked", []))
        node["questions_asked"]    = q_asked
        node["questions_remaining"] = max(0, MAX_QUESTIONS - q_asked)
        return node

    def _persist_session(
        self,
        session_id: str,
        state: dict,
        fsm_state: str = None,
        triage_status: str = None,
        framework: str = None,
        questions_asked: int = None,
        completed: bool = False,
    ) -> None:
        now  = datetime.now(timezone.utc).isoformat()
        sets = ["state_json=?", "updated_at=?"]
        vals = [json.dumps(state), now]

        if fsm_state is not None:
            sets.append("fsm_state=?")
            vals.append(fsm_state)
        if triage_status is not None:
            sets.append("triage_status=?")
            vals.append(triage_status)
        if framework is not None:
            sets.append("framework=?")
            vals.append(framework)
        if questions_asked is not None:
            sets.append("questions_asked=?")
            vals.append(questions_asked)
        if completed:
            sets.append("completed=1")
            sets.append("completed_at=?")
            vals.append(now)

        proxy_history = state.get("proxy_history", [])
        sets.append("proxy_history=?")
        vals.append(json.dumps(proxy_history))

        vals.append(session_id)
        execute_write(
            f"UPDATE patient_sessions SET {', '.join(sets)} WHERE session_id=?",
            tuple(vals),
            db_path=self.db_path,
        )

    # =======================================================================
    # UTILITY
    # =======================================================================

    @staticmethod
    def _is_positive(answer: Any) -> bool:
        """Return True if the answer represents a clinically positive response."""
        if answer is None:
            return False
        if isinstance(answer, bool):
            return answer
        if isinstance(answer, (int, float)):
            return answer > 0
        if isinstance(answer, str):
            return answer.strip().lower() in ("yes", "true", "1", "oui", "haan")
        return False

    @staticmethod
    def _build_response(
        session: dict, next_node: Optional[dict],
        completed: bool = False, msg: str = ""
    ) -> dict:
        return {
            "session_id":     session["session_id"],
            "fsm_state":      session["fsm_state"],
            "triage_status":  session["triage_status"],
            "questions_asked":session["questions_asked"],
            "next_node":      next_node,
            "completed":      completed,
            "message":        msg,
        }
