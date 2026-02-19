import random
import sys
import copy
import time

GREEN = 0
YELLOW = 1
WHITE = 2
BLUE = 3
RED = 4
ALL_COLORS = [GREEN, YELLOW, WHITE, BLUE, RED]
COLORNAMES = ["green", "yellow", "white", "blue", "red"]

class Card:
    def __init__(self, color, rank=None):
        if isinstance(color, Card):
            self.color = color.color 
            self.rank = color.rank 
        elif isinstance(color, list):
            self.color = color[0]
            self.rank = color[1]
        else:
            self.color = color 
            self.rank = rank 
    def isColor(self, color):
        return self.color == color 
    def isRank(self, rank):
        return self.rank == rank
    def __eq__(self, other):
        if other is None: return False 
        if type(other) == tuple:
            return (self.color,self.rank) == other
        return (self.color,self.rank) == (other.color,other.rank)
    def __getitem__(self, idx):
        if idx == 0: return self.color 
        return self.rank
    def __str__(self):
        return COLORNAMES[self.color] + " " + str(self.rank)
    def __repr__(self):
        return str((self.color,self.rank))
        
    def is_useless(self, board):
        return board[self.color].rank + 1 > self.rank
        
    def is_playable(self, board):
        return board[self.color].rank + 1 == self.rank
        
    def __iter__(self):
        return iter([self.color, self.rank])
        
    def to_json(self):
        return {"color": COLORNAMES[self.color], "rank": self.rank}

COUNTS = [3,2,2,2,1]

# semi-intelligently format cards in any format
def f(something):
    if type(something) == list:
        return list(map(f, something))
    elif type(something) == dict:
        return {k: something(v) for (k,v) in something.items()}
    elif type(something) == Card:
        return str(something)
    elif type(something) == tuple and len(something) == 2:
        return (COLORNAMES[something[0]],something[1])
    return something

def make_deck():
    deck = []
    for color in ALL_COLORS:
        for rank, cnt in enumerate(COUNTS):
            for i in range(cnt):
                deck.append(Card(color, rank+1))
    random.shuffle(deck)
    return deck
    
def initial_knowledge():
    knowledge = []
    for color in ALL_COLORS:
        knowledge.append(COUNTS[:])
    return knowledge
    
def hint_color(knowledge, color, truth):
    result = []
    for col in ALL_COLORS:
        if truth == (col == color):
            result.append(knowledge[col][:])
        else:
            result.append([0 for i in knowledge[col]])
    return result
    
def hint_rank(knowledge, rank, truth):
    result = []
    for col in ALL_COLORS:
        colknow = []
        for i,k in enumerate(knowledge[col]):
            if truth == (i + 1 == rank):
                colknow.append(k)
            else:
                colknow.append(0)
        result.append(colknow)
    return result
    
HINT_COLOR = 0
HINT_RANK = 1
PLAY = 2
DISCARD = 3
    
class Action(object):
    def __init__(self, type, player=None, color=None, rank=None, card_index=None):
        self.type = type
        self.player = player
        self.color = color
        self.rank = rank
        self.card_index = card_index
    def __str__(self):
        if self.type == HINT_COLOR:
            return "hints " + str(self.player) + " about all their " + COLORNAMES[self.color] + " cards"
        if self.type == HINT_RANK:
            return "hints " + str(self.player) + " about all their " + str(self.rank)+"s"
        if self.type == PLAY:
            return "plays card at index " + str(self.card_index)
        if self.type == DISCARD:
            return "discards card at index " + str(self.card_index)
    def reflective(self):
        if self.type == HINT_COLOR:
            return "hint me about all my " + COLORNAMES[self.color] + " cards"
        if self.type == HINT_RANK:
            return "hint me about all my "  + str(self.rank)+"s"
        if self.type == PLAY:
            return "play your card at index " + str(self.card_index)
        if self.type == DISCARD:
            return "discard your card at index " + str(self.card_index)
    def __eq__(self, other):
        if other is None: return False
        if self.type == PLAY or self.type == DISCARD:
            return (self.type, self.card_index) == (other.type, other.card_index)
        return (self.type, self.player, self.color, self.rank, self.card_index) == (other.type, other.player, other.color, other.rank, other.card_index)
    def to_json(self):
        if self.type == HINT_COLOR:
            return {"type": "HINT_COLOR", "player": self.player, "color": COLORNAMES[self.color]}
        elif self.type == HINT_RANK:
            return {"type": "HINT_RANK", "player": self.player, "color": self.rank}
        elif self.type == PLAY:
            return {"type": "PLAY", "card_index": self.card_index}
        return {"type": "DISCARD", "card_index": self.card_index}

def format_card(card):
    return str(card)

def format_hand(hand):
    return ", ".join(map(format_card, hand))

