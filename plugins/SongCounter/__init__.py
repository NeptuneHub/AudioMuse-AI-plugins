import base64
import io

from flask import Blueprint, request, redirect

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from plugin.api import get_db, get_setting, set_setting, render_page, manage_plugins_url

bp = Blueprint('song_counter', __name__)

SOURCES = [
    ('musicnn', 'Musicnn', 'embedding'),
    ('dclap', 'DCLAP', 'clap_embedding'),
    ('gte', 'GTE lyrics', 'lyrics_embedding'),
]


def _count(table_name):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM " + table_name)
    total = cur.fetchone()[0]
    cur.close()
    return total


def _bar_chart(labels, values):
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(labels, values, color='#2563eb')
    ax.set_ylabel('songs')
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode('ascii')


@bp.route('/')
def home():
    selected = get_setting('sources', [])
    rows = []
    if selected:
        for key, label, table_name in SOURCES:
            if key in selected:
                rows.append((label, _count(table_name)))
    else:
        rows.append(('Total analyzed songs', _count('score')))
    chart = _bar_chart([r[0] for r in rows], [r[1] for r in rows])
    items = ''.join(
        f'<li style="margin:.3rem 0;"><strong>{label}:</strong> {count}</li>'
        for label, count in rows
    )
    body = (
        f'<img src="data:image/png;base64,{chart}" alt="Song counts" style="max-width:100%;height:auto;">'
        f'<ul style="list-style:none;padding:0;font-size:1.1rem;margin-top:1rem;">{items}</ul>'
    )
    return render_page(body, title='SongCounter')


@bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        chosen = [key for key, _label, _table in SOURCES if request.form.get(key)]
        set_setting('sources', chosen)
        return redirect(manage_plugins_url())
    selected = get_setting('sources', [])
    checks = ''
    for key, label, _table in SOURCES:
        checked = 'checked' if key in selected else ''
        checks += (
            f'<label style="display:block;margin:.5rem 0;">'
            f'<input type="checkbox" name="{key}" {checked}> {label}</label>'
        )
    body = (
        '<form method="post">'
        '<p>Select which embeddings to count (choose one, more, or none):</p>'
        f'{checks}'
        '<button type="submit" class="btn btn-primary" style="margin-top:1rem;">Save</button>'
        '</form>'
    )
    return render_page(body, title='SongCounter Settings')


def register(ctx):
    ctx.add_blueprint(bp)
    ctx.add_menu_item('SongCounter', 'song_counter.home')
