from dataclasses import dataclass


@dataclass
class DifficultyConfig:
    level: str                       # 'easy' | 'medium' | 'hard'
    num_colors: int                  # 3, 4, or 5
    hand_size: int                   # cards per player
    max_hints: int                   # total hint tokens available
    max_fuses: int                   # total fuse tokens
    allow_discard_at_max_hints: bool
    ai_plays_optimally: bool         # False on Easy = AI makes occasional mistakes
    hint_must_cover_all: bool        # True = hint must point to ALL matching cards
    chatbot_verbosity: str           # 'high' | 'medium' | 'low'
    score_correct_play: int          # Compare() weights
    score_correct_discard: int
    score_correct_maydiscard: int
    score_wrong_play: int
    score_wrong_discard: int
    # Probability that the AI spends its turn giving a hint to the human (0.0 = never).
    # Higher = more freely hints; lower = saves tokens and lets human ask via chat.
    ai_hint_probability: float
    # Minimum Compare() score a hint must achieve before the AI will auto-give it.
    # Raises the bar on harder difficulties so only clearly useful hints are given.
    ai_hint_min_score: float


EASY = DifficultyConfig(
    level='easy',
    num_colors=3,
    hand_size=5,
    max_hints=9,
    max_fuses=4,
    allow_discard_at_max_hints=True,
    ai_plays_optimally=False,
    hint_must_cover_all=False,
    chatbot_verbosity='high',
    score_correct_play=10,
    score_correct_discard=5,
    score_correct_maydiscard=3,
    score_wrong_play=20,
    score_wrong_discard=10,
    # Easy: hints fairly often — helps newer players without draining tokens too fast
    ai_hint_probability=0.65,
    ai_hint_min_score=3,
)

MEDIUM = DifficultyConfig(
    level='medium',
    num_colors=4,
    hand_size=5,
    max_hints=8,
    max_fuses=3,
    allow_discard_at_max_hints=True,
    ai_plays_optimally=True,
    hint_must_cover_all=True,
    chatbot_verbosity='medium',
    score_correct_play=10,
    score_correct_discard=5,
    score_correct_maydiscard=3,
    score_wrong_play=25,
    score_wrong_discard=10,
    # Medium: only clearly valuable hints; player should ask for the rest
    ai_hint_probability=0.30,
    ai_hint_min_score=8,
)

HARD = DifficultyConfig(
    level='hard',
    num_colors=5,
    hand_size=4,
    max_hints=8,
    max_fuses=3,
    allow_discard_at_max_hints=False,
    ai_plays_optimally=True,
    hint_must_cover_all=True,
    chatbot_verbosity='low',
    score_correct_play=10,
    score_correct_discard=5,
    score_correct_maydiscard=3,
    score_wrong_play=30,
    score_wrong_discard=10,
    # Hard: AI never auto-hints — the player must ask and figure it out themselves
    ai_hint_probability=0.0,
    ai_hint_min_score=999,
)

PRESETS = {
    'easy': EASY,
    'medium': MEDIUM,
    'hard': HARD,
}


def get_preset(level: str) -> DifficultyConfig:
    key = level.strip().lower()
    if key not in PRESETS:
        raise ValueError(f"Unknown difficulty level: {level!r}. Choose easy, medium, or hard.")
    return PRESETS[key]
