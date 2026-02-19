"""
Hanabi AI System — Interactive CLI Entry Point
Human (Player 0) vs AI (Player 1)

Card positions are 1-indexed in all user-facing text.
For the original agent simulation runner, see simulate.py.
"""

import sys
import re

from difficulty import get_preset, DifficultyConfig
from config import HUMAN, AI, COLOR_NAMES, COLORS_BY_LEVEL
from game_engine import GameEngine
from knowledge_tracker import KnowledgeTracker
from logic_core import LogicCore
from chatbot import HanabiChatbot


BANNER = r"""
╔══════════════════════════════════════╗
║         H A N A B I   A I           ║
║   Intentional AI · Gemini 2.0 Flash ║
╚══════════════════════════════════════╝
"""


def display_fireworks(fireworks: dict, colors: list) -> str:
    parts = []
    for color in colors:
        val = fireworks.get(color, 0)
        bar = '█' * val + '░' * (5 - val)
        parts.append(f"  {COLOR_NAMES[color]:6s} [{bar}] {val}/5")
    return '\n'.join(parts)


def display_human_state(state_dict: dict, colors: list) -> None:
    print()
    print("─" * 44)
    print(f"  Turn {state_dict['turn_number']}  |  "
          f"Score: {state_dict['score']}/25  |  "
          f"Hints: {state_dict['hint_tokens']}  |  "
          f"Fuses: {state_dict['fuse_tokens']}")
    print()
    print("  Fireworks:")
    print(display_fireworks(state_dict['fireworks'], colors))
    print()

    ai_hand = state_dict['hands'].get(AI, [])
    print("  My (AI) hand:")
    if ai_hand:
        for c in ai_hand:
            print(f"    [{c['position']+1}] {COLOR_NAMES[c['color']]} {c['rank']}")
    else:
        print("    (empty)")
    print()

    human_hand = state_dict['hands'].get(HUMAN, [])
    print("  Your hand (you cannot see your own cards):")
    if human_hand:
        for c in human_hand:
            print(f"    [{c['position']+1}] Card #{c['card_id']}")
    else:
        print("    (empty)")
    print()

    discard = state_dict['discard_pile']
    if discard:
        discard_str = ', '.join(
            f"{COLOR_NAMES[d['color']][0]}{d['rank']}" for d in discard[-10:]
        )
        print(f"  Discard pile ({len(discard)} cards): {discard_str}")
    print("─" * 44)


COACH_TRIGGERS = {'help', '?', 'hint', 'coach', 'what should i do', 'what should i do?'}


def is_question(text: str) -> bool:
    stripped = text.strip().lower()
    if stripped in COACH_TRIGGERS:
        return False
    if stripped.endswith('?'):
        return True
    question_starters = (
        'what', 'how', 'why', 'when', 'who', 'which',
        'can', 'could', 'is', 'are', 'do', 'does',
        'tell', 'explain', 'describe',
    )
    return any(stripped.startswith(s) for s in question_starters)


def parse_human_action(text: str, hand_size: int, colors: list) -> dict:
    """
    Parse natural language input into an action dict.
    Card positions are 1-indexed; internally converted to 0-indexed.
    """
    t = text.strip().lower()

    m = re.match(r'^play\s+(?:card\s+)?(\d+)$', t)
    if m:
        pos = int(m.group(1)) - 1
        if not (0 <= pos < hand_size):
            raise ValueError(f"Card position {pos+1} is out of range (you have {hand_size} cards).")
        return {'type': 'play', 'card_index': pos}

    m = re.match(r'^discard\s+(?:card\s+)?(\d+)$', t)
    if m:
        pos = int(m.group(1)) - 1
        if not (0 <= pos < hand_size):
            raise ValueError(f"Card position {pos+1} is out of range (you have {hand_size} cards).")
        return {'type': 'discard', 'card_index': pos}

    color_map = {cn.lower(): c for c, cn in COLOR_NAMES.items()}
    color_map.update({c.lower(): c for c in colors})

    m = re.match(r'^hint\s+(?:color\s+)?([a-zA-Z]+)$', t)
    if m:
        color_str = m.group(1).lower()
        if color_str in color_map and color_map[color_str] in colors:
            return {
                'type': 'hint',
                'target_player': AI,
                'hint_type': 'color',
                'hint_value': color_map[color_str],
            }

    m = re.match(r'^hint\s+(?:rank\s+)?([1-5])$', t)
    if m:
        rank = int(m.group(1))
        return {
            'type': 'hint',
            'target_player': AI,
            'hint_type': 'rank',
            'hint_value': rank,
        }

    raise ValueError(
        "Could not parse your input. Try:\n"
        "  play <1-5>          — play card at that position\n"
        "  discard <1-5>       — discard card at that position\n"
        "  hint <color>        — hint the AI about a color (e.g. 'hint red')\n"
        "  hint <1-5>          — hint the AI about a rank\n"
        "  help / coach / ?    — ask for advice"
    )


def build_knowledge_trackers(engine: GameEngine, config: DifficultyConfig) -> dict:
    state = engine.get_full_state()
    trackers = {}
    for pid in [HUMAN, AI]:
        tracker = KnowledgeTracker(
            player_id=pid, num_colors=config.num_colors, config=config
        )
        for card in state.hands[pid]:
            tracker.add_card(card.card_id)
        if pid == AI:
            for card in state.hands[HUMAN]:
                tracker.observe_public_card(card.color, card.rank)
        trackers[pid] = tracker
    return trackers


