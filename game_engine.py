from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import random
import copy

from difficulty import DifficultyConfig
from config import RANK_COUNTS, ALL_RANKS, COLORS_BY_LEVEL, NUM_PLAYERS


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class Card:
    color: str   # one of R/G/B/W/Y
    rank: int    # 1-5
    card_id: int # globally unique, assigned at deck creation


@dataclass
class GameState:
    deck: List[Card]
    hands: Dict[int, List[Card]]          # player_id -> list of Card (index 0 = oldest)
    fireworks: Dict[str, int]             # color -> highest played rank (0 if none)
    discard_pile: List[Card]
    hint_tokens: int                      # starts at max_hints
    fuse_tokens: int                      # starts at max_fuses
    current_player: int                   # 0-indexed
    turn_number: int                      # starts at 0
    final_round: bool                     # True once deck is empty
    final_round_moves: int                # counts down from NUM_PLAYERS
    game_over: bool
    score: int                            # sum of all fireworks values
    difficulty: str                       # level name for display


@dataclass
class ActionResult:
    success: bool
    message: str
    points_gained: int
    mistake_made: bool
    game_over: bool
    new_state: GameState


# ---------------------------------------------------------------------------
# GameEngine
# ---------------------------------------------------------------------------

class GameEngine:
    def __init__(self, config: DifficultyConfig):
        self.config = config
        self.colors = COLORS_BY_LEVEL[config.level]
        self._card_id_counter = 0

        # Build and shuffle deck
        deck = self._build_deck()
        random.shuffle(deck)

        # Build initial game state
        fireworks = {c: 0 for c in self.colors}
        hands: Dict[int, List[Card]] = {p: [] for p in range(NUM_PLAYERS)}
        state = GameState(
            deck=deck,
            hands=hands,
            fireworks=fireworks,
            discard_pile=[],
            hint_tokens=config.max_hints,
            fuse_tokens=config.max_fuses,
            current_player=0,
            turn_number=0,
            final_round=False,
            final_round_moves=NUM_PLAYERS,
            game_over=False,
            score=0,
            difficulty=config.level,
        )
        self._state = state

        # Deal cards
        for p in range(NUM_PLAYERS):
            for _ in range(config.hand_size):
                self._draw_card(p)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_state_for_player(self, player_id: int) -> dict:
        """Return game state as dict. NEVER leaks the requesting player's card colors/ranks."""
        s = self._state
        # Build hands dict: own cards show only card_id, opponents show full card
        hands = {}
        for pid, hand in s.hands.items():
            if pid == player_id:
                # Own hand: hide color and rank, expose card_id for reference
                hands[pid] = [{'card_id': c.card_id, 'position': i}
                               for i, c in enumerate(hand)]
            else:
                hands[pid] = [{'card_id': c.card_id, 'color': c.color,
                                'rank': c.rank, 'position': i}
                               for i, c in enumerate(hand)]
        return {
            'hands': hands,
            'fireworks': dict(s.fireworks),
            'discard_pile': [{'color': c.color, 'rank': c.rank} for c in s.discard_pile],
            'hint_tokens': s.hint_tokens,
            'fuse_tokens': s.fuse_tokens,
            'current_player': s.current_player,
            'turn_number': s.turn_number,
            'final_round': s.final_round,
            'game_over': s.game_over,
            'score': s.score,
            'difficulty': s.difficulty,
            'deck_size': len(s.deck),
        }

    def get_full_state(self) -> GameState:
        """Return full game state (used by AI only)."""
        return self._state

    def execute_action(self, player_id: int, action: dict) -> ActionResult:
        """Validate and execute an action. Returns ActionResult."""
        s = self._state

        if s.game_over:
            raise ValueError("Cannot take actions after game_over is True.")

        action_type = action.get('type')

        if action_type == 'play':
            return self._execute_play(player_id, action)
        elif action_type == 'discard':
            return self._execute_discard(player_id, action)
        elif action_type == 'hint':
            return self._execute_hint(player_id, action)
        else:
            raise ValueError(f"Unknown action type: {action_type!r}")

    def is_game_over(self) -> bool:
        return self._state.game_over

    def get_legal_actions(self, player_id: int) -> List[dict]:
        """Return all legal action dicts for player_id."""
        s = self._state
        actions = []

        # Play and discard any card in hand
        for i in range(len(s.hands[player_id])):
            actions.append({'type': 'play', 'card_index': i})

            # Discard allowed unless hint_tokens == max AND config prohibits it
            if s.hint_tokens < self.config.max_hints or self.config.allow_discard_at_max_hints:
                actions.append({'type': 'discard', 'card_index': i})

        # Hints (only when tokens available)
        if s.hint_tokens > 0:
            for target in range(NUM_PLAYERS):
                if target == player_id:
                    continue
                target_hand = s.hands[target]
                # Collect unique colors and ranks in target's hand
                colors_in_hand = set(c.color for c in target_hand)
                ranks_in_hand = set(c.rank for c in target_hand)
                for color in colors_in_hand:
                    actions.append({
                        'type': 'hint',
                        'target_player': target,
                        'hint_type': 'color',
                        'hint_value': color,
                    })
                for rank in ranks_in_hand:
                    actions.append({
                        'type': 'hint',
                        'target_player': target,
                        'hint_type': 'rank',
                        'hint_value': rank,
                    })

        return actions

    def get_hint_matching_ids(self, action: dict) -> List[int]:
        """Return card_ids that match a hint action (used by knowledge tracker)."""
        s = self._state
        target = action['target_player']
        hint_type = action['hint_type']
        hint_value = action['hint_value']
        matching = []
        for card in s.hands[target]:
            if hint_type == 'color' and card.color == hint_value:
                matching.append(card.card_id)
            elif hint_type == 'rank' and card.rank == hint_value:
                matching.append(card.card_id)
        return matching

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_deck(self) -> List[Card]:
        deck = []
        for color in self.colors:
            for rank, count in RANK_COUNTS.items():
                for _ in range(count):
                    deck.append(Card(color=color, rank=rank, card_id=self._card_id_counter))
                    self._card_id_counter += 1
        return deck

    def _draw_card(self, player_id: int) -> Optional[Card]:
        s = self._state
        if not s.deck:
            return None
        card = s.deck.pop(0)
        s.hands[player_id].append(card)
        return card

    def _execute_play(self, player_id: int, action: dict) -> ActionResult:
        s = self._state
        idx = action.get('card_index')
        hand = s.hands[player_id]

        if idx is None or not (0 <= idx < len(hand)):
            raise ValueError(f"card_index {idx} is out of range (hand size {len(hand)}).")

        card = hand[idx]
        del hand[idx]
        new_card = self._draw_card(player_id)

        points_gained = 0
        mistake_made = False
        message = ""

        if s.fireworks.get(card.color, 0) == card.rank - 1:
            # Valid play
            s.fireworks[card.color] = card.rank
            s.score = sum(s.fireworks.values())
            points_gained = 1
            message = f"Played {card.color}{card.rank} successfully."
            if card.rank == 5:
                # Completing a color suite gives a hint token back
                s.hint_tokens = min(s.hint_tokens + 1, self.config.max_hints)
                message += " Bonus hint token!"
        else:
            # Illegal play
            s.discard_pile.append(card)
            s.fuse_tokens -= 1
            mistake_made = True
            message = (f"Played {card.color}{card.rank} — not valid! "
                       f"Fuse tokens remaining: {s.fuse_tokens}.")

        s.current_player = (s.current_player + 1) % NUM_PLAYERS
        s.turn_number += 1
        self._check_final_round()
        self._check_game_over()

        return ActionResult(
            success=True,
            message=message,
            points_gained=points_gained,
            mistake_made=mistake_made,
            game_over=s.game_over,
            new_state=s,
        )

    def _execute_discard(self, player_id: int, action: dict) -> ActionResult:
        s = self._state
        idx = action.get('card_index')
        hand = s.hands[player_id]

        if idx is None or not (0 <= idx < len(hand)):
            raise ValueError(f"card_index {idx} is out of range (hand size {len(hand)}).")

        if s.hint_tokens >= self.config.max_hints and not self.config.allow_discard_at_max_hints:
            raise ValueError(
                f"Discarding is not allowed when hint_tokens == {self.config.max_hints} "
                f"(max) on this difficulty."
            )

        card = hand[idx]
        del hand[idx]
        s.discard_pile.append(card)
        s.hint_tokens = min(s.hint_tokens + 1, self.config.max_hints)
        self._draw_card(player_id)

        s.current_player = (s.current_player + 1) % NUM_PLAYERS
        s.turn_number += 1
        self._check_final_round()
        self._check_game_over()

        return ActionResult(
            success=True,
            message=f"Discarded {card.color}{card.rank}. Hint tokens: {s.hint_tokens}.",
            points_gained=0,
            mistake_made=False,
            game_over=s.game_over,
            new_state=s,
        )

    def _execute_hint(self, player_id: int, action: dict) -> ActionResult:
        s = self._state

        if s.hint_tokens <= 0:
            raise ValueError("Cannot give a hint when hint_tokens == 0.")

        target = action.get('target_player')
        hint_type = action.get('hint_type')
        hint_value = action.get('hint_value')

        if target is None or target == player_id:
            raise ValueError("A player cannot hint themselves.")

        if target not in s.hands:
            raise ValueError(f"Invalid target_player: {target}")

        target_hand = s.hands[target]

        # Find matching cards
        matching = []
        for card in target_hand:
            if hint_type == 'color' and card.color == hint_value:
                matching.append(card)
            elif hint_type == 'rank' and card.rank == hint_value:
                matching.append(card)

        if not matching:
            raise ValueError(
                f"Hint {hint_type}={hint_value} does not match any card in player {target}'s hand."
            )

        # Hard mode: verify ALL matching cards are covered (they always are for our dict-based hints,
        # but we enforce that the hint_value actually appears so it's meaningful)
        if self.config.hint_must_cover_all:
            all_matching = [c for c in target_hand
                            if (hint_type == 'color' and c.color == hint_value)
                            or (hint_type == 'rank' and c.rank == hint_value)]
            if len(matching) != len(all_matching):
                raise ValueError(
                    "Hint must cover ALL matching cards in the target's hand (hint_must_cover_all=True)."
                )

        s.hint_tokens -= 1
        s.current_player = (s.current_player + 1) % NUM_PLAYERS
        s.turn_number += 1
        self._check_final_round()
        self._check_game_over()

        card_positions = [i for i, c in enumerate(target_hand) if c in matching]
        message = (f"Hint: player {target}'s cards at positions "
                   f"{[p+1 for p in card_positions]} are {hint_type}={hint_value}.")

        return ActionResult(
            success=True,
            message=message,
            points_gained=0,
            mistake_made=False,
            game_over=s.game_over,
            new_state=s,
        )

    def _check_final_round(self):
        s = self._state
        if not s.deck and not s.final_round:
            s.final_round = True
            s.final_round_moves = NUM_PLAYERS

    def _check_game_over(self):
        s = self._state
        if s.game_over:
            return
        # Fuses gone
        if s.fuse_tokens <= 0:
            s.game_over = True
            return
        # Perfect score
        if s.score == len(self.colors) * 5:
            s.game_over = True
            return
        # Final round countdown
        if s.final_round:
            s.final_round_moves -= 1
            if s.final_round_moves <= 0:
                s.game_over = True
