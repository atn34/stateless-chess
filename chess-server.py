"""Chess server.
Usage: chess-server.py [--debug] [--port PORT] [--secret SECRET]

--port PORT      [default: 8080]
--debug
--secret SECRET  [default: secret]
"""
import bottle
import chess
import hashlib
import hmac
import sendemail
import urllib
import uuid

app = bottle.Bottle()

secret = 'secret'


def compressed_available(path):
    """Keep up to date with bin/pre_compile"""
    return not path.startswith('img')


@app.route('/favicon.ico')
def favicon():
    return static('favicon.ico')


@app.route('/static/<path:path>')
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
def index():
    return {}


def make_url_path(*args):
    return '/' + '/'.join(map(urllib.quote, args))


def mint_game_url(board, game_uuid, move_count, white, black):
    scheme, host = bottle.request.urlparts[:2]
    serial_game = board.fen()
    return scheme + '://' + host + make_url_path(
        'game',
        game_uuid,
        move_count,
        white,
        black,
        trusted_digest(
            game_uuid,
            move_count,
            serial_game,
            white,
            black),
        serial_game)


@app.post('/start')
def start():
    white = bottle.request.forms.get('white')
    black = bottle.request.forms.get('black')
    game_uuid = str(uuid.uuid4())
    board = chess.Board()
    start_url = mint_game_url(board, game_uuid, '0', white, black)
    sendemail.send_from_statelesschess(white,
                                       "You're in a game of stateless chess!",
                                       bottle.template('email.txt', dict(opponent=black,
                                                                         start_url=start_url,
                                                                         side='white',
                                                                         token=trusted_digest(game_uuid, 'white'))))
    bottle.redirect('/static/html/sent.html')


def move_generator(board, game_uuid, move_count, white, black):
    moves = []
    serial_game = board.fen()
    for move in sorted(board.legal_moves, key=lambda x: x.uci()):
        moves.append((move.uci(), make_url_path(
            'move',
            game_uuid,
            str(move_count),
            white,
            black,
            trusted_digest(
                game_uuid,
                move_count,
                serial_game,
                white,
                black,
                move.uci()
            ),
            move.uci(),
            serial_game)))
    return moves


@app.post('/move/<game_uuid>/<move_count:int>/<white>/<black>/<digest>/<move>/<serial_game:path>')
def move(game_uuid, move_count, white, black, digest, move, serial_game):
    if not hmac.compare_digest(trusted_digest(
            game_uuid,
            move_count,
            serial_game,
            white,
            black,
            move), digest):
        raise bottle.HTTPError(404, "Tampered link")
    board = chess.Board(serial_game)
    side = 'white' if board.turn else 'black'
    try:
        token = bottle.request.json['token'].encode('utf8')
        if not hmac.compare_digest(trusted_digest(game_uuid, side), token):
            raise bottle.HTTPError(403, "Bad token provided")
    except KeyError:
        raise bottle.HTTPError(403, "No token provided")
    move = chess.Move.from_uci(move)
    board.push(move)
    new_url = mint_game_url(
        board, game_uuid, str(move_count + 1), white, black)
    if move_count == 0:
        sendemail.send_from_statelesschess(black,
                                           "You're in a game of stateless chess!",
                                           bottle.template('email.txt', dict(opponent=white,
                                                                             side='black',
                                                                             start_url=new_url,
                                                                             token=trusted_digest(game_uuid, 'black'))))
    return dict(new_url=new_url)


@app.route('/game/<game_uuid>/<move_count:int>/<white>/<black>/<digest>/<serial_game:path>')
@bottle.view('game.html')
def game(game_uuid, move_count, white, black, digest, serial_game):
    if not hmac.compare_digest(trusted_digest(game_uuid, move_count, serial_game, white, black), digest):
        raise bottle.HTTPError(404, "Tampered link")
    board = chess.Board(serial_game)
    return dict(
        board=board,
        current_url=bottle.request.url,
        moves=move_generator(board, game_uuid, move_count, white, black),
        white=white,
        black=black,
        move_count=move_count,
        token_name=game_uuid + ('white' if board.turn else 'black'),
        token_value=bottle.request.query.get('token'),
    )

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__)
    secret = arguments['--secret']
    if arguments['--debug']:
        app.run(host='localhost', debug=True, reloader=True,
                port=int(arguments['--port']))
    else:
        from paste import httpserver
        httpserver.serve(app, host='0.0.0.0', port=int(arguments['--port']))
