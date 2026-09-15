"""
MediKiosk – Information Entropy / Variance Engine (The Adaptive Discriminator)
===============================================================================
Implements the DXplain-inspired adaptive question selection algorithm.

Algorithm Overview:
  1. Maintain a score for each syndrome: score(s) = Σ [F × E × answer_weight]
  2. Compute active syndromes (score >= MIN_SYNDROME_SCORE)
  3. For each UNASKED question node, compute Variance of Evoking Strength
     across the active syndrome set: σ²(E_i)
  4. Select the node with the HIGHEST variance → most discriminating question
  5. Terminate if:
     a) 12 questions asked (MAX_QUESTIONS)
     b) Δ top_probability < 2% (FLATTENING_THRESHOLD) → flattening curve

Null/Unknown Safety:
  answer_weight for None / 'unknown' → 0.0 (zero contribution, no contamination)

Author : MediKiosk Engineering Team
Version: 1.0.0
Ref    : DXplain (MGH), NHS Pathways, Bayesian Clinical Scoring
"""

from __future__ import annotations

import math
import logging
from typing import Any, Optional

from medikiosk.engine.config import (
    MAX_QUESTIONS,
    FLATTENING_THRESHOLD,
    MIN_SYNDROME_SCORE,
    MIN_ACTIVE_SYNDROMES,
    ANSWER_YES,
    ANSWER_NO,
    ANSWER_NULL,
    SLIDER_MAX,
)
from medikiosk.engine.db import fetch_all

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: Answer Normalisation
# ---------------------------------------------------------------------------

def normalise_answer(answer: Any, ui_type: str) -> float:
    """
    Convert a raw patient answer to a float weight in [-0.5, 1.0].

    Rules:
      BINARY      → True/1/"yes"  → +1.0
                  → False/0/"no" → -0.5
                  → None/"unknown"→  0.0
      SLIDER      → raw / SLIDER_MAX  (e.g. 8/10 → 0.8)
      MULTI_SELECT→ +1.0 if list is non-empty, 0.0 if empty/None
      SINGLE_SELECT→ +1.0 if value selected, 0.0 if None
      BODY_MAP    → +1.0 if any region selected, 0.0 otherwise
      DATE_PICKER / TIME_PICKER / DURATION / TEXT_SHORT / NUMERIC
                  → +1.0 if a value was entered, 0.0 if None

    Args:
        answer  : Raw answer from the patient UI
        ui_type : The node's UI widget type

    Returns:
        float weight in [-0.5, 1.0]
    """
    if answer is None:
        return ANSWER_NULL

    ui = ui_type.upper()

    if ui == "BINARY":
        if isinstance(answer, bool):
            return ANSWER_YES if answer else ANSWER_NO
        if isinstance(answer, (int, float)):
            return ANSWER_YES if answer else ANSWER_NO
        if isinstance(answer, str):
            low = answer.strip().lower()
            if low in ("yes", "true", "1", "oui", "haan", "ha"):
                return ANSWER_YES
            if low in ("no", "false", "0", "non", "nahi", "nai"):
                return ANSWER_NO
            if low in ("unknown", "don't know", "unsure", "maybe", ""):
                return ANSWER_NULL
        return ANSWER_NULL

    if ui == "SLIDER":
        try:
            raw = float(answer)
            return max(0.0, min(raw / SLIDER_MAX, 1.0))
        except (TypeError, ValueError):
            return ANSWER_NULL

    if ui in ("MULTI_SELECT", "BODY_MAP"):
        if isinstance(answer, (list, tuple, set)) and len(answer) > 0:
            return ANSWER_YES
        if isinstance(answer, str) and answer.strip():
            return ANSWER_YES
        return ANSWER_NULL

    if ui in ("SINGLE_SELECT", "DATE_PICKER", "TIME_PICKER",
              "TEXT_SHORT", "DURATION", "NUMERIC"):
        if answer is None or answer == "":
            return ANSWER_NULL
        return ANSWER_YES

    return ANSWER_NULL


# ---------------------------------------------------------------------------
# Core Engine
# ---------------------------------------------------------------------------

