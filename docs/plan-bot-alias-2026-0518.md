# Plan: 봇별 alias (역할 라벨) 필드 추가

- date: 2026-05-18
- status: approved
- author: claude
- approved-by: ash84

## Context

봇이 11개로 늘면서 캐릭터 이름(`display_name`: "앤", "킴", "엘리"
…)만 보고 어떤 역할의 봇인지 즉시 구분이 어렵다. 사용자 요청:
"앤(집사)" 처럼 역할 라벨을 함께 노출. 필수값은 아니므로 alias 가
없는 봇은 기존과 동일하게 `display_name` 만 보인다.

## 1. 목적 및 배경

- 사용자가 11개 봇을 빠르게 식별. 캐릭터 이름은 정체성, alias 는
  역할/용도 — 이 둘을 함께 노출
- 새 봇 추가 시 alias 를 비워두면 기존 UI 와 동일하게 동작 (옵셔널)
- 기존 `display_name` / 봇 슬러그(`name`) 의미는 그대로 유지 —
  alias 는 단순 표시용 메타데이터

## 2. 예상 임팩트

- 영향 모듈
  - 백엔드
    - `src/abyss/onboarding.py` — `abyss bot add` 단계에서 alias
      입력 옵션 (스킵 가능)
    - `src/abyss/chat_server.py` — `BotSummary` / `_session_metadata`
      / `_routine_metadata` 응답에 `alias` 필드 추가, bot create
      엔드포인트가 `alias` 받기
    - `src/abyss/config.py` — bot.yaml 스키마는 free-form dict 이라
      별도 변경 불필요. helper 한 줄 (`get_bot_alias()`) 정도면 충분
  - 프론트엔드
    - `abysscope/src/lib/abyss-api.ts` — `BotSummary`,
      `ChatSession`, `RoutineSummary` 타입에 `alias?: string | null`
      추가. 신규 helper `formatBotLabel({ display_name, alias })`
    - 표시 surface (모두 helper 호출로 전환):
      - `components/sidebar.tsx` — 사이드바 봇 리스트
      - `components/bot-avatar.tsx` — tooltip / aria-label
      - `components/mobile/sessions-drawer-panel.tsx` — 채팅/루틴
        리스트 행, 신규 채팅 picker
      - `components/mobile/mobile-chat-screen.tsx` — 헤더
      - `components/mobile/mobile-routine-screen.tsx` — 헤더
      - `app/bots/[name]/edit/page.tsx` — alias 입력 필드 (신규)
      - `app/bots/[name]/page.tsx` — 상세 페이지 헤더
      - `components/bots/new-bot-form.tsx` — 신규 봇 생성 폼
- 성능: 영향 없음 (string 1개 추가)
- 가용성: alias 없을 때 fallback = `display_name` (기존 동작)
- UX: alias 가 있으면 모든 라벨에 `"<display_name> (<alias>)"` 노출.
  공백 1칸 + 한국어 괄호 표기 — "앤 (집사)"

## 3. 구현 방법 비교

### 방법 A — alias 필드를 별도 API 필드로 노출, 프론트가 포맷팅 (선택)

- 저장: bot.yaml top-level `alias: 집사`
- API: 응답에 `alias` 그대로 포함
- 프론트: `formatBotLabel({display_name, alias})` 유틸이 `"앤 (집사)"`
  포맷 결정. 향후 포맷 변경 (예: alias 만 작은 글씨로 분리 렌더)
  시 유틸 한 곳만 수정
- 장점: 백엔드는 멍청한 통로, 표현은 프론트가 통제. UI 별 조판
  자유도 (예: alias 만 muted 색상 + 더 작은 폰트). 검색/필터에도
  raw 필드 그대로 활용 가능
- 단점: 모든 surface 에서 helper 호출하도록 일관성 강제 필요

### 방법 B — 백엔드가 "Display (alias)" 문자열 합성해서 내려보냄

- API: `display_name = "앤 (집사)"` 로 미리 합쳐 응답
- 장점: 프론트 수정 surface 최소 (1곳도 안 바꿔도 됨)
- 단점:
  - 문자열에서 alias 만 다시 분리 불가 → 검색/필터 시 raw 값 잃음
  - "alias 만 회색으로" 같은 시각 분리 불가능
  - `display_name` 의 의미가 흐려져 다른 로직 (메모리, 시스템
    프롬프트) 에서 누가 무엇을 사용할지 혼란

### 선택: 방법 A

데이터는 의미 단위로 분리해 보내고 표현은 프론트가 결정하는 게
유연하고 일관성이 강하다. helper 하나로 surface 전체를 한꺼번에
바꿀 수 있어 변경 범위가 깔끔하다.

## 4. 구현 단계

### 백엔드

- [ ] Step 1: `_bot_display_name` 옆에 `_bot_alias(bot_name) -> str
      | None` helper 추가 (bot.yaml `alias` 필드 읽기, 빈문자열은
      None 으로 정규화). 길이 검증: 1-30 chars, 양쪽 trim
- [ ] Step 2: `_handle_list_bots` 응답에 `alias` 추가
- [ ] Step 3: `_session_metadata` / `_routine_metadata` 응답에
      `bot_alias` 필드 추가 (드로어 리스트에서 fetch 1회로 라벨링
      완성)
