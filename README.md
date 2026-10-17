# 트렌드 소스 수집기

기술·제품·보안 분야의 13개 소스를 같은 데이터 형식으로 수집합니다. Python 3.11 이상에서 실행하며 외부 패키지가 필요하지 않습니다.

## 실행

압축을 푼 폴더에서 실행하세요.

```bash
uv run trend_collector.py --config config.toml
```

수집 시작 전에 설정 파일 경로, 기본값·명령행 옵션을 반영한 수집 설정,
활성·비활성 소스와 소스별 설정, EPSS 활성 여부를 섹션별로 읽기 쉽게 출력합니다.
토큰·비밀번호·API 키 등 민감한 키의 값은 `***`로 가립니다.

처음에는 소량으로 확인할 수 있습니다.

```bash
uv run trend_collector.py --config config.toml --limit 3
```

수집 대상은 `config.toml`의 소스별 `enabled`로 관리합니다:

```toml
[sources.geeknews]
enabled = true

[sources.hackernews]
enabled = false
```

설정 파일을 지정하면 그 파일에 등록된 소스 중 활성화된 소스만 실행합니다.
`enabled`를 생략한 등록 소스는 활성화로 취급하며, 파일에 없는 소스는 실행하지 않습니다.

`--config` 없이 실행하면 기존처럼 모든 사용 가능한 소스를 기본 설정으로 실행합니다. 설정 파일과 출력 경로는 현재 작업 폴더를 기준으로 해석합니다.

