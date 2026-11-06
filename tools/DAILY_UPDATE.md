# 일일 업데이트 절차 (키르기스·타지키스탄 브리프)

매일 오전(KST) 한 번. **에이전트는 직접 웹 조사하지 않는다.** 조사는 ChatGPT 구독 기반 Codex CLI가 하고,
에이전트는 러너 실행 → 검증 → 게시 → push만 한다. 링크 curl 재검증은 기본 OFF(Codex 검증 신뢰).

## 1. 준비
```bash
cd /workspace/kg-tj-brief && git pull --ff-only
```

## 2. 조사 (Codex)
```bash
bash tools/run_codex_research.sh            # 결과: data/report.json (검증 통과 시에만 교체)
```
- 종료 코드: 0 성공 / 2 환경 / 10 Codex 실패 / 11 타임아웃 / 12 결과 없음·JSON 오류 / 13 검증 실패 / 14 사전검증 실패
- 10·11이면 한 번만 재실행. 그 밖의 실패는 게시하지 않고 로그(/tmp/kg-tj-brief-runs/codex-run-*/)를 보고.
- 드라이런: `bash tools/run_codex_research.sh --out /tmp/kgtj-dry/report.json`
- 프롬프트만 확인: `bash tools/run_codex_research.sh --prompt-only --out /tmp/kgtj-dry/report.json`
- 품질 경고(키르기스/타지키스탄 항목 0건 등)는 verify-log.json의 warnings에 남고 게시는 막지 않는다.

## 3. 게시
```bash
python3 tools/publish_daily.py              # 검증 + data/archive/<date>.json/.js + index + report.js + feed.xml
git add -A data feed.xml && git commit -m "Daily brief $(TZ=Asia/Seoul date +%F)" && git push
```

## 4. 확인
- https://trade-brief-kr.github.io/kg-tj-brief/data/report.json 의 date가 오늘인지 (Pages 반영 1~2분).
- 알림: 게시 후 headline과 항목 수를 사용자에게 알림(알림 경로는 운영 에이전트 루틴이 담당). RSS: feed.xml.

## 규칙 요약
- 수동 정정은 data/report.json 수정 후 3단계만 다시 실행.
- 조사 규칙은 tools/research_prompt.md (수정 가능). 스키마는 README 참고.
- 국가 약황 탭 수정: tools/profile/profile.html 편집 → `python3 tools/profile/build_profile.py`.
