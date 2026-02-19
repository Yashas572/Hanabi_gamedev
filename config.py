from difficulty import DifficultyConfig, EASY, MEDIUM, HARD, PRESETS, get_preset

# All five possible colors (used in Hard mode)
ALL_COLORS = ['R', 'G', 'B', 'W', 'Y']

# Colors available per difficulty
COLORS_BY_LEVEL = {
    'easy':   ['R', 'G', 'B'],
    'medium': ['R', 'G', 'B', 'W'],
    'hard':   ['R', 'G', 'B', 'W', 'Y'],
}

# Human-readable color names for display
COLOR_NAMES = {
    'R': 'Red',
    'G': 'Green',
    'B': 'Blue',
    'W': 'White',
    'Y': 'Yellow',
}

# Rank distribution in a standard Hanabi deck: rank -> count per color
RANK_COUNTS = {1: 3, 2: 2, 3: 2, 4: 2, 5: 1}
ALL_RANKS = [1, 2, 3, 4, 5]

# Player IDs
HUMAN = 0
AI = 1
NUM_PLAYERS = 2
