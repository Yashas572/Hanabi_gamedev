import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# System prompt (verbatim as specified in Section 6.2)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are the AI partner and coach in a 2-player game of Hanabi. You communicate through a chat panel.

YOUR ROLE:
- You are Player 1 (the AI). The human is Player 0.
- You explain your own moves in natural, friendly language after each turn.
- You answer the human's questions about rules, strategy, or game state.
- You give coaching advice when asked, based on the logic core's recommendation.
- You NEVER make game decisions yourself — decisions come from the logic core.
- When you give the human a hint (via the hint system, not this chat), explain what it reveals
  and nudge them toward the right action — but calibrate how direct you are by difficulty:
    Easy:   Be clear and helpful. It's okay to say "that card is playable" explicitly.
    Medium: Give a useful nudge but don't spell it out completely. Let them reason a bit.
    Hard:   Be cryptic. Confirm the hint happened but let them figure out the implication.

COMMUNICATION STYLE:
- Be concise and casual. Never repeat information already stated.
- When explaining a move, say WHY it was made in plain language.
- When coaching, explain the reasoning behind the recommended move.
- Refer to card positions ('your leftmost card', 'card 2') not hidden card details.
- On Easy mode: be friendly and a bit more thorough.
- On Hard mode: be terse and assume they know the rules.
- NEVER respond with bullet-point lists or headers — plain conversational text only.

RULES YOU KNOW:
- Players cannot see their own cards.
- Hints cost a hint token (max 8). Discarding a card restores one token.
- Playing a wrong card costs a fuse. 3 fuses = game over.
- Goal: play cards 1-5 in each color in order. Max score = 25.
- You follow the Intentional AI strategy: hints always signal a clear action.
"""

# ---------------------------------------------------------------------------
# Context injection helper
# ---------------------------------------------------------------------------

def inject_context(user_message: str, game_state: dict, logic_output: dict) -> str:
    context = f"""
[GAME STATE]
Turn: {game_state['turn_number']}
Score: {game_state['score']}/25
Hint tokens: {game_state['hint_tokens']}/8
Fuse tokens: {game_state['fuse_tokens']}/3
Fireworks: {game_state['fireworks']}
Discard pile size: {len(game_state['discard_pile'])}
Difficulty: {game_state['difficulty']}

[LOGIC CORE OUTPUT]
Recommended action: {logic_output['action']}
Reason: {logic_output['reason']}

