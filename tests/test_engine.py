"""
Engine tests (Section 11.1)
Run with: python -m pytest tests/ -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from difficulty import EASY, MEDIUM, HARD
from game_engine import GameEngine
from config import HUMAN, AI, RANK_COUNTS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def easy_engine():
    return GameEngine(EASY)

@pytest.fixture
def medium_engine():
    return GameEngine(MEDIUM)

@pytest.fixture
def hard_engine():
    return GameEngine(HARD)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeckSize:
    def test_deck_size_easy(self, easy_engine):
        """Easy (3 colors) deck: 3 * 10 = 30 cards total, minus 5*2=10 dealt = 20 remaining."""
        state = easy_engine.get_full_state()
        # 3 colors × (3+2+2+2+1) = 30 cards total; 2 players × 5 = 10 dealt
        assert len(state.deck) == 30 - (EASY.hand_size * 2)

    def test_deck_size_medium(self, medium_engine):
        """Medium (4 colors) deck: 4 * 10 = 40 cards total."""
        state = medium_engine.get_full_state()
        assert len(state.deck) == 40 - (MEDIUM.hand_size * 2)

    def test_deck_size_hard(self, hard_engine):
        """Hard (5 colors) deck: 5 * 10 = 50 cards total."""
        state = hard_engine.get_full_state()
        assert len(state.deck) == 50 - (HARD.hand_size * 2)

    def test_full_deck_5_colors(self):
        """A 5-color deck has exactly 50 cards before dealing."""
        engine = GameEngine(HARD)
        # Count dealt + remaining
        state = engine.get_full_state()
        dealt = sum(len(h) for h in state.hands.values())
        total = len(state.deck) + dealt
        assert total == 50


class TestDeal:
    def test_deal_easy(self, easy_engine):
        state = easy_engine.get_full_state()
        assert len(state.hands[HUMAN]) == EASY.hand_size
        assert len(state.hands[AI]) == EASY.hand_size

    def test_deal_medium(self, medium_engine):
        state = medium_engine.get_full_state()
        assert len(state.hands[HUMAN]) == MEDIUM.hand_size
        assert len(state.hands[AI]) == MEDIUM.hand_size

    def test_deal_hard(self, hard_engine):
        state = hard_engine.get_full_state()
        assert len(state.hands[HUMAN]) == HARD.hand_size
        assert len(state.hands[AI]) == HARD.hand_size


class TestHintTokens:
    def test_hint_token_decrement(self, medium_engine):
        """Giving a hint reduces hint_tokens by 1."""
        state = medium_engine.get_full_state()
        initial = state.hint_tokens
        # Give a color hint from human to AI (find a valid color in AI's hand)
        ai_hand = state.hands[AI]
        color = ai_hand[0].color
        action = {'type': 'hint', 'target_player': AI, 'hint_type': 'color', 'hint_value': color}
        medium_engine.execute_action(HUMAN, action)
        assert medium_engine.get_full_state().hint_tokens == initial - 1

    def test_hint_rejected_at_zero_tokens(self):
        """ValueError raised when hint_tokens == 0."""
        engine = GameEngine(MEDIUM)
        # Drain all hints
        state = engine.get_full_state()
        tokens = state.hint_tokens
        # Use play/discard cycle to drain tokens if needed, or just force-set
        # We'll discard cards to gain tokens, then use those; simpler: patch state
        engine._state.hint_tokens = 0
        ai_hand = engine._state.hands[AI]
        color = ai_hand[0].color
        action = {'type': 'hint', 'target_player': AI, 'hint_type': 'color', 'hint_value': color}
        with pytest.raises(ValueError, match="hint_tokens"):
            engine.execute_action(HUMAN, action)

    def test_discard_increments_tokens(self, medium_engine):
        """Discarding a card adds a hint token (up to max)."""
        engine = medium_engine
        # Reduce hints so we're below max
        engine._state.hint_tokens = 5
        action = {'type': 'discard', 'card_index': 0}
        engine.execute_action(HUMAN, action)
        assert engine.get_full_state().hint_tokens == 6

    def test_discard_does_not_exceed_max(self, medium_engine):
        """Discarding when at max_hints does not exceed max (allowed in medium)."""
        engine = medium_engine
        engine._state.hint_tokens = MEDIUM.max_hints
        action = {'type': 'discard', 'card_index': 0}
        engine.execute_action(HUMAN, action)
        assert engine.get_full_state().hint_tokens == MEDIUM.max_hints


class TestFuseTokens:
    def test_fuse_decrement_on_wrong_play(self):
        """Playing a card with wrong rank decrements fuse_tokens."""
        engine = GameEngine(MEDIUM)
        state = engine.get_full_state()
        initial_fuses = state.fuse_tokens

        # Force a wrong play: set all fireworks to 5 for all colors except one,
        # then play a rank-1 card from a color whose firework is already > 0
        # Simplest: directly set fireworks and play a guaranteed wrong card
        engine._state.fireworks = {c: 3 for c in engine.colors}
        # Find a rank-1 card in human's hand
        human_hand = engine._state.hands[HUMAN]
        target_idx = None
        for i, card in enumerate(human_hand):
            if card.rank == 1:  # rank 1 while fireworks at 3 = wrong play
                target_idx = i
                break
        if target_idx is None:
            # Force it: set first card's rank to 1
            engine._state.hands[HUMAN][0] = engine._state.hands[HUMAN][0].__class__(
                color=engine._state.hands[HUMAN][0].color,
                rank=1,
                card_id=engine._state.hands[HUMAN][0].card_id,
            )
            target_idx = 0

        action = {'type': 'play', 'card_index': target_idx}
        result = engine.execute_action(HUMAN, action)
        assert result.mistake_made
        assert engine.get_full_state().fuse_tokens == initial_fuses - 1

    def test_game_over_on_fuse_zero(self):
        """game_over is True when fuse_tokens reaches 0."""
        engine = GameEngine(MEDIUM)
        engine._state.fuse_tokens = 1
        engine._state.fireworks = {c: 3 for c in engine.colors}
        # Force a bad play
        human_hand = engine._state.hands[HUMAN]
        # Find or force a rank-1 card in a color at fireworks=3
        for i, card in enumerate(human_hand):
            if engine._state.fireworks.get(card.color, 0) != card.rank - 1:
                engine.execute_action(HUMAN, {'type': 'play', 'card_index': i})
                break
        assert engine.get_full_state().game_over or engine.get_full_state().fuse_tokens == 0


class TestScore:
    def test_score_updates_on_valid_play(self):
        """Fireworks and score increment correctly on a valid play."""
        engine = GameEngine(MEDIUM)
        state = engine.get_full_state()

        # Find a playable card in human's hand (rank 1, fireworks at 0)
        human_hand = state.hands[HUMAN]
        playable_idx = None
        for i, card in enumerate(human_hand):
            if state.fireworks.get(card.color, 0) == card.rank - 1:
                playable_idx = i
                break

        if playable_idx is None:
            pytest.skip("No playable card in hand for this random seed.")

        card_played = human_hand[playable_idx]
        result = engine.execute_action(HUMAN, {'type': 'play', 'card_index': playable_idx})

        new_state = engine.get_full_state()
        assert result.points_gained == 1
        assert new_state.fireworks[card_played.color] == card_played.rank
        assert new_state.score == sum(new_state.fireworks.values())

    def test_score_is_zero_at_start(self, medium_engine):
        state = medium_engine.get_full_state()
        assert state.score == 0
        assert all(v == 0 for v in state.fireworks.values())


class TestRuleEnforcement:
    def test_cannot_hint_self(self, medium_engine):
        """A player cannot hint themselves."""
        state = medium_engine.get_full_state()
        human_hand = state.hands[HUMAN]
        color = human_hand[0].color
        action = {'type': 'hint', 'target_player': HUMAN, 'hint_type': 'color', 'hint_value': color}
        with pytest.raises(ValueError):
            medium_engine.execute_action(HUMAN, action)

    def test_hint_must_reference_existing_card(self, medium_engine):
        """Hint must reference at least one card in the target's hand."""
        # Find a color not in AI's hand
        state = medium_engine.get_full_state()
        ai_colors = {c.color for c in state.hands[AI]}
        all_colors = set(medium_engine.colors)
        missing = all_colors - ai_colors
        if not missing:
            pytest.skip("All colors present in AI hand.")
        bad_color = list(missing)[0]
        action = {'type': 'hint', 'target_player': AI, 'hint_type': 'color', 'hint_value': bad_color}
        with pytest.raises(ValueError):
            medium_engine.execute_action(HUMAN, action)

    def test_invalid_card_index(self, medium_engine):
        """Card index out of range raises ValueError."""
        action = {'type': 'play', 'card_index': 999}
        with pytest.raises(ValueError):
            medium_engine.execute_action(HUMAN, action)

    def test_no_action_after_game_over(self, medium_engine):
        """Cannot take actions after game_over is True."""
        medium_engine._state.game_over = True
        action = {'type': 'discard', 'card_index': 0}
        with pytest.raises(ValueError, match="game_over"):
            medium_engine.execute_action(HUMAN, action)

    def test_discard_blocked_at_max_hints_hard(self):
        """Hard mode: discarding not allowed when hint_tokens == max_hints."""
        engine = GameEngine(HARD)
        engine._state.hint_tokens = HARD.max_hints
        action = {'type': 'discard', 'card_index': 0}
        with pytest.raises(ValueError):
            engine.execute_action(HUMAN, action)

    def test_get_state_never_leaks_own_cards(self, medium_engine):
        """get_state_for_player must not include requesting player's card colors/ranks."""
        state_dict = medium_engine.get_state_for_player(HUMAN)
        human_hand = state_dict['hands'][HUMAN]
        for card in human_hand:
            assert 'color' not in card
            assert 'rank' not in card
            assert 'card_id' in card
