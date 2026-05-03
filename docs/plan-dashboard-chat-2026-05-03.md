# Plan: abysscope 대시보드 OpenWebUI-style 채팅 UI

- date: 2026-05-03
- status: done
- author: claude
- approved-by: user (auto-mode 2026-05-03)
- target-repo: /Users/ash84/workspace/heg/cclaw

## 완료 기록 (2026-05-03)

| 항목 | 결과 |
|---|---|
| Python tests | `uv run pytest` → **943 passed** (회귀 0) |
| Python lint | `uv run ruff check .` → All checks passed |
| Python format | `uv run ruff format` → 모든 파일 정렬됨 |
| Node tests | `npm run test` → 68 passed (vitest, +4 신규 SSE 파서 테스트) |
| Node TS | `npx tsc --noEmit` → 0 errors |
| Node lint | `npm run lint` → 0 errors (기존 sidecar 경고 1건만) |
| Next build | `npm run build` → `/chat` 라우트 정상 등록 |

### 변경 요약

- 신규 모듈: `src/abyss/chat_core.py`, `src/abyss/chat_server.py`
- `src/abyss/session.py` chat_id `int | str` 지원, `collect_web_session_ids()` 추가
- `src/abyss/bot_manager.py` chat_server start/stop 통합 (port 3848)
- `pyproject.toml` aiohttp>=3.9 추가
- 신규 Next 라우트 6개 (`/api/chat`, `/api/chat/{cancel,bots,health,sessions,sessions/[bot]/[id],sessions/[bot]/[id]/messages}`)
- 신규 클라이언트 `src/lib/abyss-api.ts`
- 신규 페이지 `/chat` + 컴포넌트 5종 (chat-view, chat-session-list, chat-message, prompt-input, bot-selector, use-chat-stream)
- sidebar에 💬 Chat 메뉴 추가
- 신규 테스트: `tests/test_chat_core.py` (5건), `tests/test_chat_server.py` (11건), `src/lib/__tests__/abyss-api.test.ts` (4건)

### 원안 대비 변경
- shadcn AI Elements 미설치. 기존 shadcn 프리미티브(Select, Button, Textarea, ScrollArea, Alert) + react-markdown으로 직접 구성. 외부 registry 의존 제거.
- 별도 `abyss api` CLI subcommand 없음. chat_server는 `abyss start`에 embedded.

## 0. 선행 작업 회수 (2026-05-03 추가)

PR #13 (`feat: dashboard chat UI with bidirectional Telegram sync`)가 2026-04-28 main에 머지된 직후 PR #14로 **revert**됨. 사용자 요구("텔레그램 sync 불필요")와 일치 → 이전 시도의 sync가 reverted 사유로 추정. 재사용 가능한 자산:

- **`feat/dashboard-chat-ui` 브랜치의 `src/abyss/chat_server.py`**: aiohttp 서버 스켈레톤, `_sse_write()`, `_run_chat()` 코어 플로우 → 그대로 차용 (단, `event_bus`/`primary_chat_id`/`application.bot.send_message` 동기화 부분 모두 제거)
- **`feat/dashboard-chat-ui:abysscope/src/app/bots/[name]/chat/page.tsx`**: per-bot UI는 폐기. 새 top-level `/chat`로 대체.

### 아키텍처 조정 (sidecar vs embedded)

원안은 별도 `abyss api` daemon이었으나 **embedded(bot_manager 내부)**로 변경. 이유:
- SDK pool / LLMBackend cache (`registry._INSTANCES`)가 동일 프로세스에서 자동 공유 → Telegram + Web 모두 1회 backend 인스턴스화
- 라이프사이클 단순화 (`abyss start` 한 번으로 둘 다 기동)
- 이전 PR #13과 동일한 패턴 → 검증된 통합 위치
- 단점: chat server만 단독 기동 불가 (= `abyss start`로 봇 폴링도 같이 켜야 함). 개인 로컬 도구 가정 하에 수용.

### 새 endpoint set (sync 제거)

```
POST /chat                                     SSE 스트림 응답
POST /chat/cancel                              현재 진행 중 응답 취소
GET  /chat/sessions?bot=<name>                 web 세션 목록
POST /chat/sessions                            새 세션 생성
DELETE /chat/sessions/<bot>/<id>               세션 삭제
GET  /chat/sessions/<bot>/<id>/messages        세션 메시지 목록
GET  /chat/bots                                대시보드용 봇 목록
GET  /healthz
```
이전 PR이 가졌던 `/bots/{name}/stream` (SSE 구독), `/bots/{name}/history` (Telegram history) endpoint는 **삭제**. ChatEventBus, primary_chat_id 코드 경로 모두 제거.

