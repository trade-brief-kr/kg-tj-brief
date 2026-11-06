# 키르기스·타지키스탄 브리프

키르기스스탄·타지키스탄 동향을 매일 「5분 통상 브리핑」 형식으로 정리하고, 두 나라의 기본 약황과
한–양국 산업협력 현황을 함께 보는 정적 사이트. 공개 자료만 사용한다.

- 사이트: https://trade-brief-kr.github.io/kg-tj-brief/
- 상세 스타터팩: https://trade-brief-kr.github.io/kg-tj-brief/starter-pack.html
- RSS(새 브리핑 알림용): https://trade-brief-kr.github.io/kg-tj-brief/feed.xml

## 구성
| 탭 | 내용 |
|---|---|
| 일일 브리프 | ① 한국 관련 외교·인사 ② 타지키스탄·키르기스스탄 ③ 국제경제·전쟁 ④ 인근국 ⑤ 오늘 확인할 것. 날짜 이전/다음, 국가 필터(전체/키르기스스탄/타지키스탄), 텍스트 복사 |
| 국가 약황 | 기본지표·두 나라 구분·경제 이해·사업명 풀이(로군, 캄바라타-1, CKU 철도, 누레크, CASA-1000)·업무 우선순위·연락선·제재 주의·한–키르기스/한–타지키스 경제협력(관계·교역·투자·정부 의제·EDCF·KOICA) |

단순 HTML/CSS/JS(빌드·CDN 없음). `file://`로 열어도 `data/*.js` 대체본으로 동작.

```
index.html            페이지 (국가 약황 탭은 tools/profile/에서 생성)
starter-pack.html     상세 스타터팩 원문
assets/style.css, assets/app.js
data/report.json      최신 브리핑 (+ report.js)
data/archive/         날짜별 보관본 YYYY-MM-DD.json/.js, index.json/.js
feed.xml              RSS
tools/research_prompt.md     조사 규칙 (Codex 프롬프트에 그대로 포함)
tools/run_codex_research.sh  Codex CLI 조사 러너
tools/verify_report.py       후처리 검증 (날짜·스키마·기간·utm 제거)
tools/build_report_js.py     스키마 검증 + report.js
tools/publish_daily.py       게시 (보관·색인·RSS)
tools/DAILY_UPDATE.md        일일 절차
tools/profile/               국가 약황 원본(profile.html, refs.py, build_profile.py)
```

## report.json 스키마
```json
{
  "date": "2026-11-06",
  "generatedAt": "2026-11-06T08:34:00+09:00",
  "coverage": "최근 24시간 발표 중심",
  "headline": "오늘의 핵심 한 줄",
  "sections": [
    {"id": "korea", "title": "① 한국 관련 외교·인사", "items": [
      {"tag": "[한국·타지키스탄]", "countries": ["한국", "타지키스탄"], "title": "명사형 제목",
       "bullets": [{"text": "…", "source": "Avesta.tj", "url": "https://…", "altUrl": "(선택) 재게재 URL"},
                   {"text": "출처 없는 후속 설명 bullet 가능"}]}]},
    {"id": "kg_tj", "title": "② 타지키스탄·키르기스스탄", "items": []},
    {"id": "intl", "title": "③ 국제경제·전쟁", "items": []},
    {"id": "neighbors", "title": "④ 인근국", "items": []},
    {"id": "followup", "title": "⑤ 오늘 확인할 것", "items": []}
  ],
  "notes": []
}
```
규칙: sections 5개·순서 고정, headline 필수, ①~④ 항목은 출처 URL bullet 1개 이상, url이 있으면 source 필수,
URL에 utm_source 금지, ①~④ 합계 1건 이상.

## 일일 절차
`tools/DAILY_UPDATE.md` 참고: `git pull` → `bash tools/run_codex_research.sh` → `python3 tools/publish_daily.py` → commit/push → 라이브 확인.
조사는 Codex CLI(ChatGPT 로그인, `codex --search exec`)가 하고, 운영 에이전트는 직접 웹 조사하지 않는다.
