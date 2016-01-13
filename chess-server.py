"""Chess server.
Usage: chess-server.py [--debug] [--port PORT]

--port PORT  [default: 8080]
--debug
"""
from docopt import docopt
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

game_template = bottle.SimpleTemplate('''
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width">
        <link rel="stylesheet" type="text/css" href="/static/css/chessboard-0.3.0.min.css">
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.6/css/bootstrap.min.css" integrity="sha384-1q8mTJOASx8j1Au+a5WDVnPi2lkFfwwEAa8hDDdjZlpLegxhjVME1fgjWPGmkzs7" crossorigin="anonymous">
    </head>
    <body>
    <div class="container" style="max-width: 500px">
    <div id="board" style="width: 100%"></div>
    % if board.is_game_over():
    <p> Game over! Result: {{board.result()}} </p>
    % else:
        <p>
        % if board.turn:
        White's
        % else:
        Black's
        % end
        turn. Here are all legal moves. Click one.
        </p>
        <div class="list-group" style="text-align: center">
            % for (move, link) in moves:
            <a href="/game/{{link}}" class="list-group-item">{{move}}</a>
            % end
        </div>
    % end
    </div>
<script src="//cdnjs.cloudflare.com/ajax/libs/jquery/2.1.1/jquery.min.js"></script>
<script type="text/javascript" src="/static/js/chessboard-0.3.0.min.js"></script>
<script>
var cfg = {
    pieceTheme: '/static/img/chesspieces/wikipedia/{piece}.png',
    position: '{{board.fen()}}',
};
var board = ChessBoard('board', cfg); 
</script>
    </body>
</html>
''')


def move_generator(board):
    for move in sorted(board.legal_moves, key=lambda x: x.uci()):
        board.push(move)
        yield (move.uci(), urllib.quote(board.fen()))
        board.pop()


@app.route('/game')
@app.route('/game/')
@app.route('/game/<serial_game:path>')
def game(serial_game=None):
    if serial_game is None:
        board = chess.Board()
        bottle.response.set_header('Cache-Control', 'public, max-age=3600')
    else:
        board = chess.Board(serial_game)
    return game_template.render(board=board, moves=move_generator(board))

if __name__ == '__main__':
    arguments = docopt(__doc__)
    if arguments['--debug']:
        app.run(host='localhost', debug=True, reloader=True,
                port=int(arguments['--port']))
    else:
        from paste import httpserver
        httpserver.serve(app, host='0.0.0.0', port=int(arguments['--port']))
