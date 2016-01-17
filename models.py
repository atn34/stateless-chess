from bottle.ext import sqlalchemy
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
import chess
import os

Base = declarative_base()

echo_db = False

engine = create_engine(os.environ.get('DATABASE_URL', 'sqlite:////tmp/chess.db'), echo=echo_db)

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
        self.moves = ""

    id = Column(Integer, primary_key=True)
    white = Column(String, index=True)
    black = Column(String, index=True)
    epd = Column(String)
    uuid = Column(String)
    active = Column(Boolean)
    move_count = Column(Integer)
    claim_draw = Column(Boolean)
    turn = Column(Boolean)
    moves = Column(String)

