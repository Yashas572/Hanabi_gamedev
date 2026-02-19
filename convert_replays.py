import json
import hanabi
import agent
import os
import glob
import agents.nn

THRESHOLD = 18

def to_json(data):
    if isinstance(data, list):
        return [to_json(d) for d in data]
    elif isinstance(data, hanabi.Card):
        return data.to_json()
    else:
        return None

def knowledge_to_json(knowledge):
    result = {}
    for c in hanabi.ALL_COLORS:
        color = {}
        for i, n in enumerate(knowledge[c]):
            color[i + 1] = n
        result[hanabi.COLORNAMES[c]] = color
    return result

def knowledges_to_json(knowledge):
    return [knowledge_to_json(k) for k in knowledge]

class ReplayPlayer(agent.Agent):
    def __init__(self, name, pnr, gamelog=None):
        super().__init__(name, pnr)
        self.actions = []
        self.last_action = None
        self.gamelog = gamelog

    def get_action(self, nr, hands, knowledge, trash, played, board, valid_actions, hints, hits, cards_left):
        if not self.actions:
            return None

        action = self.actions.pop(0)
        features = agents.nn.to_features(
            nr, hands, knowledge, trash, played, board,
            valid_actions, hints, hits, cards_left,
            self.last_action, action
        )
        
        print(",".join(map(str, features)), file=self.gamelog)
        return action

    def inform(self, action, player):
        self.last_action = action

    def get_explanation(self):
        return []

def conv(s):
    if s == "None":
        return None
    return int(s)

def get_replay_info(fname):
    ai, deck, score = None, None, None
    try:
        with open(fname) as f:
            for line in f:
                if line.startswith("Treatment:"):
                    try:
                        items = line.strip().split()
                        ai = items[-2].strip("'(,").strip()
                        deck = int(items[-1].strip(")").strip())
                    except Exception:
                        deck = None
                elif line.startswith("Score"):
                    items = line.strip().split()
                    score = int(items[1])
    except Exception as e:
        print(f"⚠️ Error reading {fname}: {e}")
        return None, None, None

    return ai, deck, score

def convert(fname, csvf, gamelog, threshold=0):
    ai, deck, score = get_replay_info(fname)
    
    if score is None or score < threshold:
        return 0

    print(f"Processing {fname} (score: {score})")
    
    gid = os.path.basename(fname).split(".")[0]
    csvf.write(f"{gid},{ai},{deck},{score}\n")

    trace = []
    players = [ReplayPlayer("AI", 0, gamelog), ReplayPlayer("You", 1, gamelog)]

    try:
        with open(fname) as f:
            for line in f:
                if line.startswith("MOVE:"):
                    items = [s.strip() for s in line.strip().split()]
                    if len(items) < 7:
                        print(f"⚠️ Skipping malformed move in {fname}: {line}")
                        continue
                    const, pnum, type, cnr, pnr, col, num = items
                    action = hanabi.Action(conv(type), conv(pnr), conv(col), conv(num), conv(cnr))
                    players[int(pnum)].actions.append(action)
        
        game = hanabi.Game(players, log=None, deck=None)
        
        try:
            game.run()
        except Exception as e:
            print(f"⚠️ Skipping {fname} due to illegal action: {e}")
            return 0

        print(f"✅ Successfully added {fname} (score: {score})")
        return 1

    except Exception as e:
        print(f"⚠️ Error processing {fname}: {e}")
        return 0

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")

    gamelog = open("data/features.csv", "w")
    print(agents.nn.header(), file=gamelog)
    
    csvf = open("data/allgames.csv", "a")
    csvf.write("gid,ai,deck,score\n")

    total = 0

    log_paths = ["logs/log/game*.log", "logs/log2/game*.log"]

    for path in log_paths:
        files = glob.glob(path)
        if not files:
            print(f"⚠️ No files found matching {path}, skipping...")
            continue

        for f in files:
            total += convert(f, csvf, gamelog, THRESHOLD)

    csvf.close()
    gamelog.close()

    print(f"✅ Converted {total} files")
