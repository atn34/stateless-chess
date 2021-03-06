"""Chess server.
Usage: chess-server.py [--port PORT] [--secret SECRET]

--port PORT      [default: 8080]
--secret SECRET  [default: secret]
"""

from rq import Queue
from sqlalchemy import and_
from sqlalchemy import desc
from sqlalchemy import or_
import bottle
import chess
import hashlib
import hmac
import sendemail
import urllib
import uuid

import models

app = bottle.Bottle()
sql_plugin = models.sql_plugin
Game = models.Game

app.install(sql_plugin)

secret = 'secret'

q = Queue(connection=sendemail.conn)


def compressed_available(path):
    """Keep up to date with bin/pre_compile"""
    return not path.startswith('img')


def make_url_path(*args):
    return '/' + '/'.join(map(urllib.quote, args))


def mint_game_url(game):
    scheme, host = bottle.request.urlparts[:2]
    return scheme + '://' + host + make_url_path(
        'game',
        str(game.id))


@app.route('/favicon.ico', skip=[sql_plugin])
def favicon():
    return static('favicon.ico')


@app.route('/static/<path:path>', skip=[sql_plugin])
def static(path):
    gzip_available = compressed_available(path)
    if gzip_available and 'gzip' in bottle.request.headers.get('Accept-Encoding', ''):
        path += '.gz'
    response = bottle.static_file(path, root='static')
    response.set_header('Cache-Control', 'public, max-age=3600')
    if gzip_available:
        response.set_header('Vary', 'Accept-Encoding')
        if path.endswith('.gz'):
            response.set_header('Content-Encoding', 'gzip')
    return response


def trusted_digest(*args):
    h = hmac.new(secret)
    for arg in args:
        h.update(str(arg))
    return h.hexdigest()


@app.route('/')
@bottle.view('index.html')
def index(db):
    recent_games = db.query(Game).order_by(desc(Game.id)).limit(20)
    return dict(recent_games=recent_games)


@app.post('/dashboard')
def dashboard(db):
    email = bottle.request.forms.get('email')
    bottle.redirect(make_url_path('dashboard', email))


@app.route('/dashboard/<email>')
@bottle.view('dashboard.html')
def dashboard(db, email):
    games = db.query(Game).filter(Game.active == True,
                                  or_(and_(Game.white == email, Game.turn == True),
                                      and_(Game.black == email, Game.turn == False))).all()
    opponent_games = db.query(Game).filter(Game.active == True,
                                           or_(and_(Game.white == email, Game.turn == False),
                                               and_(Game.black == email, Game.turn == True))).all()
    return dict(
        email=email,
        games=games,
        opponent_games=opponent_games,
    )


def mail_token(game, side, first=False):
    start_url = mint_game_url(game)
    if not game.active:
        message = "Game Over"
    elif first:
        message = "You're in a game of stateless chess!"
    else:
        message = "It's your turn!"
    if side == 'white':
        q.enqueue(sendemail.send_from_statelesschess, game.white,
                  message,
                  bottle.template('email.txt', dict(opponent=game.black,
                                                    first=first,
                                                    start_url=start_url,
                                                    side='white',
                                                    token=trusted_digest(game.uuid, 'white'))))
    elif side == 'black':
        q.enqueue(sendemail.send_from_statelesschess, game.black,
                  message,
                  bottle.template('email.txt', dict(opponent=game.white,
                                                    first=first,
                                                    start_url=start_url,
                                                    side='black',
                                                    token=trusted_digest(game.uuid, 'black'))))
    else:
        raise ValueError("Expected side to be either 'black' or 'white'")


@app.post('/mail-token/<side>/<game_id:int>')
def mail_tokens_handler(db, side, game_id):
    game = db.query(Game).get(game_id)
    mail_token(game, side)


@app.post('/start')
def start(db):
    white = bottle.request.forms.get('white')
    black = bottle.request.forms.get('black')
    game = Game(white, black)
    db.add(game)
    db.flush()
    db.refresh(game)
    mail_token(game, 'white', first=True)
    bottle.redirect('/static/html/sent.html')


def move_generator(game):
    moves = []
    board = chess.Board()
    board.set_epd(game.epd)
    for move in sorted(board.legal_moves, key=lambda x: x.uci()):
        moves.append((move.uci(), make_url_path(
            'move',
            str(game.id),
            'uci',
            move.uci())))
    return moves


@app.post('/move/<game_id:int>/uci/<move>')
@app.post('/move/<game_id:int>/draw')
def move(db, game_id, move=None):
    game = db.query(Game).get(game_id)
    if game is None:
        raise bottle.HTTPError(404)
    if not game.active:
        raise bottle.HTTPError(403, "Game is over")
    board = chess.Board()
    board.set_epd(game.epd)
    side = 'white' if board.turn else 'black'
    try:
        token = bottle.request.json['token'].encode('utf8')
        if not hmac.compare_digest(trusted_digest(game.uuid, side), token):
            raise bottle.HTTPError(403, "Bad token provided")
    except KeyError:
        raise bottle.HTTPError(403, "No token provided")
    if move is not None:
        move = chess.Move.from_uci(move)
        if move not in board.legal_moves:
            raise bottle.HTTPError(404)
        board.push(move)
        if game.moves:
            game.moves += "," + move.uci()
        else:
            game.moves = move.uci()
    else:
        if board.can_claim_draw():
            game.claim_draw = True
    new_url = mint_game_url(game)
    game.move_count += 1
    game.epd = board.epd(hmvc=board.halfmove_clock, fmvc=board.fullmove_number)
    if board.is_game_over(claim_draw=game.claim_draw):
        game.active = False
    game.turn = board.turn
    db.add(game)
    db.flush()
    if game.move_count == 1:
        mail_token(game, 'black', first=True)
    return dict(new_url=new_url)


@app.route('/game/<game_id:int>')
@bottle.view('game.html')
def game(db, game_id):
    game = db.query(Game).get(game_id)
    if game is None:
        raise bottle.HTTPError(404)
    board = chess.Board()
    board.set_epd(game.epd)
    current_url = bottle.request.url
    q_index = current_url.find('?')
    if q_index >= 0:
        current_url = current_url[:q_index]
    return dict(
        board=board,
        current_url=current_url,
        game=game,
        moves=move_generator(game),
        draw_link=make_url_path('move', str(game.id), 'draw'),
        white=game.white,
        black=game.black,
        token_name=game.uuid + ('white' if board.turn else 'black'),
        token_value=bottle.request.query.get('token'),
    )

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__)
    secret = arguments['--secret']
    port = int(arguments['--port'])
    from gevent.pywsgi import WSGIServer
    from geventwebsocket.handler import WebSocketHandler
    from geventwebsocket import WebSocketError
    server = WSGIServer(("0.0.0.0", port), app,
                        handler_class=WebSocketHandler)
    server.serve_forever()
