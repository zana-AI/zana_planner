"""Local UI fixtures only: no .env, application imports, DB or upstream API calls.

Run this and `npm.cmd run dev -- --config vite.design.config.ts` in webapp_frontend.
The localhost-only Vite sandbox runs on :5174. Mutations below affect memory only.
"""
import copy
import json
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
SAVED = {}
CONTENT_UPDATES = {}
ROUTINES = {}
CONTROLS = r"""
const query = new URLSearchParams(location.search);
const previous = localStorage.getItem('telegram_auth_token') || '';
const mode = query.get('preview') || (previous.includes('returning') ? 'returning' : 'empty');
const lang = query.get('lang') === 'fa' ? 'fa' : query.get('lang') === 'en' ? 'en' : previous.endsWith('-fa') ? 'fa' : 'en';
localStorage.setItem('telegram_auth_token', 'design-' + (mode === 'returning' ? 'returning' : 'empty') + '-' + lang);
localStorage.removeItem('dev_init_data');
document.addEventListener('DOMContentLoaded', () => {
  if (query.has('frame')) return;
  const bar = document.createElement('aside');
  bar.setAttribute('aria-label', 'Design preview controls');
  bar.style.cssText = 'direction:ltr;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:8px 14px;background:#302344;color:#fff;font:12px system-ui;position:relative;z-index:100';
  const label = document.createElement('strong'); label.textContent = 'LOCAL DESIGN · sample data only'; bar.append(label);
  for (const [text, href] of [
    ['New user', '/dashboard?preview=empty&lang=' + lang],
    ['Returning learner', '/dashboard?preview=returning&lang=' + lang],
    ['English', location.pathname + '?preview=' + mode + '&lang=en'],
    ['فارسی', location.pathname + '?preview=' + mode + '&lang=fa'],
    ['Phone view', '/api/__preview/mobile?preview=' + mode + '&lang=' + lang],
  ]) { const a = document.createElement('a'); a.textContent = text; a.href = href; a.style.cssText='color:#b8efff;padding:6px'; bar.append(a); }
  document.body.prepend(bar);
});
"""


def catalog():
    raw = yaml.safe_load((ROOT / 'tm_bot/config/explore.yaml').read_text(encoding='utf-8'))
    raw['categories'] = [c for c in raw['categories'] if c.get('published', True)]
    for category in raw['categories']:
        category['topics'] = [t for t in category['topics'] if t.get('published', True)]
        for topic in category['topics']:
            topic['items'] = [i for i in topic['items'] if i.get('published', True)]
            for item in topic['items']:
                if item['type'] == 'video':
                    # Readiness is simulated ONLY in this isolated design server.
                    # Preserve verified catalog lengths instead of faking 13 minutes.
                    item.update(subtitles_available='cnn' not in item['id'], subtitle_language=category.get('language'))
                    item.setdefault('duration_seconds', 540)
    raw.update(metadata_available=True, clubs_available=True, clubs=[dict(club_id='design-french-club', name='French listening together', description='Sample club · practise listening and compare notes each week.', joined=False)])
    return raw


def sample_contents():
    items = [i for c in catalog()['categories'] for t in c['topics'] for i in t['items'] if i['type'] == 'video' and i.get('starter')]
    return [dict(id=i['id'], content_id=i['id'], user_content_id=i['id'], title=i['title'],
                 content_type='video', provider='youtube', author_channel=i.get('creator', 'Sample source'),
                 canonical_url='https://www.youtube.com/watch?v=' + i['native_ref'].split('video_id=')[1],
                 metadata_json={'video_id': i['native_ref'].split('video_id=')[1]},
                 thumbnail_url=i['image'], has_subtitles=True, duration_seconds=i['duration_seconds'],
                 status='in_progress' if n == 0 else 'completed' if n == 1 else 'saved', progress_ratio=0.35 if n == 0 else 1 if n == 1 else 0,
                 bucket_count=20, buckets=[1 if n == 1 else 0.6 if n == 0 and b < 7 else 0 for b in range(20)]) for n, i in enumerate(items)]


def library_items(token):
    items = {i['id']: i for i in copy.deepcopy(sample_contents() if 'returning' in token else [])}
    items.update(copy.deepcopy(SAVED.get(token, {})))
    for key, item in items.items():
        item.update(CONTENT_UPDATES.get(token, {}).get(key, {}))
    return list(items.values())


