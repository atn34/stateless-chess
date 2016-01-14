"""Chess server.
Usage: chess-server.py [--debug] [--port PORT] [--secret SECRET]

--port PORT      [default: 8080]
--debug
--secret SECRET  [default: secret]
"""
import binascii
import bottle
import chess
import hashlib
import hmac
import os
import urllib

app = bottle.Bottle()

secret = 'secret'

UUID_LENGTH = 16


def compressed_available(path):
    """Keep up to date with bin/pre_compile"""
    return not path.startswith('img')


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


def mint_game_url(board, game_uuid, move_count, white, black):
    serial_game = board.fen()
    return '/' + '/'.join(map(urllib.quote, [
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
        serial_game]))


@app.post('/start')
def start():
    white = bottle.request.forms.get('white') or 'white'
    black = bottle.request.forms.get('black') or 'black'
    game_uuid = binascii.hexlify(os.urandom(UUID_LENGTH))
    board = chess.Board()
    bottle.redirect(mint_game_url(board, game_uuid, '0', white, black))


def move_generator(board, game_uuid, move_count, white, black):
    moves = []
    for move in sorted(board.legal_moves, key=lambda x: x.uci()):
        board.push(move)
        serial_game = board.fen()
        moves.append((move.uci(), mint_game_url(board,
            game_uuid,
            str(move_count + 1),
            white,
            black)))
        board.pop()
    return moves


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
