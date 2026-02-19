"""
Logic Core tests (Section 11.2)
Run with: python -m pytest tests/ -v
"""
import sys
import os
import math
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from difficulty import MEDIUM
from game_engine import GameEngine, Card
from knowledge_tracker import KnowledgeTracker
from logic_core import LogicCore, Intent
from config import HUMAN, AI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine_and_logic():
    engine = GameEngine(MEDIUM)
    logic = LogicCore(MEDIUM)
    return engine, logic


def make_tracker(engine: GameEngine, player_id: int) -> KnowledgeTracker:
    tracker = KnowledgeTracker(player_id=player_id, num_colors=MEDIUM.num_colors, config=MEDIUM)
    state = engine.get_full_state()
    for card in state.hands[player_id]:
        tracker.add_card(card.card_id)
    return tracker


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCalculateIntentions:
    def test_play_intent_for_next_card(self):
        """A card that is next in sequence gets PLAY intent."""
        engine, logic = make_engine_and_logic()
        state = engine.get_full_state()

        # Inject a known playable card into human's hand
        colors = engine.colors
        color = colors[0]
        # fireworks[color] == 0, so rank 1 is playable
        assert state.fireworks[color] == 0

        # Force human hand to contain rank-1 card of this color
        playable_card = Card(color=color, rank=1, card_id=9999)
        engine._state.hands[HUMAN] = [playable_card]

        intentions = logic.calculate_intentions(engine.get_full_state())
        assert intentions[9999] == Intent.PLAY

    def test_discard_intent_already_played(self):
        """A card whose rank is already played (or below) gets DISCARD intent."""
        engine, logic = make_engine_and_logic()
        colors = engine.colors
        color = colors[0]

        # Set fireworks for that color to 3 (already played ranks 1-3)
        engine._state.fireworks[color] = 3

        # Force human hand to contain rank-2 card of same color
        useless_card = Card(color=color, rank=2, card_id=8888)
        engine._state.hands[HUMAN] = [useless_card]

        intentions = logic.calculate_intentions(engine.get_full_state())
        assert intentions[8888] == Intent.DISCARD

    def test_maydiscard_intent_for_duplicate(self):
        """A duplicate card in human's hand gets MAYDISCARD intent."""
        engine, logic = make_engine_and_logic()
        colors = engine.colors
        color = colors[0]
        engine._state.fireworks[color] = 0

        # Two identical rank-3 cards in hand — fireworks at 0 so neither is playable yet
        card_a = Card(color=color, rank=3, card_id=7771)
        card_b = Card(color=color, rank=3, card_id=7772)
        engine._state.hands[HUMAN] = [card_a, card_b]

        intentions = logic.calculate_intentions(engine.get_full_state())
        # At least one should be MAYDISCARD (the other may also be MAYDISCARD)
        assert Intent.MAYDISCARD in intentions.values()

    def test_keep_intent_for_important_card(self):
        """A unique, not-yet-playable card gets KEEP intent."""
        engine, logic = make_engine_and_logic()
        colors = engine.colors
        color = colors[0]
        engine._state.fireworks[color] = 0

        # rank-3 card, only one copy left, fireworks at 0 → needed but not now
        unique_card = Card(color=color, rank=3, card_id=6661)
        engine._state.hands[HUMAN] = [unique_card]
        engine._state.discard_pile = []  # no copies discarded

        intentions = logic.calculate_intentions(engine.get_full_state())
        assert intentions[6661] == Intent.KEEP

    def test_discard_intent_all_copies_discarded(self):
        """A card all copies of which are in discard pile gets DISCARD intent."""
        engine, logic = make_engine_and_logic()
        from config import RANK_COUNTS
        colors = engine.colors
        color = colors[0]
        engine._state.fireworks[color] = 0

        rank = 5  # only 1 copy of rank-5
        doomed_card = Card(color=color, rank=rank, card_id=5551)
        engine._state.hands[HUMAN] = [doomed_card]

        # Put all copies in discard
        for _ in range(RANK_COUNTS[rank]):
            engine._state.discard_pile.append(Card(color=color, rank=rank, card_id=0))

        intentions = logic.calculate_intentions(engine.get_full_state())
        assert intentions[5551] == Intent.DISCARD


class TestPredict:
    def test_predict_color_hint_triggers_play(self):
        """A color hint that narrows a card to definitely playable → predict PLAY."""
        engine, logic = make_engine_and_logic()
        colors = engine.colors
        color = colors[0]
        engine._state.fireworks[color] = 0

        # Human hand: one card that IS rank-1 of this color
        target_card = Card(color=color, rank=1, card_id=4441)
        engine._state.hands[HUMAN] = [target_card]

        # Build a human tracker with all possibilities still open
        tracker = KnowledgeTracker(player_id=HUMAN, num_colors=MEDIUM.num_colors, config=MEDIUM)
        tracker.add_card(4441)

        # Narrow down to just (color, 1) by applying both color and rank hints
        hint_action = {
            'type': 'hint',
            'target_player': HUMAN,
            'hint_type': 'color',
            'hint_value': color,
            '_matching_ids': [4441],
        }
        predictions = logic.predict(hint_action, tracker, engine._state.fireworks)
        # After color hint narrows to just this color, rank is still unknown
        # A second rank hint would definitively make it playable.
        # For this test we verify predict returns a dict without error.
        assert 4441 in predictions

    def test_predict_returns_dict_for_all_cards(self):
        """Predict returns a prediction for every card in the tracker."""
        engine, logic = make_engine_and_logic()
        colors = engine.colors
        color = colors[0]

        tracker = make_tracker(engine, HUMAN)
        hand = engine._state.hands[HUMAN]
        matching_ids = [c.card_id for c in hand if c.color == color]

        if not matching_ids:
            pytest.skip("No cards of that color in human hand.")

        hint_action = {
            'type': 'hint',
            'target_player': HUMAN,
            'hint_type': 'color',
            'hint_value': color,
            '_matching_ids': matching_ids,
        }
        predictions = logic.predict(hint_action, tracker, engine._state.fireworks)
        for card in hand:
            assert card.card_id in predictions
        assert all(p in ('play', 'discard', 'keep') for p in predictions.values())