### 세션 ID 정책

`chat_web_<8자 hex uuid>` (예: `chat_web_a3f9b2c1`). 기존 Telegram chat (chat_<int>) 와 prefix로 구분. abysscope 봇 페이지의 세션 목록에서 이 prefix 가진 세션은 별도 그룹으로 표시 또는 그냥 섞어 보여줘도 OK.

## 1. 목적 및 배경

abysscope 대시보드에서 봇과 직접 채팅 가능한 UI 제공. Telegram 없이 브라우저에서 봇 대화 가능 → 데모/디버깅/로컬 사용 흐름 단순화. 기존 abyss `LLMBackend` 인프라(`claude_code` / `openai_compat`) 그대로 재사용. **Telegram sync 없음** — `chat_web_*` prefix 별도 세션 공간.

## 2. 예상 임팩트

| 영역 | 변경 |
|---|---|
| Python (`src/abyss/`) | 신규 모듈 `web_api.py`(aiohttp 서버), `chat_core.py`(handlers.py에서 추출한 비-Telegram 핵심 로직). CLI subcommand `abyss api`. |
| abysscope (Next.js) | 신규 페이지 `/chat`, 신규 API 라우트 4개, 신규 컴포넌트. shadcn AI Elements 의존성 추가. |
| 데이터 | `~/.abyss/bots/<name>/sessions/chat_web_<uuid>/` 세션 생성. 기존 Telegram 세션과 분리. |
| 성능 | sidecar 서버 추가 → 메모리 +50MB 추정. SDK pool 재사용으로 메시지당 응답 1-2초 단축. |
| 사용자 경험 | 대시보드 사이드바 최상단에 'Chat' 메뉴 추가. |

## 3. 구현 방법 비교 (사용자 확정 사항)

### 3.1 UI 진입: top-level `/chat` (OpenWebUI 스타일) ✅
- 사이드바 'Chat' → 대화 목록 좌측 패널, 봇 셀렉터 드롭다운, 메시지 스레드 중앙
- 대안(per-bot 탭) 기각: 여러 봇과 빠르게 전환하려면 단일 페이지가 자연스러움

### 3.2 Python ↔ Node 브리지: Python sidecar HTTP ✅
- aiohttp 서버 `127.0.0.1:${ABYSS_API_PORT:-3848}` 바인드 (loopback only, 외부 접근 불가)
- `SDKClientPool` 재사용 → 매 요청마다 Python cold start 회피
- 대안(subprocess spawn) 기각: SDK pool 활용 불가, 응답 1-2초 추가 지연

### 3.3 UI 컴포넌트: shadcn AI Elements ✅
- `npx shadcn@latest add @ai-elements/conversation @ai-elements/message @ai-elements/prompt-input @ai-elements/response`
- 이미 `shadcn@4.0.5`, `react-markdown@10`, Tailwind 4 설치됨 → 호환성 OK
- AI Elements는 자체 `useChat` 훅 미강제. Vercel AI SDK 없이 SSE 직접 핸들링 가능.

## 4. 구현 단계

### Phase A — Python sidecar (`abyss api`)

- [ ] **A1.** `src/abyss/chat_core.py` 신설. `handlers.py`에서 비-Telegram 로직 추출:
  - `process_chat_message(bot_name, chat_id, user_message, on_chunk) -> str`
  - 내부: `ensure_session` → `log_conversation(user)` → `_prepare_session_context` → `get_or_create(bot_name, bot_config)` → `backend.run_streaming` → `log_conversation(assistant)` → return text
  - 기존 `handlers.py`는 `chat_core` 호출하도록 리팩터 (Telegram-specific wrap만 남김)
- [ ] **A2.** `session.py` `ensure_session`/`session_directory`가 `chat_id: int | str` 받도록 시그니처 확장 (기존 int 호환). `chat_id`가 str이면 그대로 디렉토리명으로 사용. 영향: 기존 호출부 모두 int 전달 → 무영향.
- [ ] **A3.** `src/abyss/web_api.py` 신설 (aiohttp). 의존성 `aiohttp` 추가 (pyproject.toml).
  - `POST /chat` (body: `{bot, session_id, message}`) → `text/event-stream`. 이벤트: `data: {"type":"chunk","text":"..."}`, `data: {"type":"done","tokens":{...}}`, `data: {"type":"error","message":"..."}`.
  - `POST /chat/cancel` (body: `{bot, session_id}`) → `backend.cancel(session_key)` 호출.
  - `GET /chat/sessions?bot=<name>` → `chat_web_*` 세션만 필터. 각 세션의 latest message preview + timestamp.
  - `POST /chat/sessions` (body: `{bot, title?}`) → 신규 `chat_web_<uuid>` 생성, 세션 ID 반환.
  - `DELETE /chat/sessions/<bot>/<session_id>` → 세션 디렉토리 삭제.
  - `GET /chat/sessions/<bot>/<session_id>/messages` → 해당 세션의 conversation-*.md 모두 파싱해서 메시지 배열 반환.
  - `GET /healthz` → 200.
  - 모든 엔드포인트 loopback 바인드 + `Origin` 검증 (localhost:3847만 허용).