[HUMAN MESSAGE]
{user_message}
"""
    return context


# ---------------------------------------------------------------------------
# HanabiChatbot (OpenRouter — Aurora Alpha)
# ---------------------------------------------------------------------------

class HanabiChatbot:
    """
    Arcee Trinity Large (arcee-ai/trinity-large-preview:free) conversational layer.
    Uses the OpenAI-compatible OpenRouter API (free tier).
    Conversation history is maintained across the full game for coherent context.
    """

    _MODEL       = 'arcee-ai/trinity-large-preview:free'
    _BASE_URL    = 'https://openrouter.ai/api/v1'
    _SITE_URL    = 'http://localhost:5000'
    _SITE_TITLE  = 'Hanabi AI'

    def __init__(self, difficulty: str):
        self.difficulty = difficulty
        api_key = os.environ.get('OPENROUTER_API_KEY')
        if not api_key:
            raise EnvironmentError(
                "OPENROUTER_API_KEY not set. Add it to your .env file."
            )

        self._client = OpenAI(
            api_key=api_key,
            base_url=self._BASE_URL,
        )
        # Conversation history: system prompt + alternating user/assistant turns
        self._history: list[dict] = []
        self._reset_history()

    def _reset_history(self) -> None:
        """Clear conversation history back to the system prompt only."""
        self._history = [{'role': 'system', 'content': SYSTEM_PROMPT}]

    def _send(self, user_message: str) -> str:
        """Append a user turn, call the API, append the assistant reply, return it."""
        self._history.append({'role': 'user', 'content': user_message})

        reply = ''
        for attempt in range(3):
            response = self._client.chat.completions.create(
                model=self._MODEL,
                messages=self._history,
                max_tokens=1024,
                temperature=0.7,
                extra_headers={
                    'HTTP-Referer': self._SITE_URL,
                    'X-Title': self._SITE_TITLE,
                },
            )
            reply = (response.choices[0].message.content or '').strip()
            if reply:
                break

        if not reply:
            # Don't poison history with empty turns — remove the user message and bail
            self._history.pop()
            raise RuntimeError('Model returned an empty response after 3 attempts.')

        self._history.append({'role': 'assistant', 'content': reply})
        return reply

    # ------------------------------------------------------------------
    # Public API (identical interface to the old Gemini chatbot)
    # ------------------------------------------------------------------

    def explain_ai_action(self, action: dict, reason: str) -> str:
        action_str = self._format_action(action)
        message = (
            f"I just took this action: {action_str}\n"
            f"My reasoning: {reason}\n"
            f"Please explain this to the human player in a natural, friendly way. "
            f"Be concise and focus on why the move was made."
        )
        logic_output = {'action': action_str, 'reason': reason}
        game_state = {'turn_number': '?', 'score': '?', 'hint_tokens': '?',
                      'fuse_tokens': '?', 'fireworks': '?', 'discard_pile': [],
                      'difficulty': self.difficulty}
        return self._send(inject_context(message, game_state, logic_output))

    def answer_question(self, question: str, game_state: dict) -> str:
        logic_output = {'action': 'N/A (human asked a question)', 'reason': 'Informational'}
        return self._send(inject_context(question, game_state, logic_output))

    def give_coaching_advice(self, game_state: dict, logic_output: dict) -> str:
        message = (
            "The human asked for coaching advice. Please explain the recommended move "
            "in a helpful, encouraging way, including WHY it is the best choice."
        )
        return self._send(inject_context(message, game_state, logic_output))

    def announce_game_over(self, final_score: int, game_state: dict) -> str:
        max_score = len(game_state.get('fireworks', {})) * 5
        if final_score >= 20:
            tone = "enthusiastic and celebratory"
        elif final_score >= 15:
            tone = "encouraging and positive"
        else:
            tone = "consoling and supportive"

        message = (
            f"The game is over! Final score: {final_score}/{max_score}. "
            f"Please give a {tone} game-over message. Then ask if they want to play again."
        )
        logic_output = {'action': 'Game Over', 'reason': f'Final score: {final_score}'}
        return self._send(inject_context(message, game_state, logic_output))

    def opening_message(self) -> str:
        verbosity_note = {
            'easy': (
                "Give a SHORT, punchy welcome — 3-4 sentences max. Be funny and casual, "
                "not robotic. Crack a quick joke about Hanabi being the only card game "
                "where you can't see your own hand. Give ONE sentence on the goal "
                "(play 1-5 in each color), ONE sentence on hints vs fuses, "
                "then tell them to just jump in and ask questions as they go. "
                "No bullet points, no headers, no walls of text."
            ),
            'medium': (
                "Give a SHORT, punchy welcome — 2-3 sentences max. Be casual and a bit witty. "
                "One sentence on the goal, one quick tip, then let's go. "
                "No bullet points, no headers."
            ),
            'hard': (
                "One sentence welcome, maybe a tiny smirk. They know the rules. Let's go."
            ),
        }.get(self.difficulty, "Short, funny, casual welcome. 2-3 sentences max.")

        message = f"Game starting on {self.difficulty.upper()} difficulty. {verbosity_note}"
        logic_output = {'action': 'Game Start', 'reason': 'Opening message'}
        game_state = {'turn_number': 0, 'score': 0, 'hint_tokens': '?',
                      'fuse_tokens': '?', 'fireworks': {}, 'discard_pile': [],
                      'difficulty': self.difficulty}
        return self._send(inject_context(message, game_state, logic_output))

    def detect_hint_intent(self, message: str) -> bool:
        """
        Return True if the player's message is asking for a game hint / advice on
        what to do next.  Uses the LLM — no hardcoded keywords.
        This is a lightweight one-shot call that does NOT touch conversation history.
        """
        response = self._client.chat.completions.create(
            model=self._MODEL,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        "You are classifying a Hanabi player's chat message. "
                        "Reply with ONLY \"yes\" if the player is asking for a hint, "
                        "advice, suggestion, or guidance on what card to play/discard. "
                        "Reply with ONLY \"no\" for any other message (questions about "
                        "rules, score, general chat, etc.)."
                    ),
                },
                {'role': 'user', 'content': message},
            ],
            max_tokens=5,
            temperature=0.0,
            extra_headers={
                'HTTP-Referer': self._SITE_URL,
                'X-Title': self._SITE_TITLE,
            },
        )
        reply = (response.choices[0].message.content or '').strip().lower()
        return reply.startswith('yes')

    def explain_hint_given(self, action: dict, reason: str) -> str:
        """Explain to the human what a hint just given to them means and what to do."""
        action_str = self._format_action(action)
        subtlety = {
            'easy':   "Be clear — it's okay to say outright what the card likely is and what to do.",
            'medium': "Give a useful nudge but don't spell it out — let them reason a bit.",
            'hard':   "Be cryptic. Confirm the hint was given but reveal as little as possible.",
        }.get(self.difficulty, "Be concise.")
        message = (
            f"I just gave you this hint: {action_str}\n"
            f"My reasoning: {reason}\n"
            f"Explain what this hint reveals and nudge the human on what to do next. "
            f"{subtlety} One or two sentences max."
        )
        logic_output = {'action': action_str, 'reason': reason}
        game_state = {'turn_number': '?', 'score': '?', 'hint_tokens': '?',
                      'fuse_tokens': '?', 'fireworks': '?', 'discard_pile': [],
                      'difficulty': self.difficulty}
        return self._send(inject_context(message, game_state, logic_output))

    def reset_conversation(self) -> None:
        """Reset conversation history (called at the start of each new game)."""
        self._reset_history()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_action(self, action: dict) -> str:
        atype = action.get('type', '')
        if atype == 'play':
            return f"Play card at position {action.get('card_index', '?') + 1}"
        if atype == 'discard':
            return f"Discard card at position {action.get('card_index', '?') + 1}"
        if atype == 'hint':
            htype = action.get('hint_type', '?')
            hval  = action.get('hint_value', '?')
            return f"Hint to human: {htype}={hval}"
        return str(action)
