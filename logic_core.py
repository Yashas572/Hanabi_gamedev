from enum import Enum
from typing import Dict, List, Optional, Tuple
import random
import math

from game_engine import GameState, Card
from knowledge_tracker import KnowledgeTracker
from difficulty import DifficultyConfig
from config import HUMAN, AI, RANK_COUNTS


# ---------------------------------------------------------------------------
# Intent Enum
# ---------------------------------------------------------------------------

class Intent(Enum):
    PLAY = 'play'            # Card is immediately playable
    DISCARD = 'discard'      # Card is definitively useless
    MAYDISCARD = 'maydiscard'  # Card is expendable or a duplicate exists
    KEEP = 'keep'            # All other cards


# ---------------------------------------------------------------------------
# LogicCore
# ---------------------------------------------------------------------------

class LogicCore:
    """
    Implements the three-phase Intentional AI algorithm:
      1. CalculateIntentions  — what the AI wants the human to do with each card
      2. Predict              — what the human will actually do after a hint
      3. Compare              — score a hint by comparing intentions vs predictions

    All methods are deterministic (no LLM calls). The chatbot uses the reason
    strings returned here to generate natural language explanations.
    """

    def __init__(self, config: DifficultyConfig):
        self.config = config
        self._last_reason: str = ""

    # ------------------------------------------------------------------
    # Phase 1: CalculateIntentions
    # ------------------------------------------------------------------

    def calculate_intentions(self, game_state: GameState) -> Dict[int, Intent]:
        """
        For each card in the HUMAN player's hand (which the AI can see),
        determine what the AI intends the human should do with it.
        Returns Dict[card_id -> Intent].
        """
        human_hand = game_state.hands[HUMAN]
        fireworks = game_state.fireworks
        discard_pile = game_state.discard_pile
        intentions: Dict[int, Intent] = {}

        for card in human_hand:
            intent = self._classify_card(card, human_hand, fireworks, discard_pile)
            intentions[card.card_id] = intent

        return intentions

    def _classify_card(
        self,
        card: Card,
        human_hand: List[Card],
        fireworks: dict,
        discard_pile: List[Card],
    ) -> Intent:
        color, rank = card.color, card.rank

        # PLAY: card is the next needed in its color sequence
        if fireworks.get(color, 0) == rank - 1:
            return Intent.PLAY

        # DISCARD: card's rank is already at or below what's been played
        if rank <= fireworks.get(color, 0):
            return Intent.DISCARD

        # DISCARD: all copies of this card are already in the discard pile
        total_copies = RANK_COUNTS.get(rank, 0)
        discarded_copies = sum(
            1 for dc in discard_pile if dc.color == color and dc.rank == rank
        )
        if discarded_copies >= total_copies:
            return Intent.DISCARD

        # MAYDISCARD: another identical card exists in the human's hand
        duplicates_in_hand = sum(
            1 for hc in human_hand if hc.color == color and hc.rank == rank
        )
        if duplicates_in_hand > 1:
            return Intent.MAYDISCARD

        # MAYDISCARD: this exact card has already been successfully played (fireworks >= rank)
        # (Already covered by the DISCARD branch above, so this case won't be reached)

        return Intent.KEEP

    # ------------------------------------------------------------------
    # Phase 2: Predict
    # ------------------------------------------------------------------

    def predict(
        self,
        hint_action: dict,
        human_knowledge: KnowledgeTracker,
        fireworks: dict,
    ) -> Dict[int, str]:
        """
        Simulate what the human will do after receiving a hint.
        Clones the human's KnowledgeTracker, applies the hint, then predicts
        PLAY / DISCARD / KEEP for each card based on updated knowledge.
        Returns Dict[card_id -> predicted_action_str].
        """
        cloned = human_knowledge.clone()

        # Find matching card_ids for this hint
        hint_type = hint_action['hint_type']
        hint_value = hint_action['hint_value']
        target_hand_ids = cloned.get_hand_order()

        # The matching_ids are those whose actual identity matches the hint.
        # We simulate this from the AI's full knowledge — the AI knows which cards match.
        # (In practice this is passed in via game_state; we accept it via hint_action metadata.)
        matching_ids = hint_action.get('_matching_ids', [])

        cloned.apply_hint(hint_type, hint_value, matching_ids)

        predictions: Dict[int, str] = {}
        for card_id in target_hand_ids:
            if cloned.is_definitely_playable(card_id, fireworks):
                predictions[card_id] = 'play'
            elif cloned.is_definitely_useless(card_id, fireworks):
                predictions[card_id] = 'discard'
            else:
                predictions[card_id] = 'keep'

        return predictions

    # ------------------------------------------------------------------
    # Phase 3: Compare
    # ------------------------------------------------------------------

    def compare(
        self,
        intentions: Dict[int, Intent],
        predictions: Dict[int, str],
    ) -> float:
        """
        Score a hint by comparing intended vs predicted actions.
        Returns -infinity if any card would be wrongly played or wrongly discarded.
        """
        cfg = self.config
        score = 0.0

        for card_id, prediction in predictions.items():
            intent = intentions.get(card_id, Intent.KEEP)

            if intent == Intent.PLAY and prediction == 'play':
                score += cfg.score_correct_play
            elif intent == Intent.DISCARD and prediction == 'discard':
                score += cfg.score_correct_discard
            elif intent == Intent.MAYDISCARD and prediction == 'discard':
                score += cfg.score_correct_maydiscard
            elif intent == Intent.KEEP and prediction == 'play':
                return -math.inf   # REJECT: hint would cause a wrong play
            elif intent == Intent.KEEP and prediction == 'discard':
                return -math.inf   # REJECT: hint would cause a wrong discard
            # No change predicted (keep when intended keep, etc.) → 0

        return score

    # ------------------------------------------------------------------
    # Best hint selection
    # ------------------------------------------------------------------

    def _best_hint(
        self,
        game_state: GameState,
        human_knowledge: KnowledgeTracker,
    ) -> Optional[Tuple[dict, float, str]]:
        """
        Evaluate all legal hints from AI -> Human.
        Returns (best_action_dict, score, reason) or None if no positive hint exists.
        """
        if game_state.hint_tokens <= 0:
            return None

        intentions = self.calculate_intentions(game_state)
        human_hand = game_state.hands[HUMAN]
        fireworks = game_state.fireworks

        # Collect unique hints
        colors_in_hand = set(c.color for c in human_hand)
        ranks_in_hand = set(c.rank for c in human_hand)

        candidates: List[Tuple[dict, float, str]] = []

        for hint_type, values in [('color', colors_in_hand), ('rank', ranks_in_hand)]:
            for value in values:
                # Compute matching card_ids
                matching_ids = [
                    c.card_id for c in human_hand
                    if (hint_type == 'color' and c.color == value)
                    or (hint_type == 'rank' and c.rank == value)
                ]
                action = {
                    'type': 'hint',
                    'target_player': HUMAN,
                    'hint_type': hint_type,
                    'hint_value': value,
                    '_matching_ids': matching_ids,
                }
                predictions = self.predict(action, human_knowledge, fireworks)
                score = self.compare(intentions, predictions)

                if score > -math.inf:
                    reason = self._build_hint_reason(action, intentions, matching_ids)
                    candidates.append((action, score, reason))

        if not candidates:
            return None

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Easy mode: 30% of the time pick second-best (if available)
        if not self.config.ai_plays_optimally and len(candidates) > 1:
            if random.random() < 0.30:
                return candidates[1]

        return candidates[0]

    # ------------------------------------------------------------------
    # AI Turn Decision Pipeline (Section 5.5)
    # ------------------------------------------------------------------

    def decide_action(
        self,
        game_state: GameState,
        ai_knowledge: KnowledgeTracker,
    ) -> dict:
        """
        Four-step decision pipeline:
          1. Play a definitely-playable card from AI's own knowledge.
          2. Discard a definitely-useless card (only if hint_tokens < max).
          3. Give the best hint to the human — gated by difficulty:
               Easy   (65% chance, min score 3):  hints fairly liberally
               Medium (30% chance, min score 8):  only high-value hints
               Hard   (0% chance):                never auto-hints
             The human can always request a hint at any time via the chat.
          4. Discard the chop card (lowest-value / oldest).
        Returns an action dict.
        """
        cfg = self.config
        fireworks = game_state.fireworks
        ai_hand = game_state.hands[AI]
        ai_hand_ids = ai_knowledge.get_hand_order()

        # Step 1: Play a definitely-playable card
        for card_id in ai_hand_ids:
            if ai_knowledge.is_definitely_playable(card_id, fireworks):
                idx = self._card_id_to_index(card_id, ai_hand)
                if idx is not None:
                    self._last_reason = (
                        f"I know my card at position {idx+1} is definitely playable."
                    )
                    return {'type': 'play', 'card_index': idx}

        # Step 2: Discard a definitely-useless card (only when hint tokens aren't maxed)
        if game_state.hint_tokens < cfg.max_hints:
            for card_id in ai_hand_ids:
                if ai_knowledge.is_definitely_useless(card_id, fireworks):
                    idx = self._card_id_to_index(card_id, ai_hand)
                    if idx is not None:
                        self._last_reason = (
                            f"My card at position {idx+1} is definitely useless, so I'll discard it "
                            f"to gain a hint token."
                        )
                        return {'type': 'discard', 'card_index': idx}

        # Step 3: Conditionally give the best hint — controlled by difficulty
        hint_prob = cfg.ai_hint_probability
        hint_min  = cfg.ai_hint_min_score
        if hint_prob > 0 and game_state.hint_tokens > 0 and random.random() < hint_prob:
            human_knowledge = self._get_human_knowledge_from_state(game_state)
            best = self._best_hint(game_state, human_knowledge)
            if best is not None:
                action, score, reason = best
                if score >= hint_min:
                    self._last_reason = reason
                    clean = {k: v for k, v in action.items() if not k.startswith('_')}
                    return clean

        # Step 4: Discard chop (oldest card = index 0)
        self._last_reason = (
            "No safe plays right now, so I'll discard my oldest card."
        )
        return {'type': 'discard', 'card_index': 0}

    def best_hint_for_human(
        self,
        game_state: GameState,
        human_knowledge: KnowledgeTracker,
    ) -> Optional[Tuple[dict, str]]:
        """
        Find the best hint the AI can give to the human right now.
        Called when the human requests a hint via the chatbot.
        Returns (clean_action_dict, reason_str) or None if no good hint exists.
        """
        result = self._best_hint(game_state, human_knowledge)
        if result is None:
            return None
        action, _score, reason = result
        self._last_reason = reason
        clean = {k: v for k, v in action.items() if not k.startswith('_')}
        return clean, reason

    # ------------------------------------------------------------------
    # Coach mode (Section 5.6)
    # ------------------------------------------------------------------

    def coach_human(
        self,
        game_state: GameState,
        human_knowledge: KnowledgeTracker,
    ) -> dict:
        """
        Run the same decision pipeline but from the human's perspective.
        Returns {'action': action_dict, 'reason': str}.
        """
        fireworks = game_state.fireworks
        human_hand = game_state.hands[HUMAN]
        human_hand_ids = human_knowledge.get_hand_order()

        # Step 1: Play a definitely-playable card
        for card_id in human_hand_ids:
            if human_knowledge.is_definitely_playable(card_id, fireworks):
                idx = self._card_id_to_index(card_id, human_hand)
                if idx is not None:
                    return {
                        'action': {'type': 'play', 'card_index': idx},
                        'reason': (
                            f"Your card at position {idx+1} is definitely playable based on "
                            f"what you've been told. Playing it will advance the fireworks."
                        ),
                    }

        # Step 2: Discard a definitely-useless card
        if game_state.hint_tokens < self.config.max_hints:
            for card_id in human_hand_ids:
                if human_knowledge.is_definitely_useless(card_id, fireworks):
                    idx = self._card_id_to_index(card_id, human_hand)
                    if idx is not None:
                        return {
                            'action': {'type': 'discard', 'card_index': idx},
                            'reason': (
                                f"Your card at position {idx+1} is definitely useless given "
                                f"the current fireworks state. Discarding it will give us a "
                                f"hint token."
                            ),
                        }

        # From the AI's full view: look for playable cards in the human's hand
        for i, card in enumerate(human_hand):
            if fireworks.get(card.color, 0) == card.rank - 1:
                return {
                    'action': {'type': 'play', 'card_index': i},
                    'reason': (
                        f"Your card at position {i+1} is playable! "
                        f"I can see it's {card.color}{card.rank} and the fireworks need it next."
                    ),
                }

        # Hint if possible
        if game_state.hint_tokens > 0:
            return {
                'action': {'type': 'hint', 'target_player': AI, 'hint_type': 'rank', 'hint_value': 1},
                'reason': (
                    "No immediately safe plays or discards for you. Consider giving me a hint "
                    "or waiting for more information."
                ),
            }

        # Discard chop
        return {
            'action': {'type': 'discard', 'card_index': 0},
            'reason': (
                "No hints available and no safe plays. Discard your oldest card (position 1) "
                "to gain a hint token."
            ),
        }

    def get_last_reason(self) -> str:
        return self._last_reason

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _card_id_to_index(self, card_id: int, hand: List[Card]) -> Optional[int]:
        for i, card in enumerate(hand):
            if card.card_id == card_id:
                return i
        return None

    def _build_hint_reason(
        self,
        action: dict,
        intentions: Dict[int, Intent],
        matching_ids: List[int],
    ) -> str:
        hint_type = action['hint_type']
        hint_value = action['hint_value']
        intents_for_hint = [intentions.get(cid) for cid in matching_ids]

        if Intent.PLAY in intents_for_hint:
            return (
                f"I'm hinting {hint_type}={hint_value} to signal that your matching card(s) "
                f"are playable right now."
            )
        if Intent.DISCARD in intents_for_hint or Intent.MAYDISCARD in intents_for_hint:
            return (
                f"I'm hinting {hint_type}={hint_value} to help you identify cards that are "
                f"safe to discard."
            )
        return f"I'm hinting {hint_type}={hint_value} to give you useful information."

    def _get_human_knowledge_from_state(self, game_state: GameState) -> KnowledgeTracker:
        """
        Build a fresh KnowledgeTracker for the human based on public information.
        This simulates what the human knows without the AI's full-state advantage.
        """
        tracker = KnowledgeTracker(
            player_id=HUMAN,
            num_colors=self.config.num_colors,
            config=self.config,
        )
        # Register all cards in the human's hand (in order)
        for card in game_state.hands[HUMAN]:
            tracker.add_card(card.card_id)
        return tracker
