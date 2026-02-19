import http.server
import socketserver
import threading
import time
import shutil
import os
import hanabi
import random
import hashlib
import tutorial
import sys
import traceback
import threading
import agent
from cgi import parse_header, parse_multipart
from urllib.parse import parse_qs
from serverconf import HOST_NAME, PORT_NUMBER
import importlib

for f in os.listdir("agents"):
    if f.endswith(".py") and f != "__init__.py":
        importlib.import_module("agents."+f[:-3])

HAND = 0
TRASH = 1
BOARD = 2
TRASHP = 3

debug = True


errlog = sys.stdout
if not debug:
    errlog = open("hanabi.log", "w")



template = """

<table width="100%%">
<tr><td width="15%%" valign="top"><br/> 

<table style="font-size:14pt" width="100%%">
<tr><td>
<table width="100%%" style="font-size:14pt"> 
<tr><td width="85%%"><b>Hint tokens left:</b></td><td> %s</td></tr>
<tr><td><b>Mistakes made so far:</b></td><td> %s</td></tr>
<tr><td><b>Cards left in deck:</b></td><td> %s</td></tr>
</table>

</td>
</tr>
<tr><td>
<center><h2>Discarded</h2></center>
%s
</td></tr>
</table>
%s
</td>
<td>
<center>
<h2> Other player </h2>
<table>
<tr><td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
</tr>
%s
<tr><td colspan="5"><center><h2>You</h2></center></td></tr>
<tr><td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
    <td>%s<br/>%s</td>
</tr>
</table>
</center>
</td>
<td width="15%%" valign="top"><center> <h2>Actions</h2> </center><br/>
<div style="font-size:14pt">
%s
</div></td>
</tr>
</table>
"""

board_template = """<tr><td colspan="5"><center>%s</center></td></tr>
<tr><td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
    <td>%s</td>
</tr>"""

def format_board(game, show, gid):
    if not game.started:
        return '<tr><td colspan="5"><center><h1><a href="/gid%s/start/">Start Game</a></h1></center></td></tr>'%gid
    title = "<h2>Board</h2>"
    if game.done():
        if game.dopostsurvey:
            title = "<h2>Game End<h2>Points: " + str(game.score()) + '<br/><a href="/postsurvey/%s">Continue</a>'%gid
        elif game.study:
            title = "<h2>Game End<h2>Points: " + str(game.score()) + '<br/><a href="/new/study/%s">Play again</a>'%gid
        else:
            title = "<h2>Game End<h2>Points: " + str(game.score()) + '<br/><a href="/restart/">New game</a>'
    def make_board_image(xxx_todo_changeme):
        (i,card) = xxx_todo_changeme
        return make_card_image(card, [], (BOARD,0,i) in show)
    boardcards = list(map(make_board_image, enumerate(game.board)))
    args = tuple([title] + boardcards)
    return board_template%args

def format_action(action_log, gid, replay=None):
    (i, (action, player, card)) = action_log
    result = "You "
    other = "the AI"
    otherp = "their"
    if player == 0:
        result = "AI "
        other = "you"
        otherp = "your"
    if i <= 1:
        result += " just "
     
    if action.type == hanabi.PLAY:
        result += " played <b>" + hanabi.format_card(card) + "</b>"
    elif action.type == hanabi.DISCARD:
        result += " discarded <b>" + hanabi.format_card(card) + "</b>"
    else:
        result += " hinted %s about all %s "%(other, otherp)
        if action.type == hanabi.HINT_COLOR:
            result += hanabi.COLORNAMES[action.color] + " cards"
        else:
            result += str(action.rank) + "s"
    if i == 0:
        link = ''
        if debug:
            if replay:
                (gid,round,info) = replay
                explainlink =  '<a href="/replay/%s/%d/explain" target="_blank">(Explain)</a>'%(gid, round)
            else:
                explainlink =  '<a href="/gid%s/explain" target="_blank">(Explain)</a>'%gid
        
        return "<b>" + result + '</b>%s<br/><br/>'%explainlink
    if i == 1:
        return result + '<br/><br/>'
    return '<div style="color: gray;">' + result + '</div>'

