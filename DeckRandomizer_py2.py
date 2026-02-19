# IMPORTANT: This *has* to be run with python 2.7 in order to recreate the same random decks as were used in the initial version of the experiment

import random
import glob
import os

GREEN = 0
YELLOW = 1
WHITE = 2
BLUE = 3
RED = 4
ALL_COLORS = [GREEN, YELLOW, WHITE, BLUE, RED]
COLORNAMES = ["green", "yellow", "white", "blue", "red"]

COUNTS = [3,2,2,2,1]

# semi-intelligently format cards in any format
def f(something):
    if type(something) == list:
        return map(f, something)
    elif type(something) == dict:
        return {k: something(v) for (k,v) in something.iteritems()}
    elif type(something) == tuple and len(something) == 2:
        return (COLORNAMES[something[0]],something[1])
    return something
   
def make_deck(seed):
    random.seed(seed)
    deck = []
    for col in ALL_COLORS:
        for num, cnt in enumerate(COUNTS):
            for i in xrange(cnt):
                deck.append((col, num+1))
    random.shuffle(deck)
    return deck

if __name__ == "__main__":
    #text file created from log, has same name
    for filename in glob.glob('log2\game*.log'):
        with open(os.path.join(os.getcwd(), filename), 'r') as f:
            for l in f:
                if l.startswith("Treatment:"):
                    seed = l.split(", ")
                    seed = seed[1]
                    seed = int(seed.replace(")", "").replace("\n", ""))
                    break

            filename = filename[4:]
            temp = filename.split(".")
            filename = temp[0]

            outFileName = "decks\\" + filename + ".txt"
            outFile = open(outFileName, "w")

            deck = make_deck(seed)

            outFile.writelines("seed: " + str(seed) + "\n")
            outFile.writelines(str(deck) + "\n")
            outFile.writelines(str(deck[:5]) + "\n")
            outFile.writelines(str(deck[5:10]) + "\n")
            outFile.writelines(str(deck[10:]) + "\n")
            outFile.close()