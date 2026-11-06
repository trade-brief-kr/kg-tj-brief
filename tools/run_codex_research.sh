#!/usr/bin/env bash
# 키르기스·타지키스탄 브리프 일일 조사 러너: ChatGPT(Codex CLI, 웹검색)로 오늘자 report.json을 작성하고 검증한다.
# 에이전트는 직접 웹 조사하지 않고 이 스크립트만 실행한다. 게시는 하지 않는다.
#
# 사용법: bash tools/run_codex_research.sh [--out PATH] [--timeout SEC] [--check-links] [--keep-work] [--prompt-only]
#   --out PATH      검증 통과본을 쓸 위치 (기본 data/report.json). 드라이런은 저장소 밖 경로 지정.
#   --timeout SEC   Codex 최대 실행 시간 (기본 1800초 = 30분, 환경변수 CODEX_TIMEOUT)
#   --check-links   (선택) 후처리에서 URL curl 재확인(404/410/DNS만 삭제). 기본 OFF — Codex 검증을 신뢰.
#   --keep-work     Codex 임시 작업 폴더를 지우지 않음
#   --prompt-only   Codex를 실행하지 않고 프롬프트만 <로그폴더>/prompt.md 로 생성 후 종료(0).
#
# 종료 코드 (0일 때만 다음 단계 `python3 tools/publish_daily.py` 진행)
#   0  성공: 검증 통과본이 --out 에 기록됨
#   2  사용법·환경 오류 (codex 없음, 프롬프트 파일 없음, 동시 실행 중)
#   10 Codex 실행 실패 (비정상 종료)
#   11 Codex 타임아웃
#   12 Codex 결과 없음 또는 JSON 파싱 불가
#   13 검증 실패 (날짜가 오늘 아님, 스키마 오류, ①~④ 항목 0건 등)
#   14 publish_daily.py와 동일 규칙의 사전검증 실패
# 실패 시 --out 파일은 변경되지 않는다. 로그: /tmp/kg-tj-brief-runs/codex-run-<날짜시각>/ (--out 지정 시 그 폴더)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/data/report.json"
TIMEOUT="${CODEX_TIMEOUT:-1800}"
EFFORT="${CODEX_EFFORT:-high}"
CHECK_LINKS=""
KEEP=0
PROMPT_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --check-links) CHECK_LINKS="--check-links"; shift ;;
    --keep-work) KEEP=1; shift ;;
    --prompt-only) PROMPT_ONLY=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done

[ -f "$ROOT/tools/research_prompt.md" ] || { echo "tools/research_prompt.md 없음" >&2; exit 2; }
if [ "$PROMPT_ONLY" != 1 ]; then command -v codex >/dev/null || { echo "codex CLI 없음" >&2; exit 2; }; fi
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

exec 9>/tmp/kg-tj-brief-research.lock
flock -n 9 || { echo "다른 조사 러너가 실행 중" >&2; exit 2; }

TODAY="$(TZ=Asia/Seoul date +%F)"
YESTERDAY="$(TZ=Asia/Seoul date -d '-1 day' +%F)"
NOW_ISO="$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)"
NOW_HM="$(TZ=Asia/Seoul date +%H:%M)"
if [ "$OUT" = "$ROOT/data/report.json" ]; then LOGBASE="/tmp/kg-tj-brief-runs"; else LOGBASE="$(dirname "$OUT")"; fi
LOGDIR="$LOGBASE/codex-run-$TODAY-$(TZ=Asia/Seoul date +%H%M%S)"
mkdir -p "$LOGDIR"
WORK="$(mktemp -d /tmp/codex-kgtj.XXXXXX)"
cleanup() { [ "$KEEP" = 1 ] || rm -rf "$WORK"; }
trap cleanup EXIT

# 직전 보고서(중복 방지·누락 보완 참고용) 제목 목록
PREV_TITLES="$(python3 - "$ROOT/data/report.json" "$TODAY" <<'PY' 2>/dev/null
import json, sys
try:
    r = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    sys.exit(0)
if r.get('date') == sys.argv[2]:
    sys.exit(0)