def update_knowledge_trackers(
    trackers: dict,
    result,
    action: dict,
    engine: GameEngine,
    prev_hand_human: list,
    prev_hand_ai: list,
    actor: int,
) -> None:
    state = engine.get_full_state()
    action_type = action.get('type')

    if action_type == 'hint':
        target = action['target_player']
        hint_type = action['hint_type']
        hint_value = action['hint_value']
        matching_ids = engine.get_hint_matching_ids(action)
        trackers[target].apply_hint(hint_type, hint_value, matching_ids)

    elif action_type in ('play', 'discard'):
        idx = action['card_index']
        old_hand = prev_hand_human if actor == HUMAN else prev_hand_ai

        if idx < len(old_hand):
            played_card = old_hand[idx]
            trackers[actor].remove_card(played_card.card_id)

            other = AI if actor == HUMAN else HUMAN
            trackers[other].observe_public_card(played_card.color, played_card.rank)

            new_hand = state.hands[actor]
            old_ids = {c.card_id for c in old_hand}
            for card in new_hand:
                if card.card_id not in old_ids:
                    trackers[actor].add_card(card.card_id)
                    if actor == HUMAN:
                        trackers[AI].observe_public_card(card.color, card.rank)
                    break


def select_difficulty() -> DifficultyConfig:
    print("  Select difficulty:")
    print("    1. Easy   — 3 colors, extra tokens, relaxed rules")
    print("    2. Medium — 4 colors, standard rules")
    print("    3. Hard   — 5 colors, strict rules, smaller hands")
    print()
    while True:
        choice = input("  Your choice (1/2/3 or easy/medium/hard): ").strip().lower()
        mapping = {
            '1': 'easy', '2': 'medium', '3': 'hard',
            'easy': 'easy', 'medium': 'medium', 'hard': 'hard',
        }
        if choice in mapping:
            return get_preset(mapping[choice])
        print("  Please enter 1, 2, 3, easy, medium, or hard.")


def play_game(config: DifficultyConfig) -> int:
    colors = COLORS_BY_LEVEL[config.level]

    print(f"\n  Starting {config.level.upper()} game "
          f"({config.num_colors} colors, {config.hand_size} cards/player, "
          f"{config.max_hints} hints, {config.max_fuses} fuses)\n")

    engine = GameEngine(config)
    trackers = build_knowledge_trackers(engine, config)
    logic = LogicCore(config)

    print("  Connecting to Gemini 2.0 Flash...", end='', flush=True)
    chatbot = None
    try:
        chatbot = HanabiChatbot(config.level)
        chatbot.reset_conversation()
        print(" done.")
        opening = chatbot.opening_message()
        print(f"\n  AI: {opening}\n")
    except Exception as e:
        chatbot = None
        print(f"\n  (Chatbot unavailable: {e})\n")

    def ai_say(text: str) -> None:
        if text:
            print(f"\n  AI: {text}\n")

    while not engine.is_game_over():
        state = engine.get_full_state()
        current = state.current_player

        if current == HUMAN:
            state_dict = engine.get_state_for_player(HUMAN)
            display_human_state(state_dict, colors)

            while True:
                try:
                    user_input = input("  Your move: ").strip()
                    if not user_input:
                        continue

                    stripped = user_input.strip().lower()

                    if stripped in COACH_TRIGGERS:
                        coach_out = logic.coach_human(state, trackers[HUMAN])
                        if chatbot:
                            advice = chatbot.give_coaching_advice(state_dict, coach_out)
                            ai_say(advice)
                        else:
                            print(f"  Suggestion: {coach_out['action']} — {coach_out['reason']}")
                        continue

                    if is_question(user_input):
                        if chatbot:
                            answer = chatbot.answer_question(user_input, state_dict)
                            ai_say(answer)
                        else:
                            print("  (Chatbot unavailable for questions.)")
                        continue

                    hand_size = len(state.hands[HUMAN])
                    action = parse_human_action(user_input, hand_size, colors)

                    prev_human = list(state.hands[HUMAN])
                    prev_ai = list(state.hands[AI])

                    result = engine.execute_action(HUMAN, action)
                    update_knowledge_trackers(
                        trackers, result, action, engine, prev_human, prev_ai, HUMAN
                    )

                    if result.mistake_made:
                        print(f"  *** {result.message} ***")
                    else:
                        print(f"  > {result.message}")
                    break

                except ValueError as e:
                    print(f"  ! {e}")

        else:
            state = engine.get_full_state()
            print("\n  AI is thinking...")

            action = logic.decide_action(state, trackers[AI])
            reason = logic.get_last_reason()

            prev_human = list(state.hands[HUMAN])
            prev_ai = list(state.hands[AI])

            result = engine.execute_action(AI, action)
            update_knowledge_trackers(
                trackers, result, action, engine, prev_human, prev_ai, AI
            )

            if chatbot:
                explanation = chatbot.explain_ai_action(action, reason)
                ai_say(explanation)
            else:
                print(f"  AI: {reason}")

            if result.mistake_made:
                fuses = engine.get_full_state().fuse_tokens
                print(f"  *** AI mistake! Fuses remaining: {fuses} ***")

    final_state = engine.get_full_state()
    final_score = final_state.score
    state_dict = engine.get_state_for_player(HUMAN)

    print(f"\n{'═'*44}")
    print(f"  GAME OVER — Final score: {final_score}/{len(colors)*5}")
    print(f"  Fireworks:")
    print(display_fireworks(final_state.fireworks, colors))
    print(f"{'═'*44}\n")

    if chatbot:
        farewell = chatbot.announce_game_over(final_score, state_dict)
        ai_say(farewell)

    return final_score


def main():
    print(BANNER)

    while True:
        config = select_difficulty()
        print()
        play_game(config)

        print()
        again = input("  Play again? (y/n): ").strip().lower()
        if again not in ('y', 'yes'):
            print("\n  Thanks for playing Hanabi!\n")
            break
        print()


if __name__ == '__main__':
    main()
