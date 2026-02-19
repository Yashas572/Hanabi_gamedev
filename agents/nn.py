import hanabi

def card_to_features(card):
    if card is None:
        return [0]*10
    rank = [0]*5
    rank[card.rank-1] = 1
    color = [0]*5
    color[card.color] = 1
    return rank + color
    
def knowledge_to_features(knowledge):
    result = []
    for col in hanabi.ALL_COLORS:
        for i in range(5):
            rank = i+1
            count = hanabi.COUNTS[i]
            result.append(knowledge[col][i]*1.0/count)
    return result
    
def cardlist_to_features(cards):
    options = [[0]*5 for i in range(5)]
    for c in cards:
        options[c.color][c.rank-1] += 1
        
    return knowledge_to_features(options)
    
def action_to_features(action):
    result = [0]*20
    if action is None:
        return result
    if action.type == hanabi.HINT_COLOR:
        result[action.color] = 1
    elif action.type == hanabi.HINT_RANK:
        result[5 + action.rank - 1] = 1
    elif action.type in [hanabi.DISCARD, hanabi.PLAY]:
        result[5*action.type + action.card_index] = 1
    return result

def to_features(nr, hands, knowledge, trash, played, board, valid_actions, hints, hits, cards_left, last_action, action=None):
    otherhand = hands[1-nr]
    
    result = []
    if len(otherhand) < 5:
        otherhand = otherhand[:]
        otherhand.append(None)
    for c in otherhand:
        result.extend(card_to_features(c))
    
    for pk in knowledge:
        for k in pk:
            result.extend(knowledge_to_features(k))
    pl = cardlist_to_features(played)
    #breakpoint()
    result.extend(pl)
    result.extend(cardlist_to_features(trash))
    result.append(hints)
    result.append(hits)
    result.append(cards_left)
    result.extend(action_to_features(last_action))
    if action is not None:
        result.extend(action_to_features(action))
    return result
    
def header():
    result = []
    for i in range(5):
        for col in hanabi.COLORNAMES:
            result.append(f"partner_card_{i+1}_{col}")
        
        for r in range(5):        
            result.append(f"partner_card_{i+1}_{r+1}")
    
    for p in range(2):
        for i in range(5):
            for col in hanabi.COLORNAMES:
                for r in range(5):
                    result.append(f"knowledge_player_{p+1}_card_{i+1}_{col}_{r+1}")
    
    for col in hanabi.COLORNAMES:
        for r in range(5):
            result.append(f"played_{col}_{r+1}")
            
    for col in hanabi.COLORNAMES:
        for r in range(5):
            result.append(f"trashed_{col}_{r+1}")
            
    result.append("hints")
    result.append("hits")
    result.append("cards_left")
    pref = "last_action_"
    for p in range(2):
        for col in hanabi.COLORNAMES:
            result.append(f"{pref}hint_{col}")
        for r in range(5):
            result.append(f"{pref}hint_{r+1}")
        for i in range(5):
            result.append(f"{pref}play_{i+1}")
        for i in range(5):
            result.append(f"{pref}discard_{i+1}")
        pref = ""
    return ",".join(result)