print(f"직전 보고서 {r.get('date')}:")
for s in r.get('sections', []):
    for it in s.get('items', []):
        if it.get('title'):
            print(f"- {it.get('tag','')} {it['title']}")
PY
)"

# --- 자체완결 프롬프트 구성 ---------------------------------------------------
PROMPT="$LOGDIR/prompt.md"
{
cat <<HDR
당신은 한국 산업통상 담당자용 「키르기스·타지키스탄 브리프」(5분 통상 브리핑)의 조사·작성자다.
웹 검색으로 실제 기사·공식 발표를 찾아 확인하고, 결과를 현재 작업 폴더의 report.json 파일 하나로만 저장한다.
다른 파일은 만들거나 수정하지 않는다. 화면 출력(최종 메시지)은 "DONE" 한 단어로 충분하다.

## 실행 정보
- 오늘(KST): $TODAY, 현재 시각: $NOW_ISO
- 수집 구간: $YESTERDAY $NOW_HM ~ $TODAY $NOW_HM KST (최근 24시간). [누락 보완] 항목만 최대 3일 전까지.

## 절대 원칙
1. 지어내지 않는다. 검색으로 확인한 실제 URL·매체·게시 시각만 쓴다.
2. ①~④ 각 항목의 첫 bullet에는 "source"(매체명), "url"(기사 원문 주소), "publishedAt"(게시 시각, 시간대 포함 ISO 8601)을 넣는다.
   publishedAt은 후처리에서 기간 검증 후 제거된다. 기간 밖이면 삭제되므로 확실한 것만 쓴다.
3. 출처 URL이 하나도 없는 ①~④ 항목은 삭제된다. ⑤ 오늘 확인할 것은 출처 없이 써도 된다.
4. 링크 HTTP 재검증은 후처리에서 하지 않는다. 출처·URL 검증은 Codex(본인)가 한다.
5. URL에서 utm_source 등 추적 파라미터를 붙이지 않는다.

$PREV_TITLES

## report.json 스키마 (정확히 이 구조)
{
  "date": "$TODAY",
  "generatedAt": "작성 완료 시각 (예: ${TODAY}T08:10:00+09:00)",
  "coverage": "최근 24시간 발표 중심",
  "headline": "오늘의 핵심 한 줄",
  "sections": [
    {"id":"korea","title":"① 한국 관련 외교·인사","items":[
      {"tag":"[한국·타지키스탄]","countries":["한국","타지키스탄"],"title":"명사형 제목",
       "bullets":[{"text":"명사형 종결 문장.","source":"Avesta.tj","url":"https://...","publishedAt":"${TODAY}T10:00:00+05:00"},
                  {"text":"단계·금액·미확인 사항 구분."}]}]},
    {"id":"kg_tj","title":"② 타지키스탄·키르기스스탄","items":[]},
    {"id":"intl","title":"③ 국제경제·전쟁","items":[]},
    {"id":"neighbors","title":"④ 인근국","items":[]},
    {"id":"followup","title":"⑤ 오늘 확인할 것","items":[{"tag":"","countries":["타지키스탄"],"title":"","bullets":[{"text":"… 확인 필요."}]}]}
  ],
  "notes": ["확인하지 못한 점 등 (선택)"]
}
- bullet 선택 필드: "altUrl"(재게재 URL, 원문 url과 함께만).
- sections는 정확히 5개, 위 id 순서. 항목이 없으면 "items": [].

## 조사 규칙 (사용자 지정, 그대로 따른다)

HDR
cat "$ROOT/tools/research_prompt.md"
cat <<TAIL

## 검색 체크리스트 (모두 개별 검색한 뒤 작성)
- 한–타지키스탄, 한–키르기스스탄 (한국어·러시아어·영어: "Южная Корея Таджикистан", "Кыргызстан Корея", KOTRA, KOICA, 대사).
- 타지키스탄: Avesta, Khovar, Asia-Plus, president.tj — 정부결정·인사, 로군·누레크, 광물, 철도, 국제금융기구.
- 키르기스스탄: Kabar, 24.kg, AKIpress, Kaktus.media, egov.kg/gov.kg — 내각 인사, 캄바라타-1, CKU 철도, EAEU 제도, 제재·결제.
- 인근국: 카자흐스탄·우즈베키스탄·투르크메니스탄·아프가니스탄 (Kazinform, Trend, UzDaily, Gazeta.uz, Interfax).
- 국제: Reuters 원문 우선 — 러시아–우크라이나, 이란·호르무즈, 중·미 통상, 에너지.

## 마지막 점검 (저장 전에 반드시)
- date가 "$TODAY"인지, sections 5개·순서·id, headline 비어 있지 않은지, JSON 문법 유효.
- ①~④ 각 항목 첫 bullet의 source·url·publishedAt 재확인. 기간 밖·불확실하면 삭제.
- 명사형 종결, 합의·실행·입찰·금융 구분, ⑤에 내부 기밀·내부 인명 없음.
- 현재 작업 폴더에 report.json 저장 (UTF-8). 다른 파일 생성·수정 금지.
TAIL
} > "$PROMPT"
if [ "$PROMPT_ONLY" = 1 ]; then echo "프롬프트만 생성(Codex 미실행): $PROMPT"; exit 0; fi