class Handler(BaseHTTPRequestHandler):
    def send(self, value, status=200, content_type='application/json'):
        body = (json.dumps(value, ensure_ascii=False) if content_type == 'application/json' else value).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        if path == '/api/__preview/controls.js':
            return self.send(CONTROLS, content_type='application/javascript')
        if path == '/api/__preview/mobile':
            mode = 'returning' if query.get('preview') == ['returning'] else 'empty'
            lang = 'fa' if query.get('lang') == ['fa'] else 'en'
            return self.send(f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Xaana phone preview</title></head>
                <body style="margin:0;background:#171923;color:white;font:14px system-ui;text-align:center">
                <p>LOCAL DESIGN · 390px phone · sample data · <a style="color:cyan" href="/dashboard?preview={mode}&lang={lang}">Desktop view</a></p>
                <iframe title="Xaana mobile preview" src="/dashboard?preview={mode}&lang={lang}&frame=1" style="display:block;margin:auto;border:1px solid #555;width:390px;max-width:100%;height:calc(100vh - 60px)"></iframe></body></html>''', content_type='text/html')
        if path == '/youtube-watch':
            return self.send('<h1>Design preview</h1><p>Playback and real subtitle fetching are not connected in this isolated UI sandbox.</p><a href="/explore">Back to Explore</a>', content_type='text/html')
        token = self.headers.get('Authorization', '')
        returning = 'returning' in token
        if path == '/api/user':
            return self.send(dict(user_id='900000002' if returning else '900000001', first_name='Returning learner' if returning else 'New learner', language='fa' if token.endswith('-fa') else 'en', timezone='Europe/Paris'))
        if path == '/api/admin/check':
            return self.send({'is_admin': False})
        if path == '/api/explore':
            return self.send(catalog())
        if path == '/api/weekly':
            today = date.fromisoformat(query.get('ref_time', [date.today().isoformat()])[0][:10])
            monday = today - timedelta(days=today.weekday())
            promises = {'P01': dict(text='Practise French listening', hours_promised=2, hours_spent=0.7, target_value=2, achieved_value=0.7, metric_type='hours', template_kind='commitment', recurring=True, visibility='private', sessions=[dict(date=monday.isoformat(), hours=0.7)])} if returning else {}
            promises.update(ROUTINES.get(token, {}))
            return self.send(dict(week_start=monday.isoformat(), week_end=(monday+timedelta(days=6)).isoformat(), total_promised=sum(p['hours_promised'] for p in promises.values()), total_spent=sum(p['hours_spent'] for p in promises.values()), promises=promises))
        if path == '/api/my-contents':
            items = library_items(token)
            if query.get('q'): items = [i for i in items if query['q'][0].lower() in i['title'].lower()]
            statuses = {value: sum(i['status'] == value for i in items) for value in ('saved', 'in_progress', 'completed', 'archived')}
            if not query.get('status') or query['status'][0] == 'all':
                items = [i for i in items if i['status'] != 'archived']
            for key in ('status', 'content_type'):
                if query.get(key) and query[key][0] != 'all': items = [i for i in items if i.get(key) == query[key][0]]
            return self.send(dict(items=items, total=len(items), next_cursor=None, facets={'status': statuses}))
        if path == '/api/flashcards/decks/tree':
            return self.send([dict(deck_id='design-deck', name='French vocabulary', parent_deck_id=None, total=12, due=3, new=2)] if returning else [])
        if path in ('/api/challenges', '/api/plan-sessions/upcoming', '/api/flashcards/summary', '/api/flashcards/decks'):
            return self.send([])
        if path == '/api/clubs':
            return self.send(dict(clubs=[], total=0))
        if path == '/api/focus/current':
            return self.send(None)
        return self.send({'detail': 'Not connected in the isolated design preview'}, 501)

    def do_POST(self):
        path = urlparse(self.path).path
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or '{}')
        token = self.headers.get('Authorization', '')
        if path == '/api/user/timezone':
            return self.send(dict(status='success', timezone=body.get('tz', 'UTC')))
        if path == '/api/promises':
            activity = str(body.get('text', '')).strip()
            try:
                hours = float(body.get('hours_per_week', 0))
            except (TypeError, ValueError):
                hours = 0
            if not activity or not 0 < hours <= 168:
                return self.send({'detail': 'Provide an activity and valid weekly hours'}, 422)
            routines = ROUTINES.setdefault(token, {})
            promise_id = f'P{len(routines) + 10}'
            routines[promise_id] = dict(text=activity, hours_promised=hours, hours_spent=0,
                target_value=hours, achieved_value=0, metric_type='hours', template_kind='commitment',
                recurring=True, visibility=body.get('visibility', 'private'), sessions=[], end_date=body.get('end_date'))
            return self.send(dict(status='success', promise_id=promise_id, message='Created in preview memory only'))
        if path == '/api/content/resolve':
            item = next((i for i in sample_contents() if i['canonical_url'] == body.get('url')), None)
            return self.send(item or {'detail': 'Only sample videos can be added in this design preview'}, 200 if item else 422)
        if path == '/api/user-content':
            item = next((i for i in sample_contents() if i['id'] == body.get('content_id')), None)
            if item:
                SAVED.setdefault(token, {})[item['id']] = dict(item, status='saved', progress_ratio=0, buckets=[])
                return self.send(dict(user_content_id=item['id'], status='saved'))
        return self.send({'detail': 'This action is not connected in the design preview. Production is untouched.'}, 501)

    def do_PATCH(self):
        path = urlparse(self.path).path
        token = self.headers.get('Authorization', '')
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or '{}')
        if path.startswith('/api/user-content/'):
            content_id = path.rsplit('/', 1)[1]
            if not any(i['id'] == content_id for i in library_items(token)):
                return self.send({'detail': 'Content not found'}, 404)
            if body.get('status') not in ('saved', 'in_progress', 'completed', 'archived'):
                return self.send({'detail': 'Invalid status'}, 422)
            CONTENT_UPDATES.setdefault(token, {})[content_id] = {'status': body['status']}
            return self.send({'content_id': content_id, 'updated': True})
        return self.send({'detail': 'Not connected in the design preview'}, 501)


if __name__ == '__main__':
    print('Isolated design fixture API: http://127.0.0.1:8088 (no DB or credentials)', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8088), Handler).serve_forever()