`uv`가 호환되는 Python을 선택하며, 설치되어 있지 않으면 필요에 따라 다운로드합니다. 별도의 가상환경 생성·활성화 명령은 필요하지 않습니다. [uv 스크립트 실행 안내](https://docs.astral.sh/uv/guides/scripts/)

## 트렌드 분석

수집된 데이터를 분석하는 별도 실행 엔드포인트입니다. 외부 API·LLM 없이
규칙 기반으로 실행하며 원본 수집 항목과 관측 이력은 수정하지 않습니다.

```bash
uv run trend_analyzer.py --config config.toml
uv run trend_viewer.py --config config.toml
```

뷰어의 **트렌드 분석** 메뉴에서 저장된 분석 실행을 선택할 수 있습니다.
처음 관측한 항목, 여러 출처에서 관측한 주제, 항목 수 증가, 보안 동향을 필터링하고
근거 링크·관측 당시 지표·EPSS를 확인합니다. 새 분석 이후에는 새로고침을 누르세요.

- 주제: AI, 개발 도구, 클라우드·인프라, 보안, 하드웨어, 제품·서비스, 기타·미분류
- 연결 기준: CVE → GitHub 저장소 → 설정된 이름·키워드 → 정규화 URL
- 동일 항목은 `(source, external_id)`로 중복 제거하고 반복 관측은 별도 집계
- 동일 항목의 점수·투표·누적 별 등은 소스 내에서만 변화 비교
- 출처별 점수를 합산한 종합 순위나 원인에 대한 생성형 요약은 제공하지 않음

기본은 현재까지 최근 24시간과 바로 이전 24시간의 비교입니다.
`[analysis] window_hours = 24` 또는 `--window-hours`로 길이를 바꿀 수 있습니다.
아래 명령은 **한국 시간 기준 종료된 하루**의 보고서를 만듭니다.

```bash
uv run trend_analyzer.py --config config.toml --date 2026-10-16
```

`--date`는 24시간 설정에서만 사용하며 오늘 또는 미래 날짜는 지정할 수 없습니다.
특정 데이터베이스는 `--database`, 보고서 위치는 `--out`으로 바꿉니다.
기본 결과는 `collector.output_dir/analysis/<분석ID>/report.md`와 `report.json`에 저장합니다.
SQLite의 `analysis_runs`는 분석 버전·구간·보고서, `analysis_members`는 항목별 분류 근거와
연결 식별자를 보존합니다. 재실행은 별도 분석 ID로 저장하여 이전 결과를 유지합니다.

기업·제품 이름의 연결 규칙은 추가·교체할 수 있습니다.

```toml
[analysis]
window_hours = 24

[analysis.entities]
MyTool = ["mytool", "마이툴"]
```

분류와 연결은 키워드 기반 추정입니다. 같은 이름의 묶음은 동일 사건을 의미하지 않고,
다중 출처가 독립적인 검증을 뜻하지도 않습니다. 여러 CVE를 포함한 글은 여러 묶음의
근거가 될 수 있으므로 묶음별 항목 수를 합산하지 마세요. 기존 비IT 항목도 삭제하지
않으며 맞는 분류가 없으면 미분류에 남습니다.

신규는 최초 공개가 아니라 **수집 범위 내 최초 관측**입니다. 이전 구간 시작까지
수집 이력이 없거나 비교 가능한 소스가 없으면 증가 신호를 계산하지 않습니다.
증가량은 양쪽 구간에서 오류 없이 수집된 공통 소스의 고유 항목 수 차이이며,
수집 빈도·수집 설정·표본 크기 변화의 영향을 받습니다. 인기도의 인과적 상승이나
시장 전체 동향으로 해석해서는 안 됩니다. 보고서에 소스별 정상·실패 실행 건수를
함께 보존합니다. 주제 분류는 다중 분류이므로 주제별 건수는 서로 겹칩니다.

구현은 `src/analysis/`의 `classification.py`, `grouping.py`, `signals.py`,
`engine.py`, `reporting.py`로 나뉩니다.

## 저장 데이터 조회

수집과 조회는 별도 프로세스입니다. `trend_collector.py`로 데이터를 수집한 뒤
다음 명령으로 로컬 조회 화면을 실행합니다. 외부 패키지는 필요하지 않습니다.

```bash
uv run trend_viewer.py --config config.toml
```

브라우저에서 [로컬 조회 화면](http://127.0.0.1:8765)을 엽니다.
조회 서버는 `127.0.0.1`에서만 접속을 받고, 설정의 `collector.output_dir` 아래
`trends.sqlite3`를 읽기 전용으로 엽니다. 서버 종료는 `Ctrl+C`입니다.

- 최신 항목 목록, 키워드·CVE 검색, 소스 필터와 페이지 이동
- 실행별 수집 건수, 소스 상태와 실패 이유
- 선택한 실행 당시의 관측 데이터 조회
- 항목 상세, 원문·토론 링크, 지표·EPSS·메타데이터와 최근 100건의 관측 이력
- 새 수집 결과 반영을 위한 새로고침

데이터베이스가 아직 없으면 수집 안내가 표시되며 빈 파일을 생성하지 않습니다.
실행 선택 상자에는 최근 100개 실행이 표시됩니다. 그 이전 실행은 실행 이력
화면에서 페이지를 이동하여 선택할 수 있습니다. 이 화면은 분류·점수화 등
새로운 분석을 수행하지 않고 저장된 데이터를 보여줍니다.

다른 데이터베이스나 포트를 사용할 수도 있습니다.

```bash
uv run trend_viewer.py --database data/trends.sqlite3 --port 8780
```

`trend_viewer.py`가 CLI 설정과 조회 서버 실행을 담당합니다.
`src/viewer/repository.py`는 조회 쿼리, `src/viewer/server.py`는 HTTP 핸들러,
`src/viewer/static/`은 화면을 담당합니다.

## 수집 범위와 접근 방식

| 소스 이름 | 방식 | 수집 범위 / 조건 |
|---|---|---|
| `geeknews` | 공식 Atom 피드 | 최신 뉴스·Ask·Show. 제목·일시·피드 본문·토론 주소 |
| `producthunt` | 공개 홈페이지 HTML | 오늘 제품 목록의 제목·태그라인·태그·투표 수. 토큰 불필요 |
| `hackernews` | 공식 Firebase API | top/new/best/ask/show 중 하나. 제목·원문 링크·점수·댓글 수 |
| `reddit` | 공개 old-layout HTML | 지정 커뮤니티의 new/hot/top 목록·점수·댓글 수. HTTP 접근 제한 시 error |
| `github` | 공개 Trending HTML | 일/주/월별 현재 목록. 설명·언어·누적 별·기간 내 별 증가 |
| `google_trends` | 공식 Trending Now RSS | 지정 국가의 급상승 검색어·대략적인 트래픽·관련 기사 |
| `indiehackers` | 공개 홈페이지 HTML | 화면에 제공되는 스토리 카드·제목·추천·댓글 수 |
| `disquiet` | 공개 홈페이지 HTML | 화면에 제공되는 게시글·본문·연결된 제품·추천·댓글 수 |
| `huggingface` | 공식 Hub API | 현재 trendingScore순 모델·태그·좋아요·다운로드 |
| `bleepingcomputer` | 공식 RSS | 최신 보안 뉴스와 피드에 제공된 요약 |
| `cisa_kev` | 공식 JSON | 실제 악용이 확인된 취약점. 카탈로그 추가 날짜 내림차순 |
| `github_advisories` | 공개 HTML | 검토된 취약점 권고 목록·CVE·심각도·게시 시각. HTML 다음 페이지 탐색 |
| `kisa` | 공식 보호나라 RSS | 최신 보안공지와 피드에 제공된 설명 |

2026-10-17 HTML 방식 확인: Product Hunt·GitHub Trending·GitHub Advisories에서
각 2건의 실제 수집·정규화를 확인했습니다. Reddit의 파싱·페이지 이동은 HTML
모의 응답으로 검증했습니다. robots.txt 검사 제거 후의 실제 접근 가능 여부는
서버의 HTTP 응답에 따라 달라집니다. 기존 `example-output`은 이전 수집 방식의 예시입니다.
보안 RSS·KEV 소스는 각각 소량의 실제 응답 수집도 확인했습니다.

## 보안 트렌드 수집과 EPSS

```bash
uv run trend_collector.py --config config.toml --limit 20
```

보안 소스만 수집하려면 설정에서 위 네 소스의 `enabled`를 `true`, 나머지를
`false`로 설정하세요. 별도 TOML 파일에 보안 소스 네 개만 등록해도 됩니다.

네 소스 모두 토큰 없이 사용할 수 있습니다. GitHub 권고는 공개 HTML을 파싱하며
API나 `GITHUB_TOKEN`을 사용하지 않습니다.
`sources.github_advisories.ecosystem`과 `severity`로 패키지 생태계·심각도를
필터링할 수 있습니다. 권고 목록 HTML에 없는 CVSS 점수·패치 버전은 추정하지 않습니다.
`--days`는 호환용으로만 남아 있으며 현재 수집 결과에 영향을 주지 않습니다.

보안 항목의 `metadata.cve_ids`는 출처 간 연결에 쓸 수 있는 CVE 목록입니다.
뉴스·KISA는 피드 제목·설명에 나타난 식별자만 추출하며 기사 본문은 방문하지 않습니다.
같은 CVE를 다뤄도 출처별 항목은 보존하고, 기존 URL 기반 `group_id`는 유지합니다.
CISA의 `date_added`는 카탈로그에 추가된 날짜로, 취약점 공개 시각으로 변환하지 않습니다.

제공된 `config.toml`은 `[enrichment.epss] enabled = true`로 EPSS 보강을 켭니다.
설정 없이 실행하면 EPSS는 꺼져 있습니다. 수집된 CVE를 중복 제거해 100개씩 조회하고
`metrics.epss.<CVE>`에 `probability`, `percentile`, `date`를 저장합니다.
응답에 없는 CVE는 0으로 추정하지 않고 지표를 생략합니다. 조회 결과와 누락 목록은
`manifest.json`의 `enrichment.epss`에서 확인합니다. 보강 실패 시에도 원래 수집
데이터는 저장하며, `--strict`에서는 보강의 `partial`·`error`도 종료 코드 1로 처리합니다.

EPSS도 DI로 교체하거나 별도로 사용할 수 있습니다.

```python
from src.enrichment import EPSSEnricher

enricher = EPSSEnricher(http)
rows = [item.record() for item in source.collect(request)]
status = enricher.enrich(rows)  # rows의 metrics에 EPSS 결과를 추가
# 실행부 주입: main([...], sources=my_sources, enricher=enricher)
```

CVSS는 심각도, KEV는 확인된 악용, EPSS는 악용 가능성 예측입니다.
뉴스 언급량과는 별개 신호로 보존하며 합산 점수는 계산하지 않습니다.

공식 자료: [BleepingComputer RSS](https://www.bleepingcomputer.com/rss-feeds/),
[CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog),
[GitHub Advisory Database](https://github.com/advisories),
[보호나라 RSS 안내](https://www.krcert.or.kr/kr/subPage.do?menuNo=205121),
[FIRST EPSS](https://www.first.org/epss/).

## IT 카테고리 설정

제공된 `config.toml`은 Google Trends·GeekNews·Product Hunt·Hacker News·Reddit·
Indie Hackers·Disquiet에 `category = "technology"`를 적용합니다. Reddit의 기본
커뮤니티도 `programming`, `technology`, `netsec`로 변경했습니다. GitHub·Hugging Face와
보안 전용 소스는 기존 수집 범위 자체가 기술·보안 분야이므로 별도 키워드 필터를
기본 적용하지 않습니다.

```toml
[sources.google_trends]
enabled = true
geo = "KR"
category = "technology"
scan_limit = 500
include_keywords = ["wasm", "양자컴퓨팅"]
exclude_keywords = ["연예인"]
```

`technology`는 로컬의 한·영 IT 키워드 필터입니다. 제목·요약·태그를 검사하며,
Google Trends에서는 요약에 보존된 관련 기사 제목도 검사합니다. RSS 요청에
지원 여부가 불명확한 카테고리 파라미터를 붙이지 않습니다. Google Trends는 IT 뉴스
피드가 아니라 급상승 검색어 피드이므로, 해당 피드에 IT 항목이 없으면 빈 결과가
정상입니다. [Google Trends 안내](https://support.google.com/trends/answer/3076011?hl=en)

`include_keywords`는 IT 기본 키워드에 추가할 단어이며 `exclude_keywords`는
포함 조건보다 우선합니다. `category = "all"` 또는 카테고리 설정 생략으로 기본
IT 키워드 필터를 끌 수 있습니다. 다른 소스에도 같은 설정을 적용할 수 있습니다.

필터를 적용한 소스는 `scan_limit`개까지 후보를 살펴보고, 통과한 항목을
`collector.limit`개까지 반환합니다. 후보 예산은 최소 `collector.limit`만큼이며,
원래 피드가 제공하는 항목 수를 늘리거나 과거 데이터를 소급 수집하지는 않습니다.
기본 후보 예산은 100, Google Trends는 설정에서 500, HN은 요청량을 고려해 60입니다.
통과한 항목의 `metadata.category_filter`에 적용 방식을 기록하고, 실행 상태의
`filter`에는 `scanned`, `filtered`, `accepted`를 기록합니다.

필터는 기본 소스 구성 함수 `create_sources`에서 DI 데코레이터로 적용합니다.
직접 만든 소스에는 `src.categories.CategorySource(source, config)`를 씌워 적용합니다.
키워드 방식이므로 일부 오분류·누락이 가능하며, 기존 데이터는 삭제하지 않습니다.
이전 실행 데이터는 조회 화면에 계속 표시됩니다.

## 인증 설정

Product Hunt·Reddit·GitHub Trending·GitHub Advisories는 공개 HTML 요청을 사용하며
API 토큰이 필요하지 않습니다. 이 소스들에는 토큰이나 로그인 쿠키를 전송하지 않습니다.
Hugging Face 공개 모델 조회에는 선택적으로 `HF_TOKEN`을 사용할 수 있습니다.
`.env` 파일은 자동으로 읽지 않습니다.

```bash
$env:HF_TOKEN = "발급받은_Hugging_Face_토큰"
uv run trend_collector.py --config config.toml
```

HTML 수집은 robots.txt를 조회하거나 검사하지 않고 대상 페이지를 직접 요청합니다.
설정한 요청 간격·타임아웃·재시도는 적용하며, 401·403 등 HTTP 오류는 소스 실패로 기록합니다.

## 설정

`config.toml`에서 다음을 바꿀 수 있습니다.

- `collector.limit`: 소스당 최대 항목 수. 기본 20, 최대 500. Reddit은 커뮤니티 전체에 나누어 배정합니다.
- `collector.max_workers`: 동시에 수집할 소스 수. 기본 4, 범위 1~32. 1이면 순차 실행합니다.
- `collector.days`: 호환용 옵션. 현재 HTML·피드 목록 수집에는 적용하지 않습니다.
- `collector.request_interval`: 같은 호스트에 대한 최소 요청 간격. 기본 1초.
- `collector.timeout`, `retries`: 요청 시간 제한과 재시도 횟수.
- 각 소스의 `enabled`: 기본 수집 대상에 포함할지 여부.
- `sources.reddit.subreddits`: 실제 타깃 고객이 모이는 커뮤니티 목록.
- `sources.github.since`, `language`: Trending 기간과 언어.
- `sources.google_trends.geo`: 국가 코드. 기본 KR.

수집 대상은 설정 파일의 `sources`에서만 선택합니다. 알 수 없는 소스명이나
활성화된 소스가 없는 설정은 오류로 처리합니다. `--limit`, `--days`, `--out`은
설정 파일보다 우선합니다.

## 저장 결과

```text
data/
  trends.sqlite3
  runs/
    <UTC 실행 시각_고유번호>/
      items.jsonl
      items.csv
      manifest.json
```

- `items.jsonl`: 분석·후속 처리용. 항목당 JSON 한 줄입니다.
- `items.csv`: UTF-8 BOM으로 저장하여 한글을 지원합니다. 리스트와 지표는 셀 안에 JSON으로 들어갑니다.
- `manifest.json`: 소스별 상태·건수·실패 이유를 확인합니다.
- `trends.sqlite3`: 반복 실행할 때 최신 항목과 매 실행의 관측값을 누적합니다.

주요 필드:

| 필드 | 의미 |
|---|---|
| `source`, `external_id` | 출처와 출처 내 안정적인 식별자 |
| `title`, `summary`, `tags` | 제목, 제공된 본문/설명/요약, 태그 |
| `url`, `discussion_url` | 수집 대상 URL과 토론 주소 |
| `canonical_url`, `group_id` | 추적 매개변수를 제거한 URL과 URL 그룹 식별자 |
| `published_at` | 제공되는 경우 게시 시각, 없으면 null |
| `observed_at` | 수집 시각. 모든 시각은 UTC로 저장 |
| `metrics` | 소스별 점수·댓글·별·다운로드 등. 제공되지 않으면 누락 또는 null |
| `rank` | 선택한 목록의 순서. Reddit은 커뮤니티별 순서 |
| `collection_method`, `metadata` | 접근 방식, 기간·지역·연결 제품 등 맥락 |

SQLite의 `items`는 `(source, external_id)` 기준 최신 상태이며 `observations`는 실행별 기록입니다. 같은 항목을 다시 수집해도 최신 항목은 중복 생성하지 않고 관측 이력은 추가합니다. 서로 다른 소스의 같은 원문은 출처별로 보존하며, URL이 같을 때만 `group_id`로 연결합니다.

## 범위와 해석상의 한계

- **기본 동작은 현재 목록을 관측하는 방식입니다.** `--days`는 호환용으로 유지하며 과거 N일을 소급 수집하지 않습니다. 주기적으로 직접 실행하면 관측 이력이 쌓입니다. 스케줄러 등록은 포함하지 않았습니다.
- 피드·공개 홈페이지의 항목 수는 한정되어 있습니다. `limit`보다 적게 반환될 수 있고, 전체 게시물을 빠짐없이 보관한다고 보장하지 않습니다.
- 긱뉴스 RSS에는 현재 원문 주소·추천·댓글 수가 없어 이를 추정하지 않습니다. 토론 주소만 보존하므로 HN과의 원문 중복을 완전히 잡을 수 없습니다.
- **Google Trends는 급상승 검색어 수집입니다.** 지정한 키워드의 검색 관심도 시계열 조회와 다릅니다. `approx_traffic_lower_bound`는 RSS가 제공하는 대략적인 구간값의 하한이며 정확한 검색량이 아닙니다. [RSS와 CSV 내보내기 안내](https://support.google.com/trends/answer/3076011?hl=en)
- Indie Hackers·디스콰이엇·GitHub는 HTML 구조 변경에 영향을 받습니다. 항목을 찾지 못하면 성공으로 처리하지 않고 오류를 기록합니다. 공개 목록 다음 페이지의 자동 탐색은 포함하지 않았습니다.
- 댓글은 **개수만** 수집합니다. 댓글 본문과 링크된 원문 기사 전체 본문을 재귀적으로 수집하지 않습니다.
- 소스별 지표·순위는 의미가 다릅니다. HN 점수, PH 투표, GitHub 별을 그대로 합산하지 마세요. Hugging Face 다운로드는 제공자의 기본 집계 기간 값입니다.
- URL 그룹은 동일 URL에 대한 묶음입니다. 같은 제품의 다른 주소, 의미가 같은 글, 재전파와 독립적인 검증을 구분하는 작업은 후속 분석이 필요합니다.
- 수집·정규화·저장 코드이며, 자동 주제 분류·요약 모델·트렌드 점수 계산은 포함하지 않았습니다.

## 코드 구조와 소스 추가

`trend_collector.py`는 CLI, 설정 로딩, 소스 실행과 실패 처리를 담당합니다.
사이트별 수집 코드는 `src/sources/` 아래에서 독립적으로 관리합니다.

```text
trend_collector.py       # 수집 실행 엔드포인트
trend_viewer.py          # 조회 실행 엔드포인트
trend_analyzer.py        # 분석 실행 엔드포인트
src/
  __init__.py
  models.py                # Item, URL·시각 정규화, 공통 예외
  http_client.py           # HTTP 요청, 재시도, 요청 간격, HTML 파싱
  parsing.py               # 공통 HTML/XML 파싱 도구
  security.py              # CVE 식별자 추출
  enrichment.py            # EPSS 보강
  storage.py               # SQLite, JSONL, CSV 저장
  sources/
    __init__.py            # 소스 타입 등록과 DI 조립
    base.py                # Source, HTTPClient, CollectionRequest
    geeknews.py
    hackernews.py
    producthunt.py
    reddit.py
    github.py
    google_trends.py
    indiehackers.py
    disquiet.py
    huggingface.py
    bleepingcomputer.py
    cisa_kev.py
    github_advisories.py
    kisa.py
    security_rss.py         # 보안 RSS 공통 파싱
```

모든 소스는 `name`과 `collect(request: CollectionRequest) -> Iterator[Item]`을
제공합니다. HTTP 클라이언트, 소스별 설정, 인증 정보는 생성자로 주입합니다.
사이트별 인증·페이지 이동·파싱은 소스가 담당하고, 저장은 실행부가 담당합니다.

```python
from src.http_client import HTTP
from src.sources import CollectionRequest, GeekNewsSource, create_sources

http = HTTP({"request_interval": 1})
source = GeekNewsSource(http, config={})
for item in source.collect(CollectionRequest(limit=10)):
    print(item.title)

# 기본 소스를 한 번에 구성합니다. credentials를 생략하면 환경변수를 읽습니다.
# 빈 dict를 주입하면 환경변수의 토큰을 사용하지 않습니다.
sources = create_sources(http, credentials={})
```

`HTTPClient`는 구조적 인터페이스입니다. `get`, `json`, `page`를 구현한 다른
클라이언트나 테스트 대역도 상속 없이 주입할 수 있습니다. 소스 클래스는
환경변수를 직접 읽지 않습니다. 인증 토큰은 `credentials` 매핑으로 전달합니다.

실행부에도 소스를 직접 주입할 수 있습니다. 사용자 정의 소스는 `Source`를
상속할 필요 없이 같은 인터페이스를 구현하면 됩니다.

```python
from trend_collector import main

main(["--out", "data"],
     sources={"geeknews": source})
# 기본 소스를 사용하면서 HTTP 클라이언트만 교체할 수도 있습니다.
main(["--config", "config.toml"], http=http)
```

주입된 소스 매핑의 키는 각 객체의 `name`과 같아야 합니다. `sources`를 주입하면
기본 소스를 생성하지 않습니다. 이때 소스 설정과 인증 정보는 호출자가 객체를
만들 때 전달합니다. EPSS를 설정에서 켠 경우 보강용 HTTP 클라이언트가 필요하며,
`http` 또는 `enricher`를 주입하지 않으면 기본 HTTP 클라이언트를 생성합니다.

새 기본 소스는 `src/sources/<이름>.py`에 `BaseSource`를 상속한 클래스를 만들고
`src/sources/__init__.py`의 `SOURCE_TYPES`에 등록합니다. `SOURCES`는 이 레지스트리에서
생성됩니다. 기본 설정은 `config.toml`의 `[sources.<이름>]`에 추가합니다.
`collect`는 `yield` 또는 `yield from`으로 항목을 반환합니다. 소스별 지표는
`metrics`, 추가 맥락은 `metadata`에 보존합니다. `days`는 호환용으로만 유지합니다.

기존 실행 명령과 출력 형식은 유지됩니다. 기존 함수형 `collect(http, cfg, limit,
days)`와 `trend_collector`의 가져오기도 호환용으로 제공합니다. `COLLECTORS`는
기존 함수형 호출용이며 새 실행부는 `SOURCE_TYPES`로 구성한 객체를 사용합니다.

## 실패 처리와 테스트

한 소스가 실패해도 다른 소스는 계속 수집합니다. 페이지를 읽다가 실패하면 이미 수집한 항목을 `partial` 상태로 저장합니다. `manifest.json`의 상태는 `ok`, `empty`, `skipped`, `partial`, `error`입니다.

소스별 수집은 스레드 풀에서 병렬 실행합니다. 한 소스 내부의 페이지 탐색은 순차적으로
진행하며, 결과 로그는 소스가 완료되는 순서로 출력합니다. 저장할 때는 소스 등록 순서로
결과를 합칩니다. EPSS 보강과 SQLite·파일 저장은 모든 소스 수집이 끝난 뒤 실행합니다.
공통 HTTP 클라이언트는 호스트별로 요청을 직렬화하여 요청 간격과 재시도 대기를 지키고,
서로 다른 호스트의 요청은 동시에 진행합니다. DI로 직접 주입하는 HTTP 클라이언트도
여러 소스가 공유한다면 스레드에서 안전하게 사용할 수 있어야 합니다.

429와 일부 서버 오류는 제한적으로 재시도하고 Retry-After를 따릅니다. 서버가 60초보다 긴 대기를 요구하면 이번 수집을 종료하고 이유를 기록합니다. 401·403은 재시도하지 않습니다.

기본 종료 코드는 한 건 이상 저장하면 0입니다. 전체 실패·빈 결과는 1이며, 자동 실행에서 일부 누락도 실패로 감지하려면 `--strict`를 사용하세요.

```bash
uv run trend_collector.py --config config.toml --strict
uv run --no-project --python 3.12 python -m unittest discover -s tests -v
```

테스트는 DI, 공통 인터페이스와 함께 URL 그룹화와 출처 보존, 관측 이력, CSV 수식 방지, 시각 변환, 피드·HTML 파싱, 403·429 처리, 대상 HTML 직접 요청, 토큰 없는 HTML 수집, 페이지 이동, 부분 실패 후 저장을 검증합니다.

## 확인한 공식 자료

- [GeekNews Atom 피드 안내](https://news.hada.io/blog/geeknews_feed)
- [Hacker News 공식 API](https://github.com/HackerNews/API)
- [Product Hunt 공개 홈페이지](https://www.producthunt.com/)
- [Reddit 공개 목록](https://old.reddit.com/r/SideProject/new/)
- [GitHub Trending](https://github.com/trending)
- [Hugging Face Hub API](https://huggingface.co/docs/hub/api)