- [ ] **A4.** `cli.py`에 `abyss api` subcommand: `start [--port] [--daemon]`, `stop`, `status`. PID 파일 `~/.abyss/abyss-api.pid`.
- [ ] **A5.** `bot_manager.py` (또는 `dashboard` 명령) 시작 시 `abyss api` 자동 기동 옵션. 기본은 명시 시작. `abyss start --with-api`, `abyss dashboard start --with-api` 플래그 추가.
- [ ] **A6.** Shutdown 시 `close_pool()` + `close_all()` 호출하여 SDK pool/HTTPX client 정리.

### Phase B — abysscope API 라우트

- [ ] **B1.** `abysscope/src/lib/abyss-api.ts` 신설. Python sidecar 클라이언트:
  - `getApiBase()` → `process.env.ABYSS_API_URL ?? "http://127.0.0.1:3848"`
  - `createChatSession(bot, title?)`, `listChatSessions(bot)`, `deleteChatSession(bot, id)`, `getChatMessages(bot, id)`
  - `streamChat(bot, id, message)` → `ReadableStream<ChatEvent>`
  - `cancelChat(bot, id)`
- [ ] **B2.** API 라우트 신설:
  - `src/app/api/chat/route.ts` POST → Python `/chat`로 SSE 프록시 (`Response(readable, {headers: {"content-type":"text/event-stream"}})`)
  - `src/app/api/chat/cancel/route.ts` POST → 프록시
  - `src/app/api/chat/sessions/route.ts` GET/POST → 프록시
  - `src/app/api/chat/sessions/[bot]/[id]/route.ts` DELETE / GET messages → 프록시

### Phase C — 채팅 페이지 UI

- [ ] **C1.** shadcn AI Elements 설치: `cd abysscope && npx shadcn@latest add @ai-elements/conversation @ai-elements/message @ai-elements/prompt-input @ai-elements/response`. 자동 생성되는 컴포넌트는 `src/components/ui/`에 들어감.
- [ ] **C2.** `src/app/chat/page.tsx` (server) — 봇 목록 SSR로 가져와 클라이언트 컴포넌트에 props 전달.
- [ ] **C3.** `src/app/chat/chat-view.tsx` (client) — 메인 레이아웃:
  - 좌측 280px: `<ChatSessionList>` — 세션 검색, 세션별 카드(봇 아바타 + 마지막 메시지 + 시간), 'New chat' 버튼
  - 상단 바: 현재 세션의 봇 표시. New chat 모드에서는 `<BotSelector>` 드롭다운 (검색 가능).
  - 중앙: `<Conversation>` (AI Elements) 안에 `<Message>` 반복. 사용자/봇 메시지 구분, 봇 메시지는 `<Response>`로 streaming markdown 렌더.
  - 하단: `<PromptInput>` (multi-line, Enter=send, Shift+Enter=newline). 'Stop' 버튼으로 cancel.
- [ ] **C4.** `src/components/chat/bot-selector.tsx` — Combobox(shadcn) 기반. 봇 아바타 + 이름.
- [ ] **C5.** `src/components/chat/chat-session-list.tsx` — 세션 목록 + 삭제 컨텍스트 메뉴 + 검색.
- [ ] **C6.** `src/components/chat/use-chat-stream.ts` — 자체 훅. `fetch('/api/chat', {body, method:'POST'})` → ReadableStream → SSE 파싱 → 토큰 누적/AbortController로 cancel.
- [ ] **C7.** `src/components/sidebar.tsx`에 'Chat' 최상단 메뉴 추가 (Dashboard 위 또는 직후). `MessageSquare` 아이콘.

### Phase D — 페이지 로드/시작 흐름

- [ ] **D1.** Chat 페이지 진입 시 클라이언트가 `/healthz` ping. 503이면 'Chat server not running. Run `abyss api start`' 안내 카드 표시.
- [ ] **D2.** sidebar에 sidecar 상태 표시 (선택). 기존 `<LiveStatus>` 패턴 재사용.