# --- Codex 실행 (임시 폴더에서만 쓰기 가능: 저장소 수정 불가) ---
echo "[$(TZ=Asia/Seoul date +%T) KST] Codex 조사 시작 (최대 ${TIMEOUT}s) work=$WORK log=$LOGDIR"
START=$(date +%s)
# 비밀 환경변수는 Codex에 넘기지 않는다.
for v in $(compgen -e | grep -E '^(DATA_GO_KR|GH_|GITHUB_)|KEY|TOKEN|SECRET|PASSWORD' || true); do unset "$v"; done
timeout --kill-after=60 "$TIMEOUT" codex --search exec -c model_reasoning_effort="\"$EFFORT\"" --skip-git-repo-check --ephemeral \
  -s workspace-write -C "$WORK" -o "$LOGDIR/codex-last-message.txt" - < "$PROMPT" \
  > "$LOGDIR/codex.log" 2>&1
RC=$?
ELAPSED=$(( $(date +%s) - START ))
echo "[$(TZ=Asia/Seoul date +%T) KST] Codex 종료 rc=$RC, ${ELAPSED}s"
echo "$ELAPSED" > "$LOGDIR/elapsed_seconds"
if [ $RC -eq 124 ] || [ $RC -eq 137 ]; then echo "Codex 타임아웃(${TIMEOUT}s)" >&2; exit 11; fi
if [ $RC -ne 0 ]; then echo "Codex 실패 rc=$RC (로그: $LOGDIR/codex.log)" >&2; tail -5 "$LOGDIR/codex.log" >&2; exit 10; fi
if [ ! -s "$WORK/report.json" ]; then echo "Codex가 report.json을 만들지 않음" >&2; exit 12; fi
cp "$WORK/report.json" "$LOGDIR/raw-report.json"

# --- 후처리 검증 (날짜·스키마·기간; 링크 curl은 기본 OFF) ---
python3 "$ROOT/tools/verify_report.py" --input "$LOGDIR/raw-report.json" --output "$LOGDIR/verified-report.json" \
  --log "$LOGDIR/verify-log.json" $CHECK_LINKS
VRC=$?
if [ $VRC -ne 0 ]; then exit $VRC; fi
python3 - "$LOGDIR/verified-report.json" "$TODAY" "$ROOT/tools" <<'PY' || exit 14
import json, sys
sys.path.insert(0, sys.argv[3])
from build_report_js import validate
r = json.load(open(sys.argv[1], encoding='utf-8'))
validate(r)
assert r['date'] == sys.argv[2], f"date {r['date']} != {sys.argv[2]}"
print(f"사전검증 통과(게시 안 함): {r['date']}")
PY

cp "$LOGDIR/verified-report.json" "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
echo "완료: $OUT (로그 $LOGDIR). 다음 단계: python3 tools/publish_daily.py"
exit 0
