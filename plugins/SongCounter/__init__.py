from flask import Blueprint

from plugin.api import get_db

bp = Blueprint('song_counter', __name__)


@bp.route('/')
def home():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM score")
    count = cur.fetchone()[0]
    cur.close()
    return f"Your total analyzed songs are {count}"


def register(ctx):
    ctx.add_blueprint(bp)
    ctx.add_menu_item('SongCounter', 'song_counter.home')
