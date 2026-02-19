import random
import torch
import numpy as np
from hanabi import (
    GREEN, YELLOW, WHITE, BLUE, RED,
    HINT_COLOR, HINT_RANK, PLAY, DISCARD,
    Action
)
import agent
import agents.nn

COLOR_MAP = {
    'G': GREEN,
    'Y': YELLOW,
    'W': WHITE,
    'B': BLUE,
    'R': RED
}

class HanabiNet(torch.nn.Module):
    def __init__(self, input_dim, hidden_dim=512, output_dim=20):
        super(HanabiNet, self).__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(input_dim, hidden_dim),
            torch.nn.BatchNorm1d(hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(hidden_dim, hidden_dim),
            torch.nn.BatchNorm1d(hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(hidden_dim, output_dim)
        )

    def forward(self, x):
        return self.net(x)

class NNPlayer(agent.Agent):
    def __init__(self, name, pnr):
        self.name = name
        self.explanation = []
        self.last_action = None
        
        MODEL_PATH = "./hanabi_model.pt"
        self.input_dim = 373
        self.model = HanabiNet(input_dim=self.input_dim, hidden_dim=512, output_dim=20)
        
        try:
            self.model.load_state_dict(torch.load(MODEL_PATH))
            self.model.eval()
        except Exception as e:
            print("Warning: Could not load the trained NN model:", e)
            self.model = None

    def get_action(self, nr, hands, knowledge, trash, played, board,
                   valid_actions, hints, hits, cards_left, last_action=None):
        features = agents.nn.to_features(
            nr, hands, knowledge, trash, played, board,
            valid_actions, hints, hits, cards_left,
            self.last_action
        )

        if self.model is None:
            return random.choice(valid_actions)

        x = torch.tensor(features, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            logits = self.model(x)
            probs = torch.softmax(logits, dim=1).cpu().numpy()[0]

        action_indices_sorted = np.argsort(-probs)

        for idx in action_indices_sorted:
            candidate_dict = self.index_to_action(idx)
            for va in valid_actions:
                if self.actions_match(candidate_dict, va):
                    return va
        
        return random.choice(valid_actions)

    def inform(self, action, player):
        self.last_action = action

    def index_to_action(self, idx):
        if idx == 0:  return {"type": "hint", "hint_type": "color", "hint_value": "G"}
        if idx == 1:  return {"type": "hint", "hint_type": "color", "hint_value": "Y"}
        if idx == 2:  return {"type": "hint", "hint_type": "color", "hint_value": "W"}
        if idx == 3:  return {"type": "hint", "hint_type": "color", "hint_value": "B"}
        if idx == 4:  return {"type": "hint", "hint_type": "color", "hint_value": "R"}

        if idx == 5:  return {"type": "hint", "hint_type": "rank",  "hint_value": 1}
        if idx == 6:  return {"type": "hint", "hint_type": "rank",  "hint_value": 2}
        if idx == 7:  return {"type": "hint", "hint_type": "rank",  "hint_value": 3}
        if idx == 8:  return {"type": "hint", "hint_type": "rank",  "hint_value": 4}
        if idx == 9:  return {"type": "hint", "hint_type": "rank",  "hint_value": 5}

        if idx in [10, 11, 12, 13, 14]:
            return {"type": "play", "card_index": idx - 10}
        if idx in [15, 16, 17, 18, 19]:
            return {"type": "discard", "card_index": idx - 15}

        return None

    def actions_match(self, predicted, actual):
        if predicted["type"] == "hint":
            if actual.type == HINT_COLOR and predicted["hint_type"] == "color":
                expected_color = COLOR_MAP.get(predicted["hint_value"], None)
                return (actual.color == expected_color)
            elif actual.type == HINT_RANK and predicted["hint_type"] == "rank":
                return (actual.rank == predicted["hint_value"])
            return False

        elif predicted["type"] == "play":
            return (actual.type == PLAY and actual.card_index == predicted["card_index"])

        elif predicted["type"] == "discard":
            return (actual.type == DISCARD and actual.card_index == predicted["card_index"])

        return False

agent.register("nn", "Neural Network Player", NNPlayer)