def show_game_state(game, player, turn, gid, replay=False):
    
    def make_ai_card(i, card, highlight):
        hintlinks = [("Hint Rank", "/gid%s/%d/hintrank/%d"%(gid,turn,i)), ("Hint Color", "/gid%s/%d/hintcolor/%d"%(gid,turn,i))]
        if replay:
            (pgid,round,info) = replay 
            hintlinks = [("Hint Rank", "/takeover/%s/%d/hintrank/%d"%(pgid,round,i)), ("Hint Color", "/takeover/%s/%d/hintcolor/%d"%(pgid,round,i))]     
        if game.hints == 0 or game.done() or not game.started:
            hintlinks = []
            highlight = False
        return make_card_image(card, hintlinks, highlight)
    aicards = []
    for i,c in enumerate(game.hands[0]):
        aicards.append(make_ai_card(i, c, (HAND, 0, i) in player.show))
        aicards.append(", ".join(player.aiknows[i]))
    
    while len(aicards) < 10:
        aicards.append("")
    def make_your_card(i, card, highlight):
        playlinks = [("Play", "/gid%s/%d/play/%d"%(gid,turn,i)), ("Discard", "/gid%s/%d/discard/%d"%(gid,turn,i))]
        if replay:
            (pgid,round,info) = replay 
            playlinks = [("Play", "/takeover/%s/%d/play/%d"%(pgid,round,i)), ("Discard", "/takeover/%s/%d/discard/%d"%(pgid,round,i))]
        if game.done() or not game.started:
            playlinks = []
        return unknown_card_image(playlinks, highlight)
    yourcards = []
    for i,c in enumerate(game.hands[1]):
        if game.done():
            yourcards.append(make_ai_card(i,c, False))
        else:
            yourcards.append(make_your_card(i,c, (HAND, 1, i) in player.show))
        yourcards.append(", ".join(player.knows[i]))
    while len(yourcards) < 10:
        yourcards.append("")
    board = format_board(game, player.show, gid)
    foundtrash = []
    def format_trash(c):
        result = hanabi.format_card(c)
        if (TRASH, 0, -1) in player.show and c == game.trash[-1] and not foundtrash[0]:
            foundtrash[0] = True
            return result + "<b>(just discarded)</b>"
        if (TRASHP, 0, -1) in player.show and c == game.trash[-1] and not foundtrash[0]:
            foundtrash[0] = True
            return result + "<b>(just played)</b>"
        return result
    discarded = {}
    trashhtml = '<table width="100%%" style="border-collapse: collapse"><tr>\n'
    for i,c in enumerate(hanabi.ALL_COLORS):
        style = "border-bottom: 1px solid #000"
        if i > 0:
            style += "; border-left: 1px solid #000"
        trashhtml += '<td valign="top" align="center" style="%s" width="20%%">%s</td>\n'%(style, hanabi.COLORNAMES[c])
        discarded[c] = []
        for (col,num) in game.trash:
            if col == c:
                if (TRASH, 0, -1) in player.show and (col,num) == game.trash[-1] and (col,num) not in foundtrash:
                    foundtrash.append((col,num))
                    discarded[c].append('<div style="color: red;">%d</div>'%(num))
                elif (TRASH, 0, -2) in player.show and (col,num) == game.trash[-2] and (col,num) not in foundtrash:
                    foundtrash.append((col,num))
                    discarded[c].append('<div style="color: red;">%d</div>'%(num))
                else:
                    discarded[c].append('<div>%d</div>'%num)
        discarded[c].sort()
    trashhtml += '</tr><tr style="height: 150pt">\n'
    for i,c in enumerate(hanabi.ALL_COLORS):
        style= ' style="vertical-align:top"'
        if i > 0:
            style=  ' style="border-left: 1px solid #000; vertical-align:top"'
        trashhtml += '<td valigh="top" align="center" %s>%s</td>\n'%(style, "\n".join(discarded[c]))
    trashhtml += "</tr></table><br/>"
    if foundtrash:
        trashhtml += 'Cards written in <font color="red">red</font> have been discarded or misplayed since your last turn.'
    
    trash = [trashhtml]
    hints = game.hints
    if hints == 0:
        hints = '<div style="font-weight: bold; font-size: 20pt">0</div>'
    mistakes = 3-game.hits
    if mistakes == 2:
        mistakes = '<div style="font-weight: bold; font-size: 20pt; color: red">2</div>'
    cardsleft = len(game.deck)
    if cardsleft < 5:
        cardsleft = '<div style="font-weight: bold; font-size: 20pt">%d</div>'%cardsleft
    replaycontrol = ""
    if replay:
        (gid,round,info) = replay
        replaycontrol = "<br/><br/><br/><br/>"
        if not foundtrash:
             replaycontrol += "<br/><br/><br/>"
        replaycontrol += '<table style="font-size:14pt" width="100%" border="1">'
        replaycontrol += '<tr><td colspan="3">Replay of game ' + gid + '</td></tr>\n'
        replaycontrol += '<tr><td width="33%">'
        if round > 2:
            replaycontrol += '<a href="/replay/%s/%d">&lt;&lt;&lt;</a>'%(gid,round-2)
        else:
            replaycontrol += "&lt;&lt;&lt;"
        replaycontrol += '</td><td width="33%" align="center">'
        replaycontrol += " Turn " + str(round) 
        replaycontrol += '</td><td width="33%" align="right">'
        if game.done():
            replaycontrol += "&gt;&gt;&gt;"
        else:
            replaycontrol += '<a href="/replay/%s/%d">&gt;&gt;&gt;</a>'%(gid,round+2)
        replaycontrol += "</td></tr>"
        ai,deck,score = info
        
        replaycontrol += '<tr><td colspan="3" align="center">%s AI, %s, deck %d</td></tr>'%(ai, format_score(score), deck)
        root = get_replay_root("log/game%s.log"%gid)
        #if root == gid:
        #    replaycontrol += '<tr><td colspan="3" align="center"><a href="/showsurvey/%s/full" target="_blank">Show survey answers</a></td></tr>'%root
        #else:
        #    replaycontrol += '<tr><td colspan="3" align="center"><a href="/showsurvey/%s" target="_blank">Show survey answers</a></td></tr>'%root
        replaycontrol += "</table>"
    args = tuple([str(hints), str(mistakes), str(cardsleft)] + trash + [replaycontrol] + aicards + [board] + yourcards + ["\n".join([format_action(x,gid, replay) for x in enumerate(list(reversed(player.actions))[:15])])])
    return template%args


