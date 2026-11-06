#!/usr/bin/env python3
"""키르기스·타지키스탄 브리프: report.json 스키마 검증 + data/report.js(file:// 대체본) 생성.

사용법: python3 tools/build_report_js.py [--check PATH]
  인자 없음  data/report.json 검증 후 data/report.js 작성
  --check    지정 파일만 검증 (쓰기 없음)
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SECTION_IDS = ['korea', 'kg_tj', 'intl', 'neighbors', 'followup']
SECTION_TITLES = {
    'korea': '① 한국 관련 외교·인사',
    'kg_tj': '② 타지키스탄·키르기스스탄',
    'intl': '③ 국제경제·전쟁',
    'neighbors': '④ 인근국',
    'followup': '⑤ 오늘 확인할 것',
}


def require(cond, msg):
    if not cond:
        raise ValueError(msg)


def string(v, path, allow_empty=False):
    require(isinstance(v, str), f'{path}: 문자열이어야 합니다.')
    if not allow_empty:
        require(bool(v.strip()), f'{path}: 비어 있으면 안 됩니다.')


def url(v, path):
    if v in (None, ''):
        return
    string(v, path)
    p = urlparse(v)
    require(p.scheme in ('http', 'https') and bool(p.netloc), f'{path}: http(s) URL이어야 합니다.')
    require('utm_source=' not in v, f'{path}: utm_source 파라미터를 제거해야 합니다.')


def bullet(b, path):
    require(isinstance(b, dict), f'{path}: 객체여야 합니다.')
    string(b.get('text'), path + '.text')
    if b.get('url'):
        url(b['url'], path + '.url')
        string(b.get('source'), path + '.source (url이 있으면 매체명 필수)')
    elif 'source' in b:
        string(b['source'], path + '.source', allow_empty=True)
    url(b.get('altUrl'), path + '.altUrl')
    if b.get('altUrl'):
        require(bool(b.get('url')), f'{path}: altUrl은 url과 함께만 사용합니다.')
    if b.get('publishedAt'):
        try:
            datetime.fromisoformat(b['publishedAt'].replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f'{path}.publishedAt: ISO 8601 형식이어야 합니다.') from None


def item(it, path, section_id):
    require(isinstance(it, dict), f'{path}: 객체여야 합니다.')
    string(it.get('tag', ''), path + '.tag', allow_empty=True)
    string(it.get('title', ''), path + '.title', allow_empty=(section_id == 'followup'))
    cs = it.get('countries', [])
    require(isinstance(cs, list) and all(isinstance(c, str) and c.strip() for c in cs), f'{path}.countries: 문자열 배열이어야 합니다.')
    bs = it.get('bullets')
    require(isinstance(bs, list) and bs, f'{path}.bullets: 1개 이상 필요합니다.')
    for i, b in enumerate(bs):
        bullet(b, f'{path}.bullets[{i}]')
    if section_id != 'followup':
        require(any(b.get('url') for b in bs), f'{path}: 출처 URL이 있는 bullet이 1개 이상 필요합니다(날조 금지·출처 필수).')


def validate(r):
    require(isinstance(r, dict), 'report: 객체여야 합니다.')
    string(r.get('date'), 'date')
    try:
        require(date.fromisoformat(r['date']).isoformat() == r['date'], 'date: YYYY-MM-DD')
    except ValueError:
        raise ValueError('date: 유효한 YYYY-MM-DD 날짜여야 합니다.') from None
    string(r.get('generatedAt'), 'generatedAt')
    try:
        datetime.fromisoformat(r['generatedAt'].replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('generatedAt: ISO 8601 형식이어야 합니다.') from None
    string(r.get('coverage'), 'coverage')
    string(r.get('headline'), 'headline')
    secs = r.get('sections')
    require(isinstance(secs, list) and len(secs) == 5, 'sections: 정확히 5개여야 합니다.')
    require([s.get('id') for s in secs] == SECTION_IDS, f'sections: id 순서는 {SECTION_IDS} 이어야 합니다.')
    for i, s in enumerate(secs):
        string(s.get('title'), f'sections[{i}].title')
        require(isinstance(s.get('items'), list), f'sections[{i}].items: 배열이어야 합니다.')
        for j, it in enumerate(s['items']):
            item(it, f'sections[{i}].items[{j}]', s['id'])
    require(sum(len(s['items']) for s in secs[:4]) >= 1, 'sections: ①~④에 항목이 1개 이상 필요합니다.')
    notes = r.get('notes', [])
    require(isinstance(notes, list) and all(isinstance(n, str) for n in notes), 'notes: 문자열 배열이어야 합니다.')
    return r


def js_literal(value):
    return json.dumps(value, ensure_ascii=False, indent=2).replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def main(argv):
    try:
        if argv[:1] == ['--check']:
            validate(json.loads(Path(argv[1]).read_text(encoding='utf-8')))
            print('검증 통과:', argv[1])
            return 0
        r = validate(json.loads((ROOT / 'data/report.json').read_text(encoding='utf-8')))
        (ROOT / 'data/report.js').write_text('window.REPORT_DATA = ' + js_literal(r) + ';\n', encoding='utf-8')
        print('data/report.js 작성:', r['date'])
        return 0
    except (OSError, ValueError, KeyError, IndexError) as e:
        print('검증 실패:', e, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
