from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(conexion, _):
    # SQLite no hace cumplir las claves foráneas por defecto
    if conexion.__class__.__module__.startswith("sqlite3"):
        cur = conexion.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
