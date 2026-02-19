from hanabi import *
import util
import agent
import random
import openai
import json
import os
has_key = False
try:
    import apikey
    openai.api_key = apikey.API_KEY
    has_key = True
except ImportError:
    apikey = os.environ.get("OPENAI_API_KEY")
    if apikey:
        openai.api_key = apikey
        has_key = True
    else:
        print("No OPENAI API key found. ChatGPT agent not available")
        print('Please create apikey.py with API_KEY = "YOURAPIKEYHERE" or place API key in the OPENAI_API_KEY environment variable.')

f = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "conventions.txt"))
strategy = f.read()
f.close()

# Function to send the game state and get the next move from ChatGPT
def get_next_move(client, game_state, canhint, previous):

    # Prompt to pass to ChatGPT, asking it for the next best move in JSON format
    prompt = f"""
You and I are playing Hanabi. I will provide you with the game state as you can see it, and I want you to suggest the next best move based on this game state. You cannot give yourself clues. When you are trying to give a clue, I will assume that it is for me, and you can only give me clues about colors or ranks I actually have in my hand. You can also only give clues if their are still clue tokens available. {canhint}

Assume that I will make inferences based on clues given about other my cards, and by counting cards that have already been played or discarded. Likewise, you should consider all knowledge, explicitly given as well as inferred when deciding what to do next.

Each successfully played card gives a point, and the goal is to reach as many points as possible. Therefore, playing cards is a priority, followed by giving clues about playable cards (when possible).

Please return your move in the following JSON format:
{{
  "action": "play" or "discard" or "give_clue",
  "card_index": [if play or discard] (0-indexed position of card in hand),
  "clue": {{
    "clue_type": "color" or "rank",
    "value": "blue" or "2" etc.
  }} [only if giving a clue]
}}

The current game state is as follows:
{game_state}

{strategy}

{previous}

Think step by step and provide your reasoning for your decision. End your response with a single line containing only of "JSON:" followed by a valid JSON object on the next line that matches the required format. Do not use markdown formatting.
"""
    
    # Make the API call to ChatGPT
    try:
        response = client.chat.completions.create(
            model="o1",  # Choose the model
            messages=[
                #{"role": "system", "content": "You are a Hanabi expert."},
                {"role": "user", "content": "You are a Hanabi expert." + prompt}
            ],
            #max_tokens=2000,  # Limit the response length
            #temperature=0.1,  # Low temperature for logical and deterministic moves
        )
        
        # Extract the message from the response
        chat_response = response.choices[0].message.content
        print("Raw ChatGPT response:", chat_response)  # Debugging line
        chat_response = chat_response.replace("```json", "").replace("```", "").strip()
        if chat_response.startswith("```json"):
            chat_response = chat_response.strip("`")
            chat_response = chat_response[4:]
        # Parse the response into JSON
        splitter = chat_response.index("JSON:")
        reason = chat_response[:splitter]
        action = chat_response[splitter+5:]
        print("Extracted JSON:", action)  # Debugging line
        #breakpoint()
        
        next_move = json.loads(action)
        
        return next_move
    
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response from ChatGPT"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        #breakpoint()
        return {"error": str(e)}
        
def commatize(what, connector="or"):
    what = list(what)
    if len(what) == 1:
        return str(what[0])
    return ", ".join(map(str, what[:-1])) + " " + connector + " " + str(what[-1])

def to_board(c):
    result = []
    for r in range(1,c.rank+1):
        result.append(r)
    return result
    
def to_knowledge_string(idx, colors, ranks, who):
    result = f"The card at index {idx}"
    if len(colors) == 5 and len(ranks) == 5:
        return result + f" could be any card; {who} know nothing about it.\n"
    if len(colors) == 1:
        result += " is " + colors[0]
    elif len(colors) == 5:
        result += " could be any color"
    else:
        result += " could be " + commatize(colors)
    if len(ranks) == 1:
        result += " and its rank is " + str(ranks[0])
    elif len(ranks) == 5:
        result += ", but it could be of any rank"
    else:
        result += " and it could be a " + commatize(ranks)
    return result + "\n"
        

class ChatGPTPlayer(agent.Agent):
    def __init__(self, name, pnr):
        self.name = name
        self.explanation = []
        self.client = openai.OpenAI(api_key=apikey.API_KEY)
    def get_action(self, nr, hands, knowledge, trash, played, board, valid_actions, hints, hits, cards_left, previous=None):
        players = {}
        state = ""
        selfstate = ""
        otherstate = ""
        for i,h in enumerate(hands):
            who = "I" if h else "you"
            whos = "my" if h else "your"
            knows = "What " + who + " know about the cards in " + whos + " hand:\n"
            for j,k in enumerate(knowledge[i]):
                colors = util.get_possible_colors(k)
                ranks = util.get_possible_ranks(k)
                knows += to_knowledge_string(j, [COLORNAMES[c] for c in colors], list(ranks), who)
                
            if h:
                name = "other_player"
                otherstate = "Cards I have in my hand:\n"
                for c in h:
                    otherstate += str(c) + "\n"
                otherstate += "\n" + knows
                    
                
            else:
                ha = [{"color": "unknown", "rank": "unknown"} for c in knowledge[i]]
                name = "you"
                selfstate = "You cannot see your own cards.\n\n"
                selfstate += knows
            know = []
            
                
        state = otherstate + "\n\n" + selfstate + "\n\n"
        
        state += "Cards that have been successfully played already:\n"
        for c in ALL_COLORS:
            if board[c].rank > 0:
                state += COLORNAMES[c] + ": " + commatize(to_board(board[c]), "and") + "\n"
            else:
                state += "No " + COLORNAMES[c] + " card has been played yet.\n"
        
        if trash:
            state += "\nCards that have been discarded so far:\n"
            state += commatize(map(str, trash), "and") + "\n"
        else:
            state += "\nNo cards have been discarded yet.\n"
        state += "\n"
        state += "There are " + (str(hints) if hints > 0 else "no") + " clue tokens available.\n"
        state += "We can only afford to make " + str(hits) + " more mistakes.\n"
        state += "There are " + (str(cards_left) if cards_left > 0 else "no") + " cards left in the deck.\n"
        
        #breakpoint()
        prev = ""
        if previous:
            prev = "You just tried to " + previous.reflective() + ", which is not a valid action."
        action = get_next_move(self.client, state, "Right now there are no clue tokens available, so you cannot give any clues." if hints == 0 else "", prev)
        if action["action"] == "play":
            return Action(PLAY, card_index=action["card_index"])
        if action["action"] == "discard":
            return Action(DISCARD, card_index=action["card_index"])
        if action["clue"]["clue_type"] == "color":
            return Action(HINT_COLOR, player=1-nr, color=COLORNAMES.index(action["clue"]["value"]))
        return Action(HINT_RANK, player=1-nr, rank=int(action["clue"]["value"]))
        
if has_key:
    agent.register("chatgpt", "ChatGPT Player", ChatGPTPlayer)
