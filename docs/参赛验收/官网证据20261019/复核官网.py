"""Fetch only public official pages; preserve exact response bytes and failures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
OLD = ROOT / '.verification/competition_20261018/official'
TZ = timezone(timedelta(hours=8))
URLS = {f'article-{i}': f'https://www.siac.net.cn/api/cms/articles/{i}' for i in (2, 23, 26, 27, 28)}
URLS.update(announcements='https://www.siac.net.cn/api/cms/articles?categoryId=2&page=1&pageSize=100',
            news='https://www.siac.net.cn/api/cms/articles?categoryId=1&page=1&pageSize=100',
            categories='https://www.siac.net.cn/api/cms/categories',
            homepage='https://www.siac.net.cn/',
            guide_display='https://www.siac.net.cn/article/2')


def semantic(key, obj):
    data = obj.get('data')
    if key.startswith('article-'):
        return {k: data.get(k) for k in ('id', 'title', 'summary', 'content', 'publishedAt', 'category')} | {
            'attachment_metadata': [{k: a.get(k) for k in ('name', 'size', 'mimetype', 'objectName')} for a in data.get('attachments', [])]}
    if key in ('announcements', 'news') or key.startswith(('announcements-page-', 'news-page-')):
        return {'articles': [{k: a.get(k) for k in ('id', 'title', 'summary', 'publishedAt', 'category')} for a in data], 'meta': obj.get('meta')}
    if key == 'categories':
        return [{k: a.get(k) for k in ('id', 'name', 'code', 'schedule', 'articleCount')} for a in data]
    return None


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def fetch(item):
    key, url = item
    entry = {'key': key, 'url': url, 'started_at_beijing': datetime.now(TZ).isoformat(),
             'method': 'GET', 'authentication': 'none', 'requested_cache_control': 'no-cache'}
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (public competition notice verification)', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            entry.update(http_status=response.status, final_url=response.geturl(), headers=dict(response.headers.items()))
        (OUT / f'{key}.response.bin').write_bytes(raw)
        entry.update(success=True, bytes=len(raw), raw_sha256=sha256(raw).hexdigest(), raw_file=f'{key}.response.bin')
        decoded = raw.decode('utf-8-sig', errors='replace')
        try:
            obj = json.loads(decoded)
        except json.JSONDecodeError:
            (OUT / f'{key}.html').write_text(decoded, encoding='utf-8')
            entry['decoded_file'] = f'{key}.html'
        else:
            entry['api_success'] = obj.get('success')
            (OUT / f'{key}.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            entry['decoded_file'] = f'{key}.json'
            data = obj.get('data')
            if key.startswith('article-') and isinstance(data, dict):
                body = unescape(re.sub(r'<[^>]*>', '\n', data.get('content') or ''))
                body = re.sub(r'\n[ \t]*\n+', '\n', body).strip()
                (OUT / f'{key}.txt').write_text(body + '\n', encoding='utf-8')
                entry['body_text_sha256'] = sha256((body + '\n').encode('utf-8')).hexdigest()
                entry['title'] = data.get('title')
            sem = semantic(key, obj)
            if sem is not None:
                blob = canonical(sem)
                (OUT / f'{key}.semantic.json').write_bytes(blob)
                entry['semantic_sha256'] = sha256(blob).hexdigest()
                old_path = OLD / f'{key}.json'
                if old_path.is_file():
                    previous = semantic(key, json.loads(old_path.read_text(encoding='utf-8-sig')))
                    entry.update(compared_with=str(old_path.relative_to(ROOT)).replace('\\', '/'),
                                 semantic_equal_to_20261018=sem == previous,
                                 old_semantic_sha256=sha256(canonical(previous)).hexdigest())
    except Exception as error:
        entry.update(success=False, error_type=type(error).__name__, error=str(error))
        if isinstance(error, urllib.error.HTTPError):
            entry['http_status'] = error.code
    entry['finished_at_beijing'] = datetime.now(TZ).isoformat()
    return entry


def main():
    if (OUT / 'fetch_log.json').exists():
        raise RuntimeError('Existing fetch evidence is preserved; use a fresh directory for another check.')
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(fetch, URLS.items()))
    extra = {}
    for key, category in (('announcements', 2), ('news', 1)):
        path = OUT / f'{key}.json'
        if path.is_file():
            obj = json.loads(path.read_text(encoding='utf-8'))
            pages = obj.get('meta', {}).get('totalPages', 1)
            for page in range(2, min(pages, 20) + 1):
                extra[f'{key}-page-{page}'] = f'https://www.siac.net.cn/api/cms/articles?categoryId={category}&page={page}&pageSize=100'
            for article in obj.get('data', []):
                ident = article['id']
                if f'article-{ident}' not in URLS:
                    extra[f'article-{ident}'] = f'https://www.siac.net.cn/api/cms/articles/{ident}'
    if extra:
        with ThreadPoolExecutor(max_workers=6) as pool:
            records.extend(pool.map(fetch, extra.items()))
    report = {'started_at_beijing': min(x['started_at_beijing'] for x in records),
              'finished_at_beijing': datetime.now(TZ).isoformat(),
              'read_only_public_http': True, 'no_login_or_submission': True,
              'semantic_comparison_rule': 'Article identity/title/summary/content/publication/category plus attachment name/size/type/objectName; exclude viewCount and expiring attachment URLs. Lists compare identity/title/summary/publication/category and pagination. Categories compare identity/name/code/schedule/articleCount.',
              'requests': records}
    (OUT / 'fetch_log.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'started_at_beijing': report['started_at_beijing'], 'finished_at_beijing': report['finished_at_beijing'],
                      'requests': [{k: v for k, v in x.items() if k in ('key', 'url', 'success', 'http_status', 'title', 'semantic_equal_to_20261018', 'raw_sha256', 'semantic_sha256', 'error_type', 'error')} for x in records]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