def make_circle(x, y, col):
    x += random.randint(-5,5)
    y += random.randint(-5,5)
    r0 = random.randint(0,180)
    r1 = r0 + 360
    result = """
    <circle cx="%f" cy="%d" r="10" stroke="%s" stroke-width="4" fill="none">
       <animate attributeName="r" from="1" to="22" dur="2s" repeatCount="indefinite"/>
       <animate attributeName="stroke-dasharray" values="32, 32; 16, 16; 8,8; 4,4; 2,6; 1,7;" dur="2s" repeatCount="indefinite" calcMode="discrete"/>
       <animateTransform attributeName="transform" attributeType="XML" type="rotate" from="%f %f %f" to="%f %f %f" dur="2s" begin="0s" repeatCount="indefinite"/>
    </circle>
    """
    return result%(x,y,col, r0, x,y, r1, x,y)
    

def make_card_image(card, links=[], highlight=False):
    image = """
<svg version="1.1" width="125" height="160" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <rect width="125" height="160" x="0" y="0" fill="#66ccff"%s/>
    <text x="8" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    <text x="50" y="24" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
    %s
    %s
    <text x="108" y="155" fill="%s" font-family="Arial" font-size="24" stroke="black">%s</text>
</svg>
"""
    ly = 130
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 23
    l = 35 # left
    r = 90 # right
    c = 62 # center (horizontal)
    
    t = 45 # top
    m = 70 # middle (vertical)
    b = 95 # bottom
    circles = {0: [], 1: [(c,m)], 2: [(l,t),(r,b)], 3: [(l,b), (r,b), (c,t)], 4: [(l,b), (r,b), (l,t), (r,t)], 5:[(l,b), (r,b), (l,t), (r,t), (c,m)]}
    circ = "\n".join([make_circle(x_y[0],x_y[1],hanabi.COLORNAMES[card.color]) for x_y in circles[card.rank]])
    highlighttext = ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image%(highlighttext, hanabi.COLORNAMES[card.color],str(card.rank), hanabi.COLORNAMES[card.color], hanabi.COLORNAMES[card.color], circ, linktext, hanabi.COLORNAMES[card.color],str(card.rank))

    
def unknown_card_image(links=[], highlight=False):
    image = """
<svg version="1.1" width="125" height="160" xmlns="http://www.w3.org/2000/svg">
    <rect width="125" height="160" x="0" y="0" fill="#66ccff"%s/>
    %s
    <text x="35" y="90" fill="black" font-family="Arial" font-size="100">?</text>
</svg>
"""
    ly = 130
    linktext = ""
    for (text,target) in links:
        linktext += """<a xlink:href="%s">
                           <text x="8" y="%d" fill="blue" font-family="Arial" font-size="12" text-decoration="underline">%s</text>
                       </a>
                       """%(target, ly, text)
        ly += 23
    highlighttext= ""
    if highlight:
        highlighttext = ' stroke="red" stroke-width="4"'
    return image%(highlighttext,linktext)
    