## 5. 테스트 계획

### 단위 테스트 (Python — pytest)
- [ ] `tests/test_chat_core.py`: `process_chat_message()` 호출 → mock backend 사용해 chunk on_chunk 호출 검증, conversation-*.md 파일에 user/assistant 두 줄 append 확인
- [ ] `tests/test_chat_core.py`: 신규 세션 생성 시 CLAUDE.md 복사 확인
- [ ] `tests/test_chat_core.py`: `chat_id="chat_web_xxx"` 문자열 ID 정상 동작 확인
- [ ] `tests/test_web_api.py`: aiohttp test client로 `/chat` SSE 시나리오 (chunk → done event), `/chat/sessions` CRUD, cancel
- [ ] `tests/test_web_api.py`: Origin 검증 — `http://example.com` 거부, `http://127.0.0.1:3847` 허용
- [ ] `tests/test_web_api.py`: 존재 안 하는 봇/세션 → 404
- [ ] `tests/test_session.py`: `ensure_session(bot_path, "chat_web_xyz")` 디렉토리 생성 확인 (기존 int 케이스 그대로 통과)

### 단위 테스트 (Node — vitest)
- [ ] `src/lib/__tests__/abyss-api.test.ts`: `streamChat` SSE 파서가 chunk/done/error 이벤트 분리하는지 확인 (mock fetch)
- [ ] `src/components/chat/__tests__/use-chat-stream.test.tsx`: AbortController로 중단 시 onChunk 호출 멈추는지

### 통합 테스트
- [ ] `abyss api start --port 3848` → curl `POST /chat` → SSE 응답 정상
- [ ] 대시보드 `/chat` 진입 → New chat → 봇 선택 → 메시지 입력 → 스트리밍 표시 → 새로고침 후 메시지 유지 확인
- [ ] `/cancel` 버튼: 응답 도중 중단 시 다음 메시지 정상 동작
- [ ] 같은 세션을 두 탭에서 열고 동시 메시지 → asyncio.Lock으로 직렬화되는지
- [ ] Telegram 봇 동시 동작 중에도 web 채팅이 backend cache 공유 (registry `_INSTANCES`)
- [ ] `claude_code` 봇 + `openai_compat` 봇 모두 정상 스트리밍

### 엣지 케이스
- [ ] sidecar 미기동 상태에서 `/chat` 페이지 진입 → 안내 표시
- [ ] 메시지 송신 중 sidecar 죽으면 클라이언트가 error 이벤트 수신 + 재시도 안내
- [ ] 매우 긴 응답(10K+ 토큰) 스트리밍 중단 없이 완료
- [ ] 한국어/이모지/코드블록 정상 렌더 (`react-markdown` + `react-markdown` 코드 하이라이트)
- [ ] 세션 50+ 개일 때 목록 스크롤/검색 성능

## 6. 사이드 이펙트

| 항목 | 영향 | 대응 |
|---|---|---|
| `handlers.py` 리팩터 | Telegram 흐름이 chat_core로 위임 | 기존 동작 동일 보장하는 회귀 테스트 (`test_handlers.py` 그대로 통과) |
| `session.py` chat_id 타입 확장 | 기존 호출부 영향 없음 (int 그대로 호환) | 타입 hint만 `int | str`, 디렉토리 이름 표현만 변경 |
| 새 의존성 `aiohttp` (Python) | wheel 크기 +~5MB | 이미 httpx 의존성 있음. aiohttp는 sidecar 한 곳만 사용. 또는 `starlette`+`uvicorn`도 검토 가능 (구현 단계에서 결정) |
| 새 디펜던시 (Node) shadcn AI Elements | 컴포넌트 코드만 추가, 런타임 의존 거의 없음 | 빌드 사이즈 영향 미미 |
| 기존 Telegram 채팅과 별도 세션 | `getBotSessions()` UI에 web 세션 섞여 표시될 수 있음 | abysscope 봇 세션 목록에서 `chat_web_*` 표기/필터 추가 (선택사항) |
| 하위 호환성 | 기존 봇 동작 변경 없음, dashboard만 신규 메뉴 | sidecar 미기동 시 Chat 메뉴는 graceful degrade |
| 마이그레이션 | 없음 (신규 디렉토리만 생성) | — |

## 7. 보안 검토

