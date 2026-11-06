#!/usr/bin/env python3
"""Codex가 만든 키르기스·타지키스탄 브리프를 게시 전에 후처리·검증한다 (항목은 지우기만, 만들지 않음).

사용법:
  python3 tools/verify_report.py --input RAW.json --output REPORT.json [--log LOG.json]
                                 [--check-links] [--now ISO] [--window-hours 30]
처리:
  1. JSON 파싱, date == 오늘(KST) 필수.
  2. 모든 URL에서 utm_* 추적 파라미터 제거 (utm_source=chatgpt.com 등).
  3. sections를 korea, kg_tj, intl, neighbors, followup 5개 순서로 정규화(제목 기본값 채움).
  4. bullet에 publishedAt이 있으면 기간 확인: 기본 30시간(24h+여유). text가 "[누락 보완"으로 시작하면 96시간.
     기간 밖 → 삭제. url은 있는데 source가 없으면 삭제. publishedAt은 출력에서 제거.
  5. 링크 curl 재검증은 기본 OFF (Codex 검증 신뢰). --check-links 시 404/410/DNS 실패만 삭제.
  6. ①~④ 항목 중 출처 URL bullet이 하나도 없는 항목 삭제. 빈 항목 삭제.
  7. build_report_js.validate 스키마 검증 (headline, sections 5개, ①~④ 항목 ≥1).
품질 경고(키르기스/타지키스탄 항목 0건, 한국 관련 0건)는 로그·stderr에만 남기고 실패시키지 않는다.
종료 코드: 0 성공, 12 읽기/JSON 오류, 13 검증 실패. 실패 시 --output은 쓰지 않고 *.rejected.json 남김.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_report_js import SECTION_IDS, SECTION_TITLES, validate  # noqa: E402

KST = timezone(timedelta(hours=9))


def clean_url(u):
    if not isinstance(u, str) or not u.strip():
        return u
    p = urlparse(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith('utm_')]
    return urlunparse(p._replace(query=urlencode(q)))


def parse_ts(v):
    try:
        t = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return t if t.tzinfo else None
    except ValueError:
        return None


def link_dead(u):
    try:
        out = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-L', '--max-time', '20', '-A', 'Mozilla/5.0',
                              '-w', '%{http_code}', u], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return False
    code = out.stdout.strip()
    if code in ('404', '410'):
        return True
    return code == '000' and 'resolve' in out.stderr.lower()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--log')
    ap.add_argument('--check-links', action='store_true')
    ap.add_argument('--now')
    ap.add_argument('--window-hours', type=float, default=30.0)
    a = ap.parse_args(argv)
    now = parse_ts(a.now) if a.now else datetime.now(KST)
    today = now.astimezone(KST).date().isoformat()
    log = {'removed': [], 'warnings': [], 'today': today}

    def finish(code, msg, report=None):
        log['result'] = msg
        if a.log:
            Path(a.log).write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')
        if code == 0:
            Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print('검증 통과:', msg)
        else:
            if report is not None:
                Path(a.output + '.rejected.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print('검증 실패:', msg, file=sys.stderr)
        for w in log['warnings']:
            print('품질 경고:', w, file=sys.stderr)
        return code

    try:
        r = json.loads(Path(a.input).read_text(encoding='utf-8'))
        assert isinstance(r, dict)
    except Exception as e:  # noqa: BLE001
        return finish(12, f'JSON 읽기 실패: {e}')
    if r.get('date') != today:
        return finish(13, f"date {r.get('date')} != 오늘 {today}", r)

    by_id = {s.get('id'): s for s in r.get('sections', []) if isinstance(s, dict)}
    sections = []
    for sid in SECTION_IDS:
        s = by_id.get(sid, {})
        items = []
        for it in s.get('items', []) or []:
            if not isinstance(it, dict):
                continue
            bullets = []
            for b in it.get('bullets', []) or []:
                if not isinstance(b, dict) or not str(b.get('text', '')).strip():
                    continue
                for k in ('url', 'altUrl'):
                    if b.get(k):
                        b[k] = clean_url(b[k])
                    else:
                        b.pop(k, None)
                where = f"{sid}:{it.get('title', '')}"
                if b.get('url') and not str(b.get('source', '')).strip():
                    log['removed'].append({'where': where, 'reason': 'source 없음', 'text': b['text'][:60]})
                    continue
                pub = b.pop('publishedAt', None)
                if pub:
                    t = parse_ts(pub)
                    hours = 96 if b['text'].lstrip().startswith('[누락 보완') else a.window_hours
                    if t is None or t < now - timedelta(hours=hours) or t > now + timedelta(hours=2):
                        log['removed'].append({'where': where, 'reason': f'기간 밖/형식 오류 publishedAt={pub}', 'text': b['text'][:60]})
                        continue
                if a.check_links and b.get('url') and link_dead(b['url']):
                    log['removed'].append({'where': where, 'reason': '링크 404/410/DNS', 'url': b['url']})
                    continue
                bullets.append(b)
            if not bullets:
                continue
            if sid != 'followup' and not any(b.get('url') for b in bullets):
                log['removed'].append({'where': f"{sid}:{it.get('title', '')}", 'reason': '출처 URL 없는 항목'})
                continue
            it['bullets'] = bullets
            it.setdefault('tag', '')
            it.setdefault('countries', [])
            it.setdefault('title', '')
            items.append(it)
        sections.append({'id': sid, 'title': s.get('title') or SECTION_TITLES[sid], 'items': items})
    r['sections'] = sections
    r.setdefault('notes', [])

    allc = [c for s in sections[:4] for it in s['items'] for c in it.get('countries', [])]
    for c in ('키르기스스탄', '타지키스탄'):
        if c not in allc:
            log['warnings'].append(f'{c} 항목 0건')
    if not sections[0]['items']:
        log['warnings'].append('① 한국 관련 항목 0건')
    try:
        validate(r)
    except ValueError as e:
        return finish(13, str(e), r)
    n = sum(len(s['items']) for s in sections[:4])
    return finish(0, f"{r['date']} 항목 {n}건(①~④), 삭제 {len(log['removed'])}건", r)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
