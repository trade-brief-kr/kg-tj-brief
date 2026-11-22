#!/usr/bin/env python3
"""data/report.json 검증 후 게시(최신본 + 보관본 + 색인 + RSS)를 한 번에 처리.

사용법: python3 tools/publish_daily.py [--allow-any-date]
1. data/report.json 검증 (build_report_js.validate와 동일 규칙)
2. date == 오늘(KST) 확인 (--allow-any-date로 생략)
3. data/archive/<date>.json/.js 작성(같은 날짜 재실행 시 덮어씀)
4. data/archive/index.json/.js 재생성(최신순), data/report.js 재생성, feed.xml(RSS) 재생성
오류 시 아무것도 바꾸지 않음(임시 파일에 쓴 뒤 모두 성공하면 교체). 실패 시 종료 코드 1.
"""
import json
import sys
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common.brief_common import KST, Stager, js_literal, today_kst  # noqa: E402
from build_report_js import ROOT, validate  # noqa: E402

DATA = ROOT / 'data'
ARCHIVE = DATA / 'archive'
SITE = 'https://trade-brief-kr.github.io/kg-tj-brief/'
FEED_ITEMS = 30


def index_entry(r):
    titles = [f"{it.get('tag', '')} {it.get('title', '')}".strip() for s in r['sections'] for it in s['items'] if it.get('title')]
    return {'date': r['date'], 'headline': r['headline'], 'generatedAt': r['generatedAt'],
            'itemCount': sum(len(s['items']) for s in r['sections'][:4]), 'titles': titles}


def feed(index):
    items = []
    for e in index[:FEED_ITEMS]:
        pub = datetime.fromisoformat(e['generatedAt'].replace('Z', '+00:00'))
        desc = '\n'.join(e['titles'])
        items.append(
            f"<item><title>{escape(e['date'] + ' · ' + e['headline'])}</title>"
            f"<link>{SITE}?date={e['date']}</link><guid isPermaLink=\"false\">kg-tj-brief-{e['date']}</guid>"
            f"<pubDate>{format_datetime(pub)}</pubDate><description>{escape(desc)}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            '<title>키르기스·타지키스탄 브리프</title>'
            f'<link>{SITE}</link><description>키르기스스탄·타지키스탄 일일 5분 통상 브리핑</description><language>ko</language>'
            + ''.join(items) + '</channel></rss>\n')


def main(argv):
    allow_any = '--allow-any-date' in argv
    stager = Stager()
    try:
        r = validate(json.loads((DATA / 'report.json').read_text(encoding='utf-8')))
        today = today_kst().isoformat()
        if not allow_any and r['date'] != today:
            raise ValueError(f"date: 오늘(KST {today})이 아님: {r['date']} (--allow-any-date로 무시 가능)")
        d = r['date']
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        entries = {d: index_entry(r)}
        for p in sorted(ARCHIVE.glob('????-??-??.json')):
            if p.stem == d:
                continue
            old = validate(json.loads(p.read_text(encoding='utf-8')))
            if old['date'] != p.stem:
                raise ValueError(f'{p.name}: 파일명과 date({old["date"]})가 다름')
            entries[old['date']] = index_entry(old)
        index = sorted(entries.values(), key=lambda e: e['date'], reverse=True)

        body = js_literal(r)
        stager.stage(ARCHIVE / f'{d}.json', json.dumps(r, ensure_ascii=False, indent=2) + '\n')
        stager.stage(ARCHIVE / f'{d}.js', 'window.REPORT_ARCHIVE = window.REPORT_ARCHIVE || {};\n'
                     f'window.REPORT_ARCHIVE[{json.dumps(d)}] = {body};\n')
        stager.stage(ARCHIVE / 'index.json', json.dumps(index, ensure_ascii=False, indent=2) + '\n')
        stager.stage(ARCHIVE / 'index.js', 'window.REPORT_INDEX = ' + js_literal(index) + ';\n')
        stager.stage(DATA / 'report.js', 'window.REPORT_DATA = ' + body + ';\n')
        stager.stage(ROOT / 'feed.xml', feed(index))
        stager.commit()
    except (OSError, ValueError, TypeError, KeyError) as e:
        stager.rollback()
        print(f'게시 실패(아무 파일도 변경하지 않음): {e}', file=sys.stderr)
        return 1
    print(f'게시 완료: {d} (보관 {len(index)}일) → data/report.js, data/archive/{d}.json/.js, index.json/.js, feed.xml')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