class Game(object):
    def __init__(self, players, log=sys.stdout, format=0, deck=None):
        self.players = players
        self.hits = 3
        self.hints = 8
        self.current_player = 0
        self.board = [Card(c,0) for c in ALL_COLORS]
        self.played = []
        if deck is not None:
            self.deck = list(map(Card, deck))
        else:
            self.deck = make_deck()
        self.extra_turns = 0
        self.hands = []
        self.knowledge = []
        self.make_hands()
        self.trash = []
        self.log = log
        self.turn = 1
        self.format = format
        self.dopostsurvey = False
        self.study = False
        if self.format:
            print(self.deck, file=self.log)
    def make_hands(self):
        handsize = 4
        if len(self.players) < 4:
            handsize = 5
        for i, p in enumerate(self.players):
            self.hands.append([])
            self.knowledge.append([])
            for j in range(handsize):
                self.draw_card(i)
    def draw_card(self, pnr=None):
        if pnr is None:
            pnr = self.current_player
        if not self.deck:
            return
        self.hands[pnr].append(self.deck[0])
        self.knowledge[pnr].append(initial_knowledge())
        del self.deck[0]
    def perform(self, action):
        for p in self.players:
            p.inform(action, self.current_player)
        if format:
            print("MOVE:", self.current_player, action.type, action.card_index, action.player, action.color, action.rank, file=self.log)
        if action.type == HINT_COLOR:
            self.hints -= 1
            print(self.players[self.current_player].name, "hints", self.players[action.player].name, "about all their", COLORNAMES[action.color], "cards", "hints remaining:", self.hints, file=self.log)
            print(self.players[action.player].name, "has", format_hand(self.hands[action.player]), file=self.log)
            for card,knowledge in zip(self.hands[action.player],self.knowledge[action.player]):
                if card.color == action.color:
                    for i, k in enumerate(knowledge):
                        if i != card.color:
                            for i in range(len(k)):
                                k[i] = 0
                else:
                    for i in range(len(knowledge[action.color])):
                        knowledge[action.color][i] = 0
        elif action.type == HINT_RANK:
            self.hints -= 1
            print(self.players[self.current_player].name, "hints", self.players[action.player].name, "about all their", action.rank, "hints remaining:", self.hints, file=self.log)
            print(self.players[action.player].name, "has", format_hand(self.hands[action.player]), file=self.log)
            for card,knowledge in zip(self.hands[action.player],self.knowledge[action.player]):
                if card.rank == action.rank:
                    for k in knowledge:
                        for i in range(len(COUNTS)):
                            if i+1 != card.rank:
                                k[i] = 0
                else:
                    for k in knowledge:
                        k[action.rank-1] = 0
        elif action.type == PLAY:
            card = self.hands[self.current_player][action.card_index]
            print(self.players[self.current_player].name, "plays", format_card(card), end=' ', file=self.log)
            if self.board[card.color][1] == card.rank-1:
                self.board[card.color] = card
                self.played.append(card)
                if card.rank == 5:
                    self.hints += 1
                    self.hints = min(self.hints, 8)
                print("successfully! Board is now", format_hand(self.board), file=self.log)
            else:
                self.trash.append(card)
                self.hits -= 1
                print("and fails. Board was", format_hand(self.board), file=self.log)
            del self.hands[self.current_player][action.card_index]
            del self.knowledge[self.current_player][action.card_index]
            self.draw_card()
            print(self.players[self.current_player].name, "now has", format_hand(self.hands[self.current_player]), file=self.log)
        else:
            self.hints += 1 
            self.hints = min(self.hints, 8)
            self.trash.append(self.hands[self.current_player][action.card_index])
            print(self.players[self.current_player].name, "discards", format_card(self.hands[self.current_player][action.card_index]), file=self.log)
            print("trash is now", format_hand(self.trash), file=self.log)
            del self.hands[self.current_player][action.card_index]
            del self.knowledge[self.current_player][action.card_index]
            self.draw_card()
            print(self.players[self.current_player].name, "now has", format_hand(self.hands[self.current_player]), file=self.log)
    def valid_actions(self):
        valid = []
        for i in range(len(self.hands[self.current_player])):
            valid.append(Action(PLAY, card_index=i))
            valid.append(Action(DISCARD, card_index=i))
        if self.hints > 0:
            for i, p in enumerate(self.players):
                if i != self.current_player:
                    for color in set([card[0] for card in self.hands[i]]):
                        valid.append(Action(HINT_COLOR, player=i, color=color))
                    for rank in set([card[1] for card in self.hands[i]]):
                        valid.append(Action(HINT_RANK, player=i, rank=rank))
        return valid
    def run(self, turns=-1):
        self.turn = 1
        while not self.done() and (turns < 0 or self.turn < turns):
            self.turn += 1
            if not self.deck:
                self.extra_turns += 1
            hands = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            valid = self.valid_actions()
            action = None
            while action not in valid:
                if action:
                    action = self.players[self.current_player].get_action(self.current_player, hands, copy.deepcopy(self.knowledge), self.trash[:], self.played[:], self.board[:], valid, self.hints, self.hits, len(self.deck), action)
                else:
                    action = self.players[self.current_player].get_action(self.current_player, hands, copy.deepcopy(self.knowledge), self.trash[:], self.played[:], self.board[:], valid, self.hints, self.hits, len(self.deck))
                if action not in valid:
                    print("Tried to perform illegal action, retrying")
                    print("Action was:", action)
                    
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)
        print("Game done, hits left:", self.hits, file=self.log)
        points = self.score()
        print("Points:", points, file=self.log)
        return points
    def score(self):
        return sum([card.rank for card in self.board])
    def single_turn(self):
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            hands = []
            for i, h in enumerate(self.hands):
                if i == self.current_player:
                    hands.append([])
                else:
                    hands.append(h)
            action = self.players[self.current_player].get_action(self.current_player, hands, self.knowledge, self.trash, self.played, self.board, self.valid_actions(), self.hints, self.hits, len(self.deck))
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)
    def external_turn(self, action): 
        if not self.done():
            if not self.deck:
                self.extra_turns += 1
            self.perform(action)
            self.current_player += 1
            self.current_player %= len(self.players)
    def done(self):
        if self.extra_turns == len(self.players) or self.hits == 0:
            return True
        for card in self.board:
            if card.rank != 5:
                return False
        return True
    def finish(self):
        if self.format:
            print("Score", self.score(), file=self.log)
            self.log.close()
