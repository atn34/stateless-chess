"""Chess server.
Usage: chess-server.py [--debug] [--port PORT] [--secret SECRET]

--port PORT      [default: 8080]
--debug
--secret SECRET  [default: secret]
"""

from bottle.ext import sqlalchemy
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import and_
from sqlalchemy import create_engine
from sqlalchemy import or_
from sqlalchemy.ext.declarative import declarative_base
import bottle
import chess
import hashlib
import hmac
import os
import sendemail
import urllib
import uuid

Base = declarative_base()

echo_db = False

engine = create_engine(os.environ.get('DATABASE_URL', 'sqlite:////tmp/chess.db'), echo=echo_db)

app = bottle.Bottle()
sql_plugin = sqlalchemy.Plugin(
    engine,  # SQLAlchemy engine created with create_engine function.
    Base.metadata,  # SQLAlchemy metadata, required only if create=True.
    # Keyword used to inject session database in a app.route (default 'db').
    keyword='db',
    # If it is true, execute `metadata.create_all(engine)` when plugin is
    # applied (default False).
    create=True,
    # If it is true, plugin commit changes after app.route is executed (default
    # True).
    commit=True,
    # If it is true and keyword is not defined, plugin uses **kwargs argument
    # to inject session database (default False).
    use_kwargs=True,
)

app.install(sql_plugin)

secret = 'secret'

class Game(Base):
    __tablename__ = 'games'

    def __init__(self, white, black):
        self.white = white
        self.black = black
        board = chess.Board()
        self.epd = board.epd()
        self.active = True
        self.uuid = str(uuid.uuid4())
        self.move_count = 0
        self.claim_draw = False
        self.turn = True

    id = Column(Integer, primary_key=True)
    white = Column(String, index=True)
    black = Column(String, index=True)
    epd = Column(String)
    uuid = Column(String)
    active = Column(Boolean)
    move_count = Column(Integer)
    claim_draw = Column(Boolean)
    turn = Column(Boolean)


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
    return {}


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


@app.post('/start')
def start(db):
    white = bottle.request.forms.get('white')
    black = bottle.request.forms.get('black')
    game = Game(white, black)
    db.add(game)
    db.flush()
    db.refresh(game)
    start_url = mint_game_url(game)
    sendemail.send_from_statelesschess(white,
                                       "You're in a game of stateless chess!",
                                       bottle.template('email.txt', dict(opponent=black,
                                                                         start_url=start_url,
                                                                         side='white',
                                                                         token=trusted_digest(game.uuid, 'white'))))
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
        sendemail.send_from_statelesschess(game.black,
                                           "You're in a game of stateless chess!",
                                           bottle.template('email.txt', dict(opponent=game.white,
                                                                             side='black',
                                                                             start_url=new_url,
                                                                             token=trusted_digest(game.uuid, 'black'))))
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
    if arguments['--debug']:
        echo_db = True
        app.run(host='localhost', debug=True, reloader=True,
                port=int(arguments['--port']))
    else:
        from paste import httpserver
        httpserver.serve(app, host='0.0.0.0', port=int(arguments['--port']))
