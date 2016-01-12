"""Chess server.
Usage: chess-server.py [--debug] [--port PORT]

--port PORT  [default: 8080]
--debug
"""
from docopt import docopt
import bottle
import chess

app = bottle.Bottle()


class Game(object):

    def __init__(self, board=None):
        if board is None:
            board = chess.Board()
        self._board = board

    @staticmethod
    def loads(serialized):
        board = chess.Board()
        for move in serialized.split(','):
            board.push_uci(move)
        return Game(board)

    def dumps(self):
        return ','.join(move.uci() for move in self._board.move_stack)

    def board(self):
        return self._board


@app.route('/static/<path:path>')
def static(path):
    return bottle.static_file(path, root='static')


@app.route('/game')
@app.route('/game/')
@app.route('/game/<serial_game>')
def game(serial_game=None):
    if serial_game is None:
        game = Game()
        serial_game = ''
    else:
        game = Game.loads(serial_game)
        serial_game += ','
    if game.board().is_game_over():
        return game.board().result()
    return bottle.SimpleTemplate('''
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width">
        <link rel="stylesheet" type="text/css" href="/static/css/chessboard-0.3.0.min.css">
    </head>
    <body>
        <div id="board" style="width: 400px"></div>
        % if board.turn:
        <p> White's turn. </p>
        % else:
        <p> Black's turn. </p>
        % end
        <ul>
            % for move in board.legal_moves:
            <li><a href="/game/{{serial_game}}{{move}}">{{move}}</a></li>
            % end
        </ul>
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
''').render(
        board=game.board(),
        serial_game=serial_game,
    )

if __name__ == '__main__':
    arguments = docopt(__doc__)
    print arguments
    if arguments['--debug']:
        app.run(host='localhost', debug=True, reloader=True, port=int(arguments['--port']))
    else:
        from paste import httpserver
        httpserver.serve(app, host='0.0.0.0', port=int(arguments['--port']))