- [ ] Step 4: `_handle_create_bot` body schema 에 optional `alias`
      허용, sanitize 후 저장
- [ ] Step 5: `onboarding.py` `abyss bot add` 대화형 흐름에 alias
      질문 1개 추가 (Enter 스킵 시 None)

### 프론트엔드 타입 + helper

- [ ] Step 6: `lib/abyss-api.ts`
  - `BotSummary` 에 `alias?: string | null`
  - `ChatSession`, `RoutineSummary` 에 `bot_alias?: string | null`
  - 신규 export `formatBotLabel({ display_name, alias })`:
    alias 없으면 display_name 그대로, 있으면 `"앤 (집사)"`

### UI 적용

- [ ] Step 7: `components/sidebar.tsx` — `formatBotLabel` 사용
- [ ] Step 8: `components/bot-avatar.tsx` — aria-label / title 에
      alias 포함
- [ ] Step 9: `mobile/sessions-drawer-panel.tsx` — 채팅 picker /
      Routines 행 / Chats 행 모두 helper 적용. 단, custom_name
      이 있는 세션은 custom_name 그대로 유지 (사용자 라벨 우선)
- [ ] Step 10: `mobile/mobile-chat-screen.tsx` 헤더 + 신규 채팅
      picker (sessions-drawer 와 동일 유틸)
- [ ] Step 11: `mobile/mobile-routine-screen.tsx` 헤더 (`{bot}` 옆에
      alias)
- [ ] Step 12: `app/bots/[name]/page.tsx` 상세 헤더에 alias 노출
- [ ] Step 13: `app/bots/[name]/edit/page.tsx` — alias text input
      필드 (선택 입력) + 저장 시 PUT body 에 포함
- [ ] Step 14: `components/bots/new-bot-form.tsx` — alias text input
      추가, 빈 값이면 omit

## 5. 테스트 계획

### 단위 테스트 (pytest)

- [ ] 케이스 1: bot.yaml 에 `alias: 집사` 있을 때 `/chat/bots` 응답이
      `alias: "집사"` 포함
- [ ] 케이스 2: alias 미설정 / 빈문자열 → 응답에서 `alias: null`
- [ ] 케이스 3: `_session_metadata` / `_routine_metadata` 가
      `bot_alias` 동일 규칙으로 반영
- [ ] 케이스 4: `POST /chat/bots` 가 `alias` 받아 bot.yaml 에 저장,
      후속 조회에서 노출
- [ ] 케이스 5: alias 길이 31자 초과 / 제어문자 포함 → 400
- [ ] 케이스 6: alias 가 양쪽 공백만 → None 으로 정규화

### 단위 테스트 (vitest)

- [ ] 케이스 7: `formatBotLabel({ display_name: "앤", alias: "집사" })`
      → `"앤 (집사)"`
- [ ] 케이스 8: `formatBotLabel({ display_name: "앤", alias: null })`
      → `"앤"`
- [ ] 케이스 9: `formatBotLabel({ display_name: "앤",
      alias: "  " })` → `"앤"` (whitespace-only 도 무시)

### 통합 테스트

- [ ] 시나리오 1: 봇 1개에 alias 설정 후 데스크탑 사이드바, 모바일
      드로어 양쪽에서 `"<name> (<alias>)"` 형식으로 보임
- [ ] 시나리오 2: 다른 봇은 alias 없이 기존과 동일하게 보임 — 회귀
      없음
- [ ] 시나리오 3: edit page 에서 alias 입력 → 저장 → 사이드바 즉시
      반영

## 6. 사이드 이펙트

- bot.yaml 에 신규 키 추가 — 기존 yaml 파서 (yaml.safe_load) 가
  자동 인식. 마이그레이션 불필요
- helper 도입으로 라벨링이 일관됨. 추후 (예: 봇 검색 기능) alias
  를 검색 대상에 포함하기 쉬워짐
- helper 도입으로 라벨링 일관성 유지. **두 가지 surface 는 의도적
  으로 alias 를 제외** (사용자 결정):
  - 채팅 메시지 버블 안 author 라벨 — 매 메시지마다 alias 가 붙으면
    노이즈
  - Web Push 알림 title — iOS truncate 위험 (`⏰ {display_name}:
    {job}` 형식 유지). cron / heartbeat / chat 푸시 모두 동일
- 위 두 surface 는 `formatBotLabel` 호출하지 않고 `display_name` 만
  사용. 회귀 방지를 위해 메시지 버블 + push 빌더 코드에 주석 명시

## 7. 보안 검토

- OWASP A03 (Injection): alias 는 UI 텍스트로만 사용 — React 가
  자동 escape. yaml 저장 시 `yaml.safe_dump` 사용 (기존 패턴)
- OWASP A04 (Insecure Design): alias 는 PII / 인증 정보가 아님.
  bot.yaml 은 이미 personality / role 같은 자유 텍스트를 담고 있어
  추가 위험 없음
- 입력 검증: 길이 30자, 제어문자 stripping. 기존
  `_sanitise_custom_name` 패턴 재사용 가능 → `_sanitise_bot_alias`
  로 분리 (cap 만 다름)
- 권한: bot create / edit 엔드포인트는 이미 chat_server 가 loopback
  + Origin allowlist 로 보호. 새 endpoint 추가 없음
- PCI-DSS: 영향 없음