gameslock = threading.Lock()
games = {}
participantslock = threading.Lock()
participants = {}
participantstarts = {}



class HTTPPlayer(agent.Agent):
    def __init__(self, name, pnr):
        self.name = name
        self.pnr = pnr
        self.actions = []
        self.knows = [set() for i in range(5)]
        self.aiknows = [set() for i in range(5)]
        self.show = []
    
    def inform(self, action, player):
        if player == 1:
            self.show = []
        card = None
        if action.type in [hanabi.PLAY, hanabi.DISCARD]:
            card = self.game.hands[player][action.card_index]
        self.actions.append((action, player,card))
        if player != self.pnr: 
            if action.type == hanabi.HINT_COLOR:
                for i, (col,num) in enumerate(self.game.hands[self.pnr]):
                    if col == action.color:
                        self.knows[i].add(hanabi.COLORNAMES[col])
                        self.show.append((HAND,self.pnr,i))
            elif action.type == hanabi.HINT_RANK:
                for i, (col,num) in enumerate(self.game.hands[self.pnr]):
                    if num == action.rank:
                        self.knows[i].add(str(num))
                        self.show.append((HAND,self.pnr,i))
        else:
            if action.type == hanabi.HINT_COLOR:
                for i, (col,num) in enumerate(self.game.hands[action.player]):
                    if col == action.color:
                        self.aiknows[i].add(hanabi.COLORNAMES[col])
                        self.show.append((HAND,action.player,i))
            elif action.type == hanabi.HINT_RANK:
                for i, (col,num) in enumerate(self.game.hands[action.player]):
                    if num == action.rank:
                        self.aiknows[i].add(str(num))
                        self.show.append((HAND,action.player,i))
 
        if action.type in [hanabi.PLAY, hanabi.DISCARD] and player == 0:
            newshow = []
            for (where,who,what) in self.show:
                if who == 0 and where == HAND:
                    if what < action.card_index:
                        newshow.append((where,who,what))
                    elif what > action.card_index:
                        newshow.append((where,who,what-1))
                else:
                    newshow.append((where,who,what))
            self.show = newshow
        if action.type == hanabi.DISCARD:
            newshow = []
            for (t,w1,w2) in self.show:
                if t == TRASH:
                    newshow.append((t,w1,w2-1))
                else:
                    newshow.append((t,w1,w2))
            self.show = newshow
            self.show.append((TRASH,0,-1))
            
        elif action.type == hanabi.PLAY:
            (col,num) = self.game.hands[player][action.card_index]
            if self.game.board[col][1] + 1 == num:
                self.show.append((BOARD,0,col))
            else:
                newshow = []
                for (t,w1,w2) in self.show:
                    if t == TRASH:
                        newshow.append((t,w1,w2-1))
                    else:
                        newshow.append((t,w1,w2))
                self.show = newshow
                self.show.append((TRASH,0,-1))
        if player == self.pnr and action.type in [hanabi.PLAY, hanabi.DISCARD]:
            del self.knows[action.card_index]
            self.knows.append(set())
        if player != self.pnr and action.type in [hanabi.PLAY, hanabi.DISCARD]:
            del self.aiknows[action.card_index]
            self.aiknows.append(set())
            
class ReplayHTTPPlayer(HTTPPlayer):
    def __init__(self, name, pnr):
        super(ReplayHTTPPlayer, self).__init__(name,pnr)
        self.actions = []
    def get_action(self, nr, hands, knowledge, trash, played, board, valid_actions, hints, hits, cards_left):
        return self.actions.pop(0)
            
class ReplayPlayer(agent.Agent):
    def __init__(self, name, pnr):
        super(ReplayPlayer, self).__init__(name,pnr)
        self.actions = []
        self.realplayer = None
    def get_action(self, nr, hands, knowledge, trash, played, board, valid_actions, hints, hits, cards_left):
        if self.realplayer:
            self.realplayer.get_action(nr, hands, knowledge, trash, played, board, valid_actions, hints, hits, cards_left)
        return self.actions.pop(0)
    def inform(self, action, player):
        if self.realplayer:
            self.realplayer.inform(action, player)
    def get_explanation(self):
        if self.realplayer:
            return self.realplayer.get_explanation()
        return []
        
