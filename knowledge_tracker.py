from typing import Set, Tuple, List, Dict, Optional
import copy

from difficulty import DifficultyConfig
from config import RANK_COUNTS, ALL_RANKS, COLORS_BY_LEVEL


class KnowledgeTracker:
    """
    Tracks what a player knows about each card in their own hand.

    For each card_id, maintains a set of possible (color, rank) identities.
    Possibilities shrink as hints are applied and public information is observed.

    The AI's tracker also accounts for cards it can see in the human's hand,
    giving it stronger inference than a human player.
    """

    def __init__(self, player_id: int, num_colors: int, config: DifficultyConfig):
        self.player_id = player_id
        self.config = config
        self.colors = COLORS_BY_LEVEL[config.level]

        # All possible (color, rank) pairs in the game, with multiplicity
        self._full_deck: List[Tuple[str, int]] = []
        for color in self.colors:
            for rank, count in RANK_COUNTS.items():
                for _ in range(count):
                    self._full_deck.append((color, rank))

        # card_id -> set of possible (color, rank) tuples
        self._possibilities: Dict[int, Set[Tuple[str, int]]] = {}

        # Public knowledge: cards that have been removed from the deck publicly
        # (played successfully, discarded, or visible in another player's hand)
        self._public_removed: List[Tuple[str, int]] = []

        # Card IDs currently in hand (ordered)
        self._hand_order: List[int] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_card(self, card_id: int) -> None:
        """Register a newly drawn card. Possibilities start as everything not publicly visible."""
        self._hand_order.append(card_id)
        self._possibilities[card_id] = self._compute_initial_possibilities()

    def remove_card(self, card_id: int) -> None:
        """Remove a card from the hand (played or discarded)."""
        self._possibilities.pop(card_id, None)
        if card_id in self._hand_order:
            self._hand_order.remove(card_id)

    def apply_hint(self, hint_type: str, hint_value, matching_ids: List[int]) -> None:
        """
        Update possibilities based on a hint received.
        matching_ids: card_ids in this player's hand that match the hint.
        """
        for card_id, possibilities in self._possibilities.items():
            if card_id in matching_ids:
                # This card IS the hinted color/rank — eliminate non-matching possibilities
                if hint_type == 'color':
                    self._possibilities[card_id] = {
                        (c, r) for (c, r) in possibilities if c == hint_value
                    }
                else:  # rank
                    self._possibilities[card_id] = {
                        (c, r) for (c, r) in possibilities if r == hint_value
                    }
            else:
                # This card is NOT the hinted color/rank — eliminate matching possibilities
                if hint_type == 'color':
                    self._possibilities[card_id] = {
                        (c, r) for (c, r) in possibilities if c != hint_value
                    }
                else:  # rank
                    self._possibilities[card_id] = {
                        (c, r) for (c, r) in possibilities if r != hint_value
                    }

    def get_possibilities(self, card_id: int) -> Set[Tuple[str, int]]:
        """Return the set of possible (color, rank) identities for a card."""
        return set(self._possibilities.get(card_id, set()))

    def is_definitely_playable(self, card_id: int, fireworks: dict) -> bool:
        """Return True if ALL possibilities for this card are immediately playable."""
        possibilities = self._possibilities.get(card_id)
        if not possibilities:
            return False
        return all(
            fireworks.get(color, 0) == rank - 1
            for (color, rank) in possibilities
        )

    def is_definitely_useless(self, card_id: int, fireworks: dict) -> bool:
        """
        Return True if ALL possibilities for this card are definitively useless.
        A card is useless if its rank is already played (rank <= fireworks[color])
        OR all copies of that identity have been publicly removed.
        """
        possibilities = self._possibilities.get(card_id)
        if not possibilities:
            return False

        for (color, rank) in possibilities:
            if not self._is_identity_useless(color, rank, fireworks):
                return False
        return True

    def get_knowledge_summary(self) -> dict:
        """Return a summary of knowledge suitable for LLM context."""
        summary = {}
        for i, card_id in enumerate(self._hand_order):
            possibilities = self._possibilities.get(card_id, set())
            colors = sorted(set(c for c, r in possibilities))
            ranks = sorted(set(r for c, r in possibilities))
            summary[f'card_{i+1}'] = {
                'card_id': card_id,
                'possible_colors': colors,
                'possible_ranks': ranks,
                'num_possibilities': len(possibilities),
            }
        return summary

    def observe_public_card(self, color: str, rank: int) -> None:
        """
        Record a card that has become publicly visible (discarded, played by opponent,
        or visible in another player's hand). Updates internal possibilities.
        """
        self._public_removed.append((color, rank))
        # Recompute all possibilities since the pool has shrunk
        for card_id in self._possibilities:
            # Remove this specific identity if its count is now exhausted
            self._possibilities[card_id] = {
                (c, r) for (c, r) in self._possibilities[card_id]
                if self._is_still_possible(c, r)
            }

    def clone(self) -> 'KnowledgeTracker':
        """Return a deep copy of this tracker (used by Predict phase)."""
        new_tracker = KnowledgeTracker.__new__(KnowledgeTracker)
        new_tracker.player_id = self.player_id
        new_tracker.config = self.config
        new_tracker.colors = self.colors
        new_tracker._full_deck = list(self._full_deck)
        new_tracker._possibilities = {k: set(v) for k, v in self._possibilities.items()}
        new_tracker._public_removed = list(self._public_removed)
        new_tracker._hand_order = list(self._hand_order)
        return new_tracker

    def get_hand_order(self) -> List[int]:
        """Return card_ids in hand order."""
        return list(self._hand_order)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_initial_possibilities(self) -> Set[Tuple[str, int]]:
        """
        All (color, rank) pairs still possible given public information.
        Start from the full deck and remove publicly known cards.
        """
        available: List[Tuple[str, int]] = list(self._full_deck)
        for identity in self._public_removed:
            if identity in available:
                available.remove(identity)
        return set(available)

    def _is_still_possible(self, color: str, rank: int) -> bool:
        """Check if a (color, rank) identity is still possible given public removals."""
        total = RANK_COUNTS.get(rank, 0)
        removed_count = sum(1 for (c, r) in self._public_removed if c == color and r == rank)
        return removed_count < total

    def _is_identity_useless(self, color: str, rank: int, fireworks: dict) -> bool:
        """Return True if this specific (color, rank) can never contribute to the score."""
        # Already played at this rank or beyond
        if fireworks.get(color, 0) >= rank:
            return True
        # All copies have been publicly removed (discarded or played — can't recover)
        total = RANK_COUNTS.get(rank, 0)
        removed = sum(1 for (c, r) in self._public_removed if c == color and r == rank)
        if removed >= total:
            return True
        return False
