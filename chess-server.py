"""Chess server.
Usage: chess-server.py [--debug] [--port PORT]

--port PORT  [default: 8080]
--debug
"""
import bottle
import chess
import urllib

app = bottle.Bottle()


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

def move_generator(board):
    moves = []
    for move in sorted(board.legal_moves, key=lambda x: x.uci()):
        board.push(move)
        moves.append((move.uci(), '/game/' + urllib.quote(board.fen())))
        board.pop()
    return moves


@app.route('/game')
@app.route('/game/')
@app.route('/game/<serial_game:path>')
@bottle.view('game.html')
def game(serial_game=None):
    if serial_game is None:
        board = chess.Board()
        bottle.response.set_header('Cache-Control', 'public, max-age=3600')
    else:
        board = chess.Board(serial_game)
    return dict(
        board=board,
        current_url=bottle.request.url,
        moves=move_generator(board),
    )

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__)
    if arguments['--debug']:
        app.run(host='localhost', debug=True, reloader=True,
                port=int(arguments['--port']))
    else:
        from paste import httpserver
        httpserver.serve(app, host='0.0.0.0', port=int(arguments['--port']))