def get_replay_info(fname):
    f = open(fname)
    ai = None
    deck = None
    score = None
    try:
        for l in f:
            if l.startswith("Treatment:"):
                try:
                    items = l.strip().split()
                    ai = items[-2].strip("'(,")
                    deck = int(items[-1].strip(")"))
                except Exception:
                    deck = None
            elif l.startswith("Score"):
                items = l.strip().split()
                score = int(items[1])
    except Exception:
        f.close()
        return (None, None, None)
    f.close()
    
    return (ai, deck, score)
    
def get_replay_root(fname):
    f = open(fname)
    parent = None
    for l in f:
        if l.startswith("Old GID:"):
            parent = l[8:].strip()
            break
    f.close()
    if parent:
        return get_replay_root("log/game%s.log"%parent)
    return fname[8:24]
    
def format_score(sc):
    if sc is None:
        return "not finished"
    return "%d points"%sc
    
class NullStream(object):
    def write(self, *args):
        pass
    def close(self):
        pass


class MyHandler(http.server.BaseHTTPRequestHandler):
    def respond(s, response):
        s.wfile.write(response.encode("utf-8"))

    def do_HEAD(s):
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
    def do_GET(s):
        try:
            return s.perform_response()
        except Exception:
            errlog.write(traceback.format_exc())
            errlog.flush()
            
    def invalid(s, gid):
        if len(gid) != 16:
            return True
        for c in gid:
            if c not in "0123456789abcdef":
                return True
        if not os.path.exists("log/game%s.log"%gid):
            return True
        return False
    
    def perform_response(s):
        """Respond to a GET request."""
        global games
        
        game = None
        player = None
        turn = None
        gid = None
        path = s.path
        if s.path.startswith("/gid"):
            gid = s.path[4:20]
            gameslock.acquire()
            if gid in games:
                game, player, turn = games[gid]
            gameslock.release()
            path = s.path[20:]
        
        if s.path == "/hanabiui.png":
            f = open("hanabiui.png", "rb")
            s.send_response(200)
            s.send_header("Content-type", "image/png")
            s.end_headers()
            shutil.copyfileobj(f, s.wfile)
            f.close()
            return
        
        if s.path.startswith("/favicon"):
            s.send_response(200)
            s.end_headers()
            return
            
        # I honestly don't know why, but I already received a request for http://www.google.com
        if s.path.startswith("http://"): 
            s.send_response(400)
            s.end_headers()
            return
            
        if s.path.startswith("/robots.txt"):
            s.send_response(200)
            s.send_header("Content-type", "text/plain")
            s.end_headers()
            s.respond("User-agent: *\n")
            s.respond("Disallow: /\n")
            return
            
        
        
        s.send_response(200)
        s.send_header("Content-type", "text/html")
        s.end_headers()
        
        
        if path.startswith("/tutorial"):
            gid = s.getgid()
            todelete = []
            participantslock.acquire()
            try:
                for g in participantstarts:
                    if participantstarts[g] + 7200 < time.time():
                        todelete.append(g)
                for d in todelete:
                    del participants[d]
                    del participantstarts[d]
            except Exception:
                errlog.write("Error cleaning participants:\n")
                errlog.write(traceback.format_exc())
            participants[gid] = open("log/survey%s.log"%gid, "w")
            participantstarts[gid] = time.time()
            participantslock.release()
            s.respond("<html><head><title>Hanabi</title></head>")
            s.respond('<body><center>')
            s.respond(tutorial.intro)
            if not path.startswith("/tutorial/newtab"):
                s.respond('<br/>If you want to open this tutorial in a new tab for reference during the game, click here  <a href="/tutorial/newtab" target="_blank">here</a><br/>\n')
                s.respond('<form action="/tutorialdone" method="POST"><input type="hidden" value="%s" name="gid"/><input type="submit" value="Continue"/></form>\n'%(gid))
            
            s.respond(tutorial.summary)
            
            s.respond('</center></body></html>')
            return
            
        if s.path.startswith("/postsurvey/"):
            gid = s.path[12:]
            if gid in participants:
                s.postsurvey(gid)
            return
            
        doaction = True
        replay = False
        if path.startswith("/new/") and debug:
            
        
            type = s.path[5:]
            if type in agent.ids():
                ai = agent.make(type, type, 0)
            turn = 1
            player = HTTPPlayer("You", 1)
            random.seed(None)
            nr = random.randint(6,10000)
            
            t = (type,nr)
            gid = s.getgid()
            log = open("log/game%s.log"%gid, "w")
            print("Treatment:", t, file=log)
            random.seed(nr)
            game = hanabi.Game([ai,player], log=log, format=1)
            player.game = game
            game.treatment = t
            game.ping = time.time()
            game.started = False
            todelete = []
            gameslock.acquire()
            for g in games:
                if games[g][0].ping + 3600 < time.time():
                    todelete.append(g)
            for g in todelete:
                del games[g]
            games[gid] = (game,player,turn)
            gameslock.release()
            
        elif path.startswith("/replay/") and debug:
            gid = path[8:24]
            rest = path[25:]
            
            items = rest.split("/")
            round = items[0]
            if len(items) > 1 and items[1] == "explain":
                path = "/explain"
            
            fname = "log/game%s.log"%gid
            try:
                round = int(round)
            except Exception:
                import traceback
                traceback.print_exc()
                round = None
            if "/" in gid or "\\" in gid or round is None or not os.path.exists(fname):
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game ID</h1>\n')
                s.respond("</body></html>")
                return
            
            info = get_replay_info(fname)
            
            replay = (gid,round,info)
            f = open(fname)
            players = [ReplayPlayer("AI", 0), ReplayHTTPPlayer("You", 1)]
            i = 0
            def convert(s):
                if s == "None":
                    return None
                return int(s)
            for l in f:
                if l.startswith("Treatment:"):
                    try:
                        items = l.strip().split()
                        ai = items[-2].strip("'(,")
                        players[0].realplayer = agent.make(ai, ai, 0)
                        deck = int(items[-1].strip(")"))
                        
                    except Exception:
                        deck = None
                elif l.startswith("MOVE:"):
                    items = [s.strip() for s in l.strip().split()]
                    const, pnum, type, cnr, pnr, col, num = items
                    a = hanabi.Action(convert(type), convert(pnr), convert(col), convert(num), convert(cnr))
                    players[int(pnum)].actions.append(a)
                    i += 1
                if i >= round:
                    break
            if not deck: 
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game Log</h1>\n')
                s.respond("</body></html>")
                return
            player = players[1]
            random.seed(deck)
            game = hanabi.Game(players, log=NullStream())
            player.game = game
            game.started = time.time()
            for i in range(round):
                game.single_turn()
            doaction = False
            turn = -1
            gid = ""
        elif path.startswith("/starttakeover/"):
            items = [_f for _f in path.split("/") if _f]
            if len(items) < 6:
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game ID</h1>\n')
                s.respond("</body></html>")
                return
            gid, round, ai, action, arg = items[1:]
            oldgid = gid
            fname = "log/game%s.log"%gid
            try:
                round = int(round)
            except Exception:
                import traceback
                traceback.print_exc()
                round = None
            if "/" in gid or "\\" in gid or round is None or not os.path.exists(fname):
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game ID</h1>\n')
                s.respond("</body></html>")
                return
            
            info = get_replay_info(fname)
            f = open(fname)
            players = [ReplayPlayer(ai.capitalize(), 0), ReplayHTTPPlayer("You", 1)]
            players[0].realplayer = agent.make(ai, ai.capitalize(), 0)
            i = 0
            def convert(s):
                if s == "None":
                    return None
                return int(s)
            for l in f:
                if l.startswith("Treatment:"):
                    try:
                        items = l.strip().split()
                        deck = int(items[-1].strip(")"))
                    except Exception:
                        deck = None
                elif l.startswith("MOVE:"):
                    items = [s.strip() for s in l.strip().split()]
                    const, pnum, type, cnr, pnr, col, num = items
                    a = hanabi.Action(convert(type), convert(pnr), convert(col), convert(num), convert(cnr))
                    players[int(pnum)].actions.append(a)
                    i += 1
                if i >= round:
                    break
            if not deck: 
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game Log</h1>\n')
                s.respond("</body></html>")
                return
            player = players[1]
            
            gid = s.getgid()
            t = (ai,deck)
            log = NullStream()
            random.seed(deck)
            game = hanabi.Game(players, log=log, format=1)
            player.game = game
            game.treatment = t
            game.ping = time.time()
            game.started = True
            for i in range(round):
                game.single_turn()
            game.players[0] = game.players[0].realplayer
            game.current_player = 1
            doaction = False
            turn = round+1
            gameslock.acquire()
            games[gid] = (game,players[1],turn)
            gameslock.release()
            path = "/%d/%s/%s"%(turn, action, arg)
        
        elif path.startswith("/selectreplay/"):
            filters = path[14:].split("/")
            filters = dict(list(zip(filters[::2], filters[1::2])))
            s.respond("<html><head><title>Hanabi</title></head>\n")
            s.respond('<body>')
            s.respond('<h1>Replay selection</h1>')
            s.respond('<h2>Filters:</h2>')
            def format_filters(f):
                result = ""
                for k in f:
                    result += "%s/%s/"%(k,f[k])
                return result
                
            def update_filters(f, k, v):
                result = dict(f)
                if v:
                    result[k] = v
                elif k in result:
                    del result[k]
                return result
            
            s.respond('<p>AI: ')
            
            ais = []
            for id in agent.ids():
                ais.append((agent.get(id)[0],id))
            for i,(display,value) in enumerate(ais):
                s.respond(' <a href="/selectreplay/%s">%s</a> - '%(format_filters(update_filters(filters, "ai", value)), display))
            s.respond(' <a href="/selectreplay/%s">any</a></p>'%(format_filters(update_filters(filters, "ai", ""))))
            
            s.respond('<p>Score: ')
            
            for i,(display,value) in enumerate([("0-4", "0"), ("5-9", "1"), ("10-14", "2"), ("15-19", "3"), ("20-24", "4"), ("25", "5")]):
                s.respond(' <a href="/selectreplay/%s">%s</a> - '%(format_filters(update_filters(filters, "score", value)), display))
            s.respond(' <a href="/selectreplay/%s">any</a></p>'%(format_filters(update_filters(filters, "score", ""))))
            
            s.respond('<p>Deck: ')
            
            for i,(display,value) in enumerate([("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("other", "other")]):
                s.respond(' <a href="/selectreplay/%s">%s</a> - '%(format_filters(update_filters(filters, "deck", value)), display))
            s.respond(' <a href="/selectreplay/%s">any</a></p>'%(format_filters(update_filters(filters, "deck", ""))))
            
            s.respond('Select a replay to view:<br/><ul>')
            replays = []
            
            def match(f, ai, deck, score):
                if "ai" in f and ai != f["ai"]:
                    return False
                if "score" in f and (score is None or score/5 != int(f["score"])):
                    return False
                if "deck" in f and ((str(deck) != f["deck"] and f["deck"] != "other") or (f["deck"] == "other" and deck <= 5)):
                    return False
                
                return True
            
            for f in os.listdir("log/"):
                if f.startswith("game"):
                    gid = f[4:20]
                    fname = os.path.join("log", f)
                    (ai,deck,score) = get_replay_info(fname)
                    if ai and deck and match(filters, ai, deck, score) and score is not None:
                        entry = '<li><a href="/replay/%s/1">Game %s (%s AI, %s, deck %d)</a></li>\n'%(gid, gid, ai, format_score(score), deck)
                        replays.append(((score if score else -1), entry))
            replays.sort(key=lambda s_e: -s_e[0])
            for (score,entry) in replays:
                s.respond(entry)
            return
        elif path.startswith("/takeover/"):
            items = [_f for _f in path.split("/") if _f]
            
            if len(items) < 5:
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game ID</h1>\n')
                s.respond("</body></html>")
                return
            gid,round,action,arg = items[1:]
            fname = "log/game%s.log"%gid
            try:
                round = int(round)
            except Exception:
                import traceback
                traceback.print_exc()
                round = None
            if "/" in gid or "\\" in gid or round is None or not os.path.exists(fname):
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game ID</h1>\n')
                s.respond("</body></html>")
                return
            (ai,deck,score) = get_replay_info(fname)
            s.respond("<html><head><title>Hanabi</title></head>\n")
            s.respond('<body><h1>Take over game</h1>\n')
            s.respond('<p>If you continue, you will take over playing the game you were viewing from turn %d onward</p>'%round)
            s.respond('<p>You may choose to use the same AI as the player that was playing the game by clicking <a href="/starttakeover/%s/%d/%s/%s/%s">here</a></p>\n'%(gid,round+1,ai,action,arg))
            s.respond('<p>You may also choose any AI to play with:</p><ul>')
            for a in agent.ids():
                s.respond('<li><a href="/starttakeover/%s/%d/%s/%s/%s">%s AI</a></li>'%(gid,round+1,a,action,arg,a.capitalize()))
                
            s.respond("</ul></p></body></html>")
            return
        
        if gid is None or game is None or path.startswith("/restart/"):
            if not debug:
                s.respond("<html><head><title>Hanabi</title></head>\n")
                s.respond('<body><h1>Invalid Game ID</h1>\n')
                s.respond("</body></html>")
                return
            if game is not None:
                del game
            gameslock.acquire()
            if gid is not None and gid in games:
                del games[gid]
            gameslock.release()
            # AIList
            # /new/<foo> will look up <foo> in the agent ids dictionary, so make sure the names match
            s.respond("<html><head><title>Hanabi</title></head>\n")
            s.respond('<body><h1>Welcome to Hanabi</h1> <p>To start, choose an AI:</p>\n')
            s.respond("<ul>\n")
            for id in agent.ids():
                s.respond('<li><a href="/new/%s">%s</a></li>\n'%(id,agent.get(id)[0]))
            s.respond('</ul><br/>')
            s.respond('<p>Or select a <a href="/selectreplay/">replay file to view</a></p>')
            s.respond('</body></html>')
            return
            
        if path.startswith("/explain") and debug:
            s.show_explanation(game)
            return 
            
        if path.startswith("/start/"):
            game.single_turn()
            game.started = True
            
        
        parts = path.strip("/").split("/")
        if parts[0] == str(turn):
            actionname = parts[1]
            index = int(parts[2])
            action = None
            if actionname == "hintcolor" and game.hints > 0:
                col = game.hands[0][index][0]
                action = hanabi.Action(hanabi.HINT_COLOR, player=0, color=col)
            elif actionname == "hintrank" and game.hints > 0:
                nr = game.hands[0][index][1]
                action = hanabi.Action(hanabi.HINT_RANK, player=0, rank=nr)
            elif actionname == "play":
                action = hanabi.Action(hanabi.PLAY, player=1, card_index=index)
            elif actionname == "discard":
                action = hanabi.Action(hanabi.DISCARD, player=1, card_index=index)
            
            if action:
                turn += 1
                gameslock.acquire()
                games[gid] = (game,player,turn)
                gameslock.release()
                game.external_turn(action)
                game.single_turn()
            
                
                
        
        s.respond("<html><head><title>Hanabi</title></head>")
        s.respond('<body>')
        
        s.respond(show_game_state(game, player, turn, gid, replay))
       
        s.respond("</body></html>")
        if game.done() and gid is not None and gid in games:
            errlog.write("%s game done. Score: %d\n"%(str(game.treatment), game.score()))
            errlog.flush()
            game.finish()
            del[gid]
        
    def show_explanation(s, game):
        s.respond("<html><head><title>Hanabi - AI Explanation</title></head>")
        s.respond('<body>')
        
        s.respond('<table border="1">')
        s.respond('<tr><th>Description</th><th>Card 1</th><th>Card 2</th><th>Card 3</th><th>Card 4</th><th>Card 5</th>\n')
        for line in game.players[0].get_explanation():
            s.respond('<tr>\n')
            for item in line:
                s.respond('\t<td>%s</td>\n'%(str(item).replace("\n", "<br/>")))
            s.respond('</tr>\n')
        s.respond("</table>\n")
       
        
        s.respond("</body></html>")
        
    def parse_POST(self):
        ctype, pdict = parse_header(self.headers['content-type'])
        if ctype == 'multipart/form-data':
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers['content-length'])
            postvars = parse_qs(
                    self.rfile.read(length), 
                    keep_blank_values=1)
        else:
            postvars = {}
        return postvars
        
    def getgid(s):
        peer = str(s.connection.getpeername()) + str(time.time()) + str(os.urandom(4))
        return hashlib.sha224(peer.encode("utf-8")).hexdigest()[:16]

 
class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    def finish_request(self, request, client_address):
        request.settimeout(30)
        # "super" can not be used because BaseServer is not created from object
        http.server.HTTPServer.finish_request(self, request, client_address) 
 
if __name__ == '__main__':
    server_class = ThreadingHTTPServer
    if not os.path.exists("log/"):
        os.makedirs("log")
    httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
    errlog.write(time.asctime() + " Server Starts - %s:%s\n" % (HOST_NAME, PORT_NUMBER))
    errlog.flush()
    try:
       httpd.serve_forever()
    except KeyboardInterrupt:
       pass
    httpd.server_close()
    errlog.write(time.asctime() +  " Server Stops - %s:%s\n" % (HOST_NAME, PORT_NUMBER))
    errlog.flush()