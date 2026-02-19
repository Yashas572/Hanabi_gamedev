import random

class Agent:
    def __init__(self, name, pnr):
        self.name = name
        self.explanation = []
    def get_action(self, nr, hands, knowledge, trash, played, board, valid_actions, hints, hits, cards_left):
        return random.choice(valid_actions)
    def inform(self, action, player):
        pass
    def get_explanation(self):
        return self.explanation
        
agent_types = {}

def register(id, name, agent):
    agent_types[id] = (name,agent)
    
register("random", "Random Player", Agent)

def get(id):
    return agent_types[id]
    
def make(id, *args, **kwargs):
    return agent_types[id][1](*args, **kwargs)
    
def ids():
    return list(agent_types.keys())