- **A01:2021 Broken Access Control**: sidecar는 `127.0.0.1` loopback만 바인드. 외부 네트워크 노출 금지. 다중 사용자 macOS 환경 가정하지 않음(개인 로컬).
- **A03:2021 Injection**: `bot_name`/`session_id` 정규식 화이트리스트 검증(`^[a-zA-Z0-9_-]+$`, `^chat_web_[a-f0-9-]+$`). 경로 traversal 차단(`../` 거부, 결과 경로가 `~/.abyss/` 하위인지 `is_relative_to()` 검증).
- **A05 Security Misconfiguration**: aiohttp CORS는 `http://127.0.0.1:3847` / `http://localhost:3847`만 허용. 그 외 Origin 헤더 거부.
- **A07 Auth**: 단일 사용자 로컬 환경 가정 → 별도 인증 없음. 단, `ABYSS_API_TOKEN` 환경변수가 설정되면 `Authorization: Bearer` 검증 (옵션, 기본 off).
- **CSRF**: SSE는 GET이 아니라 POST + JSON body. SameSite 쿠키 미사용(상태 없음). Origin 검증으로 충분.
- **민감 데이터**: 봇 토큰은 sidecar가 file system 읽을 때만 접근. 응답 페이로드에 포함 금지(이미 abysscope 다른 라우트도 동일 정책).
- **PCI-DSS**: 해당 없음(결제 데이터 없음).
- **DoS**: 동일 세션의 동시 메시지는 기존 `asyncio.Lock`으로 직렬화. 봇별 메시지 길이 제한 (기본 32KB) 추가.
- **Workspace 격리**: 기존 abyss 정책 그대로 (세션 workspace/ 하위만 쓰기). 별도 검토 불필요.

## 8. 핵심 재사용 함수/모듈

| 무엇 | 위치 |
|---|---|
| `LLMBackend.run_streaming` | `src/abyss/llm/base.py:84` |
| `get_or_create()` | `src/abyss/llm/registry.py:42` |
| `make_request()` | `src/abyss/llm/base.py:132` |
| `ensure_session()` | `src/abyss/session.py:46` |
| `log_conversation()` | `src/abyss/session.py:225` |
| `compose_claude_md()` | `src/abyss/skill.py:392` |
| `_prepare_session_context()` | `src/abyss/handlers.py:661` (chat_core로 추출) |
| `_call_with_resume_fallback()` | `src/abyss/handlers.py:700` (chat_core로 추출) |
| `getBotPath` 유사 헬퍼 (TS) | `abysscope/src/lib/abyss.ts` (private; chat에서는 sidecar 통해 우회) |
| 기존 `<LiveStatus>` 컴포넌트 | `abysscope/src/components/live-status.tsx` (sidecar 헬스 표시 재사용) |
| 기존 subprocess spawn 패턴 | `abysscope/src/lib/conversation-search.ts:155` (참고용; 이번엔 HTTP 사용) |

## 9. 검증 (End-to-End)

```bash
# 1. Python 측
cd /Users/ash84/workspace/heg/cclaw
make lint && make test
uv run abyss api start --port 3848
curl -N -X POST http://127.0.0.1:3848/chat \
  -H "content-type: application/json" \
  -H "origin: http://127.0.0.1:3847" \
  -d '{"bot":"<test-bot>","session_id":"chat_web_test","message":"hello"}'
# → SSE chunk 이벤트가 흘러야 함

# 2. abysscope 측
cd abysscope
npm run lint && npm run test
npm run dev  # http://localhost:3000 또는 3847
# 브라우저 → /chat → New chat → 봇 선택 → 메시지 송수신 확인
```

## 10. 완료 조건

- [ ] 4번 모든 체크 박스 100%
- [ ] 5번 단위/통합/엣지 100%
- [ ] `make lint && make test` (Python), `npm run lint && npm run test` (Node) 통과
- [ ] 6번 사이드 이펙트 모두 "대응 완료"
- [ ] sidecar 자동 기동 안내 문서 (`README.md` 또는 `docs/CHAT.md`) 1매 작성
- [ ] plan 상단 `status: done` + `docs/plan-dashboard-chat-2026-05-03.md`로 이동

## 11. 중단 기준

- aiohttp 도입 시 wheel 빌드/배포 충돌 발견 → starlette+uvicorn으로 변경 plan 수정
- shadcn AI Elements가 React 19 / Tailwind 4와 호환 문제 발견 → headless + 자체 컴포넌트로 plan 수정
- SDK pool이 다중 세션 동시 사용 시 race 발견 → 세션별 직렬화 강화 또는 풀 재설계, plan 재검토
- handlers.py 리팩터가 기존 회귀 테스트를 깨면 → 즉시 중단, 리팩터 범위 축소(추출 대신 chat_core가 handlers의 함수를 호출만 하는 방식)