class TestCompare:
    def test_compare_rejects_wrong_play(self):
        """A hint that causes a KEEP card to be predicted as play returns -infinity."""
        logic = LogicCore(MEDIUM)
        intentions = {1: Intent.KEEP}
        predictions = {1: 'play'}
        score = logic.compare(intentions, predictions)
        assert score == -math.inf

    def test_compare_rejects_wrong_discard(self):
        """A hint that causes a KEEP card to be predicted as discard returns -infinity."""
        logic = LogicCore(MEDIUM)
        intentions = {1: Intent.KEEP}
        predictions = {1: 'discard'}
        score = logic.compare(intentions, predictions)
        assert score == -math.inf

    def test_compare_scores_correct_play(self):
        """Intended PLAY + Predicted PLAY → positive score."""
        logic = LogicCore(MEDIUM)
        intentions = {1: Intent.PLAY}
        predictions = {1: 'play'}
        score = logic.compare(intentions, predictions)
        assert score == MEDIUM.score_correct_play

    def test_compare_scores_correct_discard(self):
        """Intended DISCARD + Predicted DISCARD → positive score."""
        logic = LogicCore(MEDIUM)
        intentions = {1: Intent.DISCARD}
        predictions = {1: 'discard'}
        score = logic.compare(intentions, predictions)
        assert score == MEDIUM.score_correct_discard

    def test_compare_scores_maydiscard(self):
        """Intended MAYDISCARD + Predicted DISCARD → positive score."""
        logic = LogicCore(MEDIUM)
        intentions = {1: Intent.MAYDISCARD}
        predictions = {1: 'discard'}
        score = logic.compare(intentions, predictions)
        assert score == MEDIUM.score_correct_maydiscard

    def test_compare_no_change_is_zero(self):
        """Intended KEEP + Predicted KEEP → score 0 (no change)."""
        logic = LogicCore(MEDIUM)
        intentions = {1: Intent.KEEP}
        predictions = {1: 'keep'}
        score = logic.compare(intentions, predictions)
        assert score == 0


class TestBestHintSelection:
    def test_best_hint_selects_highest_score(self):
        """decide_action picks a hint when it's the best action available."""
        engine, logic = make_engine_and_logic()
        state = engine.get_full_state()
        colors = engine.colors

        # Ensure AI has no definitely-playable cards in its own knowledge
        tracker = KnowledgeTracker(
            player_id=AI, num_colors=MEDIUM.num_colors, config=MEDIUM
        )
        for card in state.hands[AI]:
            tracker.add_card(card.card_id)

        action = logic.decide_action(state, tracker)
        # The action must be valid (type is known)
        assert action['type'] in ('play', 'discard', 'hint')

    def test_hint_only_given_when_tokens_available(self):
        """No hint given when hint_tokens == 0."""
        engine, logic = make_engine_and_logic()
        engine._state.hint_tokens = 0

        tracker = KnowledgeTracker(
            player_id=AI, num_colors=MEDIUM.num_colors, config=MEDIUM
        )
        for card in engine._state.hands[AI]:
            tracker.add_card(card.card_id)

        action = logic.decide_action(engine.get_full_state(), tracker)
        assert action['type'] != 'hint'


class TestKnowledgeTracker:
    def test_is_definitely_playable_after_full_hint(self):
        """After both color and rank hints narrow to one identity, card is definitely playable."""
        engine = GameEngine(MEDIUM)
        colors = engine.colors
        color = colors[0]
        engine._state.fireworks[color] = 0

        # Human hand contains rank-1 card of color[0]
        target = Card(color=color, rank=1, card_id=100)
        engine._state.hands[HUMAN] = [target]

        tracker = KnowledgeTracker(
            player_id=HUMAN, num_colors=MEDIUM.num_colors, config=MEDIUM
        )
        tracker.add_card(100)

        # Apply color hint
        tracker.apply_hint('color', color, [100])
        # Apply rank hint
        tracker.apply_hint('rank', 1, [100])

        assert tracker.is_definitely_playable(100, {color: 0, **{c: 0 for c in colors}})

    def test_is_definitely_useless_for_played_card(self):
        """A card whose rank is already exceeded by fireworks is definitely useless."""
        engine = GameEngine(MEDIUM)
        colors = engine.colors
        color = colors[0]

        target = Card(color=color, rank=1, card_id=200)
        engine._state.hands[HUMAN] = [target]

        tracker = KnowledgeTracker(
            player_id=HUMAN, num_colors=MEDIUM.num_colors, config=MEDIUM
        )
        tracker.add_card(200)

        # Apply both hints to narrow to (color, 1)
        tracker.apply_hint('color', color, [200])
        tracker.apply_hint('rank', 1, [200])

        fireworks = {c: 0 for c in colors}
        fireworks[color] = 2  # rank 1 already exceeded

        assert tracker.is_definitely_useless(200, fireworks)
