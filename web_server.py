"""
Hanabi AI Web Server
Run with:  python3 web_server.py
Access at: http://localhost:5000
"""

import os
import sys
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from difficulty import get_preset
from config import HUMAN, AI, COLOR_NAMES, COLORS_BY_LEVEL
from game_engine import GameEngine
from knowledge_tracker import KnowledgeTracker
from logic_core import LogicCore
from chatbot import HanabiChatbot

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Global game state (single-user local server)
# ---------------------------------------------------------------------------

_game: dict = {
    'engine': None,
    'trackers': None,
    'logic': None,
    'chatbot': None,
    'config': None,
    'colors': None,
    'chat_log': [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_trackers(engine: GameEngine, config) -> dict:
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


def _update_trackers(action: dict, engine: GameEngine, prev_human: list,
                     prev_ai: list, actor: int) -> None:
    trackers = _game['trackers']
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
        old_hand = prev_human if actor == HUMAN else prev_ai

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


def _get_response_state() -> dict:
    """Build the full state dict sent to the browser."""
    engine = _game['engine']
    colors = _game['colors']
    config = _game['config']

    state_for_human = engine.get_state_for_player(HUMAN)
    full_state = engine.get_full_state()

    # Enrich human's hand cards with knowledge tracker info
    tracker = _game['trackers'][HUMAN]
    human_hand = []
    for card_data in state_for_human['hands'][HUMAN]:
        card_id = card_data['card_id']
        poss = tracker.get_possibilities(card_id)
        known_colors = list({c for c, r in poss})
        known_ranks = list({r for c, r in poss})
        human_hand.append({
            'card_id': card_id,
            'position': card_data['position'],
            'known_color': known_colors[0] if len(known_colors) == 1 else None,
            'known_rank': known_ranks[0] if len(known_ranks) == 1 else None,
            'possible_count': len(poss),
        })

    # Discard pile (full list, client shows last N)
    discard = [{'color': c.color, 'rank': c.rank} for c in full_state.discard_pile]

    return {
        'fireworks': state_for_human['fireworks'],
        'hint_tokens': state_for_human['hint_tokens'],
        'fuse_tokens': state_for_human['fuse_tokens'],
        'score': state_for_human['score'],
        'turn_number': state_for_human['turn_number'],
        'current_player': state_for_human['current_player'],
        'game_over': state_for_human['game_over'],
        'deck_size': state_for_human['deck_size'],
        'final_round': state_for_human['final_round'],
        'difficulty': state_for_human['difficulty'],
        'colors': colors,
        'max_score': len(colors) * 5,
        'max_hints': config.max_hints,
        'max_fuses': config.max_fuses,
        'human_hand': human_hand,
        'ai_hand': state_for_human['hands'][AI],
        'discard_pile': discard,
        'chat_log': list(_game['chat_log']),
    }


def _format_action_label(action: dict) -> str:
    atype = action.get('type', '')
    if atype == 'play':
        return f"played card {action.get('card_index', 0) + 1}"
    if atype == 'discard':
        return f"discarded card {action.get('card_index', 0) + 1}"
    if atype == 'hint':
        htype = action.get('hint_type', '?')
        hval = action.get('hint_value', '?')
        color_name = COLOR_NAMES.get(str(hval), str(hval))
        if htype == 'color':
            return f"hinted {color_name}"
        return f"hinted rank {hval}"
    return str(action)


def _add_message(role: str, text: str) -> None:
    # Drop empty messages — they corrupt conversation flow and show blank bubbles
    if not text or not text.strip():
        return
    _game['chat_log'].append({'role': role, 'text': text.strip()})
    # Keep chat log bounded
    if len(_game['chat_log']) > 100:
        _game['chat_log'] = _game['chat_log'][-100:]


# ---------------------------------------------------------------------------
# Hint-on-demand helper
# ---------------------------------------------------------------------------

def _execute_hint_without_turn_advance(hint_action: dict) -> None:
    """
    Execute a hint from AI→Human that was requested via the chatbot.
    The hint token is consumed and the human's KnowledgeTracker is updated,
    but current_player and turn_number are NOT advanced — the hint doesn't
    count as anyone's 'turn'.
    """
    engine = _game['engine']
    state = engine.get_full_state()

    # Snapshot turn-order fields so we can restore them after the engine call
    saved_current_player = state.current_player
    saved_turn_number = state.turn_number
    saved_final_round_moves = state.final_round_moves

    prev_human = list(state.hands[HUMAN])
    prev_ai = list(state.hands[AI])

    engine.execute_action(AI, hint_action)          # validates + consumes token
    _update_trackers(hint_action, engine, prev_human, prev_ai, AI)

    # Restore turn order (the hint is "free" in terms of turns)
    restored = engine.get_full_state()
    if not restored.game_over:
        restored.current_player = saved_current_player
        restored.turn_number = saved_turn_number
        if restored.final_round:
            restored.final_round_moves = saved_final_round_moves


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('game.html')


@app.route('/api/start', methods=['POST'])
def start_game():
    data = request.json or {}
    difficulty = data.get('difficulty', 'medium').lower()

    try:
        config = get_preset(difficulty)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    colors = COLORS_BY_LEVEL[config.level]
    engine = GameEngine(config)
    trackers = _build_trackers(engine, config)
    logic = LogicCore(config)

    _game.update({
        'engine': engine,
        'trackers': trackers,
        'logic': logic,
        'config': config,
        'colors': colors,
        'chat_log': [],
    })

    # Initialise chatbot
    try:
        chatbot = HanabiChatbot(config.level)
        chatbot.reset_conversation()
        opening = chatbot.opening_message()
        _game['chatbot'] = chatbot
        _add_message('ai', opening)
    except Exception as e:
        _game['chatbot'] = None
        _add_message('system', f'Chatbot unavailable: {e}')

    return jsonify({'success': True, 'state': _get_response_state()})


@app.route('/api/state', methods=['GET'])
def get_state():
    if _game['engine'] is None:
        return jsonify({'error': 'No game in progress'}), 400
    return jsonify(_get_response_state())


@app.route('/api/action', methods=['POST'])
def take_action():
    if _game['engine'] is None:
        return jsonify({'error': 'No game in progress'}), 400

    engine = _game['engine']
    logic = _game['logic']
    chatbot = _game['chatbot']

    if engine.is_game_over():
        return jsonify({'error': 'Game is already over'}), 400

    data = request.json or {}
    action = data.get('action')
    if not action:
        return jsonify({'error': 'No action provided'}), 400

    full_state = engine.get_full_state()
    prev_human = list(full_state.hands[HUMAN])
    prev_ai = list(full_state.hands[AI])

    # Execute human action
    try:
        result = engine.execute_action(HUMAN, action)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    _update_trackers(action, engine, prev_human, prev_ai, HUMAN)
    _add_message('system', f'You {_format_action_label(action)}.')
    if result.mistake_made:
        fuses_left = engine.get_full_state().fuse_tokens
        _add_message('system', f'⚠️ Wrong play! Fuses remaining: {fuses_left}')

    # Game over after human action?
    if result.game_over:
        _handle_game_over(chatbot, engine)
        return jsonify({'success': True, 'state': _get_response_state()})

    # Execute AI action
    full_state2 = engine.get_full_state()
    prev_human2 = list(full_state2.hands[HUMAN])
    prev_ai2 = list(full_state2.hands[AI])

    ai_action = logic.decide_action(full_state2, _game['trackers'][AI])
    ai_reason = logic.get_last_reason()

    try:
        ai_result = engine.execute_action(AI, ai_action)
    except ValueError as e:
        return jsonify({'error': f'AI action error: {e}'}), 500

    _update_trackers(ai_action, engine, prev_human2, prev_ai2, AI)

    # Chatbot explains AI action
    if chatbot:
        try:
            state_dict = engine.get_state_for_player(HUMAN)
            explanation = chatbot.explain_ai_action(ai_action, ai_reason)
            _add_message('ai', explanation)
        except Exception:
            _add_message('ai', ai_reason)
    else:
        _add_message('ai', f'AI {_format_action_label(ai_action)}. {ai_reason}')

    if ai_result.mistake_made:
        fuses = engine.get_full_state().fuse_tokens
        _add_message('system', f'⚠️ AI made a mistake! Fuses remaining: {fuses}')

    if ai_result.game_over:
        _handle_game_over(chatbot, engine)

    return jsonify({'success': True, 'state': _get_response_state()})


@app.route('/api/coach', methods=['POST'])
def coach():
    if _game['engine'] is None:
        return jsonify({'error': 'No game in progress'}), 400
    if _game['engine'].is_game_over():
        return jsonify({'error': 'Game is over'}), 400

    engine = _game['engine']
    logic = _game['logic']
    chatbot = _game['chatbot']
    state = engine.get_full_state()

    coach_out = logic.coach_human(state, _game['trackers'][HUMAN])

    if chatbot:
        try:
            state_dict = engine.get_state_for_player(HUMAN)
            advice = chatbot.give_coaching_advice(state_dict, coach_out)
            _add_message('ai', f'💡 {advice}')
        except Exception:
            _add_message('ai', f"💡 Suggestion: {coach_out.get('reason', '')}")
    else:
        _add_message('ai', f"💡 {coach_out.get('reason', 'No advice available.')}")

    return jsonify({'success': True, 'state': _get_response_state()})


@app.route('/api/ask', methods=['POST'])
def ask_question():
    if _game['engine'] is None:
        return jsonify({'error': 'No game in progress'}), 400

    data = request.json or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    _add_message('human', question)
    chatbot = _game['chatbot']
    engine = _game['engine']
    logic = _game['logic']

    if chatbot:
        try:
            # Detect whether the player wants a game hint
            wants_hint = (
                not engine.is_game_over()
                and chatbot.detect_hint_intent(question)
            )

            if wants_hint:
                state = engine.get_full_state()
                if state.hint_tokens <= 0:
                    _add_message('ai', "We're out of hint tokens — no hints left this game!")
                else:
                    hint_result = logic.best_hint_for_human(
                        state, _game['trackers'][HUMAN]
                    )
                    if hint_result is None:
                        _add_message('ai',
                            "No clean hint available right now — any hint I give could "
                            "mislead you. Trust your knowledge and make a move!")
                    else:
                        hint_action, hint_reason = hint_result
                        _execute_hint_without_turn_advance(hint_action)
                        try:
                            explanation = chatbot.explain_hint_given(hint_action, hint_reason)
                            _add_message('ai', f'💡 {explanation}')
                        except Exception:
                            _add_message('ai', f'💡 {hint_reason}')
            else:
                state_dict = engine.get_state_for_player(HUMAN)
                answer = chatbot.answer_question(question, state_dict)
                _add_message('ai', answer)

        except RuntimeError as e:
            if 'empty response' in str(e).lower():
                _add_message('system', "AI didn't respond — try asking again in a moment.")
            else:
                _add_message('system', f'Chatbot error: {e}')
    else:
        _add_message('system', 'Chatbot is unavailable.')

    return jsonify({'success': True, 'state': _get_response_state()})


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _handle_game_over(chatbot, engine) -> None:
    final_score = engine.get_full_state().score
    if chatbot:
        try:
            state_dict = engine.get_state_for_player(HUMAN)
            farewell = chatbot.announce_game_over(final_score, state_dict)
            _add_message('ai', farewell)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print()
    print('  ╔══════════════════════════════════════╗')
    print('  ║         H A N A B I   A I           ║')
    print('  ║   Web Server  ·  Arcee Trinity       ║')
    print('  ╚══════════════════════════════════════╝')
    print()
    print('  Open your browser at: http://localhost:5000')
    print('  Press Ctrl+C to stop the server')
    print()
    app.run(debug=False, port=5000, host='127.0.0.1')