class EntropyEngine:
    """
    The Adaptive Discriminator.

    Operates on a session_state dictionary with this shape:
      {
        "answers": {node_id: raw_answer},        # Patient answers
        "scores":  {syndrome_id: float},          # Running F×E score
        "asked":   [node_id, ...],                # Ordered list of asked nodes
        "framework": str,                         # Active framework
        "top_prob_prev": float,                   # Top probability at last step
      }
    """

    def __init__(self, db_path: str = None):
        from medikiosk.engine.config import DB_PATH
        self.db_path = db_path or DB_PATH
        self._weights_cache: dict | None = None   # Lazy-loaded
        self._nodes_cache:   dict | None = None

    # -----------------------------------------------------------------------
    # Internal: Load / cache the full weight matrix from DB
    # -----------------------------------------------------------------------

    def _load_weights(self) -> dict:
        """
        Load the complete matrix_weights table into an in-memory dict.
        Structure:
          weights[node_id][syndrome_id] = {
              'frequency': int,
              'evoking_strength': int,
              'answer_direction': str  # POSITIVE | NEGATIVE
          }
        Cached after first load (weights are static during a session).
        """
        if self._weights_cache is not None:
            return self._weights_cache

        rows = fetch_all(
            "SELECT node_id, syndrome_id, frequency, evoking_strength, "
            "answer_direction FROM matrix_weights",
            db_path=self.db_path,
        )
        weights: dict = {}
        for row in rows:
            nid = row["node_id"]
            sid = row["syndrome_id"]
            if nid not in weights:
                weights[nid] = {}
            weights[nid][sid] = {
                "frequency":        row["frequency"],
                "evoking_strength": row["evoking_strength"],
                "answer_direction": row["answer_direction"],
            }
        self._weights_cache = weights
        logger.debug("Weight matrix loaded: %d node entries", len(weights))
        return weights

    def _load_nodes(self) -> dict:
        """
        Load all nodes into an in-memory dict keyed by node_id.
        Cached after first load.
        """
        if self._nodes_cache is not None:
            return self._nodes_cache
        rows = fetch_all(
            "SELECT node_id, ui_type, framework, phase, system_tag, "
            "is_mandatory, display_order FROM nodes",
            db_path=self.db_path,
        )
        nodes = {row["node_id"]: dict(row) for row in rows}
        self._nodes_cache = nodes
        return nodes

    # -----------------------------------------------------------------------
    # Public: Update syndrome scores after a new answer
    # -----------------------------------------------------------------------

    def update_scores(
        self,
        session_state: dict,
        node_id: str,
        raw_answer: Any,
    ) -> dict:
        """
        Recalculate syndrome scores after the patient answers `node_id`.

        Score delta for each syndrome s:
            delta(s) = F(n,s) × E(n,s) × answer_weight × direction_sign

        direction_sign:
            POSITIVE: +1  (YES increases score)
            NEGATIVE: -1  (YES decreases score – e.g. "pain relieved by antacids"
                           INCREASES GERD score, so that node is POSITIVE for GERD)

        Args:
            session_state: Mutable session state dict
            node_id      : The node that was answered
            raw_answer   : The patient's raw answer

        Returns:
            Updated session_state
        """
        weights = self._load_weights()
        nodes   = self._load_nodes()

        node = nodes.get(node_id)
        if node is None:
            logger.warning("update_scores: unknown node_id '%s'", node_id)
            return session_state

        weight_val = normalise_answer(raw_answer, node["ui_type"])

        # Initialise scores dict if absent
        if "scores" not in session_state:
            session_state["scores"] = {}

        node_weights = weights.get(node_id, {})
        for syndrome_id, w in node_weights.items():
            F = w["frequency"]
            E = w["evoking_strength"]
            direction = 1 if w["answer_direction"] == "POSITIVE" else -1
            delta = F * E * weight_val * direction

            prev = session_state["scores"].get(syndrome_id, 0.0)
            session_state["scores"][syndrome_id] = prev + delta

        # Store the answer
        if "answers" not in session_state:
            session_state["answers"] = {}
        session_state["answers"][node_id] = raw_answer

        # Track asked nodes
        if "asked" not in session_state:
            session_state["asked"] = []
        if node_id not in session_state["asked"]:
            session_state["asked"].append(node_id)

        return session_state

    # -----------------------------------------------------------------------
    # Public: Get active syndromes (score >= threshold)
    # -----------------------------------------------------------------------

    def get_active_syndromes(
        self,
        session_state: dict,
        threshold: float = MIN_SYNDROME_SCORE,
    ) -> dict:
        """
        Return syndromes with a score at or above `threshold`.

        If no syndromes meet the threshold, return all syndromes with
        the highest scores (at least MIN_ACTIVE_SYNDROMES) to prevent
        the engine from running out of candidates.

        Returns:
            Dict {syndrome_id: score} for active syndromes
        """
        scores = session_state.get("scores", {})
        if not scores:
            # Before any answers: all syndromes are equally active
            all_syn = fetch_all("SELECT syndrome_id FROM syndromes",
                                db_path=self.db_path)
            return {row["syndrome_id"]: 0.0 for row in all_syn}

        active = {sid: sc for sid, sc in scores.items() if sc >= threshold}

        if len(active) < MIN_ACTIVE_SYNDROMES:
            # Fallback: take top N by score
            sorted_all = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            active = {sid: sc for sid, sc in sorted_all[:max(5, MIN_ACTIVE_SYNDROMES)]}

        return active

    # -----------------------------------------------------------------------
    # Public: Compute top probability
    # -----------------------------------------------------------------------

    def get_top_probability(self, session_state: dict) -> tuple[str, float]:
        """
        Compute the softmax-normalised probability of the top syndrome.

        Returns:
            (top_syndrome_id, probability_0_to_1)
        """
        scores = session_state.get("scores", {})
        if not scores:
            return ("", 0.0)

        # Clamp scores to avoid exp overflow: subtract max (log-sum-exp trick)
        max_score = max(scores.values())
        exp_scores = {sid: math.exp(min(sc - max_score, 700)) for sid, sc in scores.items()}
        total = sum(exp_scores.values())
        if total == 0:
            return ("", 0.0)

        probs = {sid: v / total for sid, v in exp_scores.items()}
        top_sid = max(probs, key=probs.get)
        return (top_sid, probs[top_sid])

    # -----------------------------------------------------------------------
    # Core: Get the next best question (argmax σ²(E))
    # -----------------------------------------------------------------------

    def get_next_best_question(
        self,
        session_state: dict,
        framework: str,
        phase_override: Optional[int] = None,
    ) -> Optional[str]:
        """
        Select the next question node that maximises the VARIANCE of Evoking
        Strength across the active syndrome set.

        Steps:
          1. Get active syndromes (high-score candidates)
          2. For each unasked node (in the correct framework/phase):
               collect E-values across active syndromes
               compute σ²(E)
          3. Return the node_id with the highest σ²(E)
             Tie-break: mandatory nodes first, then display_order

        Args:
            session_state  : Current session state
            framework      : Active framework (SOCRATES, OLD_CARTS, etc.)
            phase_override : If set, restrict to this phase number

        Returns:
            node_id str, or None if no more questions available
        """
        weights = self._load_weights()
        nodes   = self._load_nodes()
        asked   = set(session_state.get("asked", []))
        active  = self.get_active_syndromes(session_state)

        if not active:
            return None

        active_sids = set(active.keys())

        best_node_id: Optional[str] = None
        best_variance: float        = 0.0
        best_mandatory: bool        = False
        best_order: int             = 9999

        for node_id, node in nodes.items():
            # Skip already asked nodes
            if node_id in asked:
                continue

            # Skip triage nodes in the entropy loop
            if node["framework"] == "TRIAGE":
                continue

            # Framework filter: allow ROS and PMH nodes regardless,
            # but primary framework nodes must match
            node_fw = node["framework"]
            if node_fw not in (framework, "ROS", "PMH"):
                continue

            # Phase override (used during triage to restrict to phase 1)
            if phase_override is not None and node["phase"] != phase_override:
                continue

            # Collect Evoking Strength values across ACTIVE syndromes
            e_values = []
            node_weights = weights.get(node_id, {})
            for sid in active_sids:
                if sid in node_weights:
                    e_values.append(node_weights[sid]["evoking_strength"])
                else:
                    e_values.append(0)  # Node has no weight for this syndrome

            if not e_values:
                continue

            variance = self._variance(e_values)

            is_mandatory = bool(node.get("is_mandatory", 0))
            order        = node.get("display_order", 9999)

            if variance == 0.0 and not is_mandatory:
                continue

            # Select node with highest variance
            # Mandatory nodes always beat non-mandatory with same variance
            if variance > best_variance or (
                is_mandatory and not best_mandatory and variance >= best_variance * 0.9
            ) or (
                variance == best_variance and order < best_order
            ):
                best_variance  = variance
                best_node_id   = node_id
                best_mandatory = is_mandatory
                best_order     = order

        if best_node_id is None:
            logger.debug("No more questions available for framework '%s'", framework)

        return best_node_id

    # -----------------------------------------------------------------------
    # Public: Check termination condition
    # -----------------------------------------------------------------------

    def check_termination(
        self,
        session_state: dict,
        prev_top_prob: float,
        new_top_prob: float,
    ) -> tuple[bool, str]:
        """
        Evaluate whether the engine should stop asking questions.

        Termination conditions (in priority order):
          1. questions_asked >= MAX_QUESTIONS         → MAX_REACHED
          2. |new_top_prob - prev_top_prob| < 0.02   → FLATTENING_CURVE
          3. new_top_prob >= 0.90                     → HIGH_CONFIDENCE

        Args:
            session_state  : Current session state
            prev_top_prob  : Top probability before last question
            new_top_prob   : Top probability after last question

        Returns:
            (should_stop: bool, reason: str)
        """
        # Triage nodes don't count towards the 12 clinical questions limit
        asked_clinical = [n for n in session_state.get("asked", []) if not n.startswith("T0")]
        asked_count = len(asked_clinical)

        if asked_count >= MAX_QUESTIONS:
            return True, "MAX_REACHED"

        delta = abs(new_top_prob - prev_top_prob)
        if delta < FLATTENING_THRESHOLD and asked_count >= 4:
            # Only apply flattening curve after at least 4 questions
            return True, "FLATTENING_CURVE"

        if new_top_prob >= 0.90 and asked_count >= 6:
            # Very high confidence reached
            return True, "HIGH_CONFIDENCE"

        return False, "CONTINUE"

    # -----------------------------------------------------------------------
    # Public: Build ranked differential diagnosis
    # -----------------------------------------------------------------------

    def build_differential(
        self, session_state: dict, top_n: int = 10
    ) -> list[dict]:
        """
        Produce a ranked list of syndromes with softmax probabilities.

        Returns:
            List of dicts sorted by probability descending:
            [
              {"syndrome_id": str, "name": str, "icd10": str,
               "category": str, "severity_tier": int,
               "score": float, "probability": float},
              ...
            ]
        """
        scores = session_state.get("scores", {})
        if not scores:
            return []

        # Fetch syndrome metadata
        syn_rows = fetch_all(
            "SELECT syndrome_id, name, icd10, category, severity_tier FROM syndromes",
            db_path=self.db_path,
        )
        syn_meta = {row["syndrome_id"]: dict(row) for row in syn_rows}

        # Softmax probabilities
        max_score = max(scores.values())
        exp_scores = {
            sid: math.exp(min(sc - max_score, 700))
            for sid, sc in scores.items()
        }
        total = sum(exp_scores.values()) or 1.0

        results = []
        for sid, exp_val in exp_scores.items():
            meta = syn_meta.get(sid, {})
            results.append({
                "syndrome_id":  sid,
                "name":         meta.get("name", sid),
                "icd10":        meta.get("icd10", ""),
                "category":     meta.get("category", ""),
                "severity_tier":meta.get("severity_tier", 2),
                "score":        round(scores.get(sid, 0.0), 4),
                "probability":  round(exp_val / total, 4),
            })

        results.sort(key=lambda x: x["probability"], reverse=True)
        return results[:top_n]

    # -----------------------------------------------------------------------
    # Internal: Variance calculation (no numpy – zero-dependency)
    # -----------------------------------------------------------------------

    @staticmethod
    def _variance(values: list[float]) -> float:
        """
        Population variance σ² = (1/N) × Σ(x - μ)²
        Pure Python – no numpy required for offline deployment.
        """
        n = len(values)
        if n == 0:
            return 0.0
        mean = sum(values) / n
        return sum((v - mean) ** 2 for v in values) / n
