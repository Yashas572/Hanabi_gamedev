# Neural Network Hanabi Agent

[data/features.zip](data/features.zip) contains a single csv file encoding all actions performed by human players in games with an outcome of at least 20 points. Each row contains:

- `partner_card_x_property` one-hot encoding for each card (x is the index in hand, 1 to 5) the other player is holding whether it is a red,green,blue,yellow,white card (or a 1,2,3,4,5)
- `knowledge_player_x_card_y_color_rank` encoding for each player (x is 1,2), and each card in their hand (y going from 1 to 5) whether they believe (based on given hints) that it could be that card (e.g. `knowledge_player_1_card_2_red_4` would be 1 if player 1 believes their second card *could be* a red 4 (initially, each player believes that each card could be *anything*, so all columns would be `1`s!
- `played_color_rank` encodes if a certain card has already been (successfully!) played.
- `trashed_color_rank` encodes if a certain card is in the trash/discard.
- `hints` represents how many hint tokens are left (max 8)
- `hits` represents how many mistakes the players have made so far (max 3)
- `cards_left` represents how many cards are left in the deck (there are 50 cards total; players in a two-player game are dealt 5 each, so this is 40 at the start of the game)
- `last_action_x` is a one-hot encoding of the action just performed by the *other* player. This is useful, because players typically perform actions that should be responded to (especially hint actions)
- The last 20 columns represent the possible actions, and are a one-hot encoding of the action actually performed by the human player in the given situation.

[agents/nnagent.py](agents/nnagent.py) contains an empty shell for the eventual Neural Network agent. Essentially, we'd train a NN on the data in features.csv, and then use it to predict the "correct" action each turn. 

# Testing

`main.py` allows you to run a large number of games to determine the average points the agent scores. You could, e.g. use `python main.py -n 100 nn nn` to run 100 games of the nn agent playing with itself (`python main.py --list` shows you the available agents; `python main.py --help` shows you all options). Eventually we will want to run more than 10 000 games, but that might take a while.

# Data Extraction

With a threshold of 20 points, we got almost 200k data points, but if we were to set the threshold lower, we'd incorporate more games and thus get more data, if necessary. You can run (convert_replays.py)[convert_replays.py] after you set a new value for `THRESHOLD` in that file to get more data points. You'll also need to extract `logs.zip`, which contains the actual replay files.

# ChatGPT Agent

[agents/chatgpt.py](agents/chatgpt.py) contains my current version of the ChatGPT agent, that converts the current game state into words, and adds some Hanabi strategy conventions to try to get ChatGPT to select a good move. Maybe it'll work better now, with the recent advancements? You'll need an apikey that you can either provide in apikey.py (with `API_KEY = "KEYHERE"`) or as an environment variable `OPENAI_API_KEY`. Let me know if you need an API key, but please don't commit it to the git repo.