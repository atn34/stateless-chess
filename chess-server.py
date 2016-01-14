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


@app.route('/')
def index():
    return '''
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width">
    </head>
    <body>
        Welcome to the stateless chess server! Start a game
        <a href="/game">here</a>, and mail the links back and forth to a friend
        to play chess by email!
    </body>
</html>
'''


def trusted_digest(*args):
    h = hmac.new(secret)
    for arg in args:
        h.update(str(arg))
    return h.hexdigest()


def move_generator(board, game_uuid):
    moves = []
    for move in sorted(board.legal_moves, key=lambda x: x.uci()):
        board.push(move)
        serial_game = board.fen()
        moves.append((move.uci(), '/' + '/'.join([
            'game',
            game_uuid,
            trusted_digest(
                game_uuid,
                serial_game),
            urllib.quote(serial_game)])))
        board.pop()
    return moves


@app.route('/game')
@app.route('/game/')
@app.route('/game/<game_uuid>/<digest>/<serial_game:path>')
@bottle.view('game.html')
def game(game_uuid=None, digest=None, serial_game=None):
    if serial_game is None:
        board = chess.Board()
        game_uuid = binascii.hexlify(os.urandom(UUID_LENGTH))
        bottle.response.set_header('Cache-Control', 'public, max-age=3600')
    else:
        if not hmac.compare_digest(trusted_digest(game_uuid, serial_game), digest):
            raise bottle.HTTPError(404, "Tampered link")
        board = chess.Board(serial_game)
    return dict(
        board=board,
        current_url=bottle.request.url,
        moves=move_generator(board, game_uuid),
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
