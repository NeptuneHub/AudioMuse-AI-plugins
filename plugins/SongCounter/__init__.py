import base64
import html
import io
import json

from flask import Blueprint, request, redirect

from plugin.api import get_db, get_setting, set_setting, table, render_page, manage_plugins_url

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
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(labels, values, color='#2563eb')
    ax.set_ylabel('songs')
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def migrate(db):
    cur = db.cursor()
    stats = table('hook_stats')
    cur.execute(
        "CREATE TABLE IF NOT EXISTS " + stats +
        " (id INTEGER PRIMARY KEY, run_id TEXT, analyzed_count INTEGER NOT NULL DEFAULT 0, last_song TEXT)"
    )
    cur.execute("ALTER TABLE " + stats + " ADD COLUMN IF NOT EXISTS run_id TEXT")
    db.commit()
    cur.close()


def _summarize(song):
    def shape(vector):
        if vector is None:
            return None
        try:
            return f'{len(vector)}-dim vector'
        except TypeError:
            return 'present'
    return {
        'item_id': song.get('item_id'),
        'run_id': song.get('run_id'),
        'audio_path': song.get('audio_path'),
        'metadata': song.get('metadata'),
        'analysis': song.get('analysis'),
        'top_moods': song.get('top_moods'),
        'musicnn_embedding': shape(song.get('musicnn_embedding')),
        'clap_embedding': shape(song.get('clap_embedding')),
    }


def on_analyzed(song):
    db = get_db()
    cur = db.cursor()
    stats = table('hook_stats')
    cur.execute(
        "INSERT INTO " + stats + " (id, run_id, analyzed_count, last_song) VALUES (1, %s, 1, %s) "
        "ON CONFLICT (id) DO UPDATE SET "
        "analyzed_count = CASE WHEN " + stats + ".run_id IS DISTINCT FROM EXCLUDED.run_id "
        "THEN 1 ELSE " + stats + ".analyzed_count + 1 END, "
        "run_id = EXCLUDED.run_id, last_song = EXCLUDED.last_song",
        (song.get('run_id'), json.dumps(_summarize(song))),
    )
    db.commit()
    cur.close()


def _hook_stats():
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("SELECT analyzed_count, last_song FROM " + table('hook_stats') + " WHERE id = 1")
        row = cur.fetchone()
        cur.close()
    except Exception:
        db.rollback()
        return 0, None
    if not row:
        return 0, None
    total, last_json = row
    return total, (json.loads(last_json) if last_json else None)


def _last_song_rows(last):
    rows = []
    for key, value in last.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                rows.append((f'{key}.{sub_key}', sub_value))
        else:
            rows.append((key, value))
    return rows


def _fmt_value(value):
    if isinstance(value, dict):
        return '\n'.join(
            f'{k}: {v:.4f}' if isinstance(v, float) else f'{k}: {v}'
            for k, v in value.items()
        )
    if isinstance(value, float):
        return f'{value:.4f}'
    return str(value)


def _hook_html():
    analyzed, last = _hook_stats()
    html_out = (
        '<h3 style="margin-top:1.5rem;">Live analysis (on_song_analyzed hook)</h3>'
        f'<p><strong>Songs analyzed in the latest run:</strong> {analyzed}</p>'
    )
    if not last:
        return html_out + '<p>No song analyzed yet. Start an analysis to watch this update.</p>'
    detail = ''.join(
        '<tr>'
        f'<td style="padding:.2rem .6rem;border-top:1px solid #ccc;vertical-align:top;"><strong>{html.escape(str(key))}</strong></td>'
        f'<td style="padding:.2rem .6rem;border-top:1px solid #ccc;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;">{html.escape(_fmt_value(value))}</td>'
        '</tr>'
        for key, value in _last_song_rows(last)
    )
    return html_out + (
        '<p style="margin-top:1rem;">Last analyzed song (everything the hook passed):</p>'
        '<table style="border-collapse:collapse;font-size:.95rem;width:100%;max-width:100%;table-layout:fixed;">'
        '<colgroup><col style="width:230px"><col></colgroup>'
        f'{detail}</table>'
    )


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
        f'{_hook_html()}'
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
    ctx.on_install(migrate)
    ctx.add_blueprint(bp)
    ctx.add_menu_item('SongCounter', 'song_counter.home')
    ctx.on_song_analyzed(on_analyzed)
