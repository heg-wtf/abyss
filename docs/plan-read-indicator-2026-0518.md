# Plan: Chats / Routines 읽음·안읽음 표시

- date: 2026-05-18
- status: approved
- author: claude
- approved-by: ash84

## Context

현재 모바일 PWA의 `SessionsDrawerPanel` (Chats + Routines 탭) 및 채팅
상세 (`MobileChatScreen`, `MobileRoutineScreen`) 는 새 메시지가
도착해도 어떤 세션/루틴에 새 메시지가 있는지 시각적으로 구분되지
않는다. cron / heartbeat 결과는 Web Push 로만 알 수 있고, 사용자는
드로어를 열어도 어느 행이 미확인인지 모른다.

서버측 세션 메타는 `<session_dir>/.session_meta.json` (현재 필드:
`custom_name`) 이 이미 존재하고, 동일 패턴을 routine 세션 디렉터리
(`cron_sessions/<job>/`, `heartbeat_sessions/`) 에 그대로 확장
가능하다. 미확인/확인 상태는 `last_read_at` (ISO8601) 1개 필드로
충분히 표현된다 — 단일 유저 환경이라 unread count 가 아닌 boolean
판정만 필요하기 때문이다.

## 1. 목적 및 배경

- 목록(Chats / Routines 탭)에서 새 메시지가 도착한 행을 즉시 식별
  가능해야 함 — bold 텍스트 + 좌측 unread dot 패턴 (iMessage / Slack
  모바일과 동일)
- 채팅 상세 진입 시 자동으로 "읽음" 처리되고, 안읽었던 메시지가
  여러 건이면 첫 unread 위에 "여기까지 읽음" divider 1줄을 표시해
  맥락 단절 없이 빠르게 새 메시지로 점프 가능
- cron / heartbeat (Routines) 도 동일 모델로 처리해 PWA Web Push
  알림과 시각적 일관성 유지

## 2. 예상 임팩트

- 영향 모듈
  - 백엔드: `src/abyss/chat_server.py` (세션·루틴 메타 read API,
    list 응답에 `last_read_at` / `unread` 필드 추가)
  - 프론트엔드:
    - `abysscope/src/lib/abyss-api.ts` — `ChatSession`,
      `RoutineSummary` 타입 확장 + `markSessionRead`,
      `markRoutineRead` helper
    - `abysscope/src/components/mobile/sessions-drawer-panel.tsx`
      — unread dot + bold 적용
    - `abysscope/src/components/mobile/mobile-chat-screen.tsx`,
      `mobile-routine-screen.tsx` — mount 시 read API 호출,
      unread divider 렌더
    - `abysscope/src/app/api/chat/sessions/[bot]/[id]/read/route.ts`
      (신규), `.../routines/[bot]/[kind]/[job]/read/route.ts` (신규)
- 성능: 목록 fetch 비용 변화 없음 (메타 파일 1회 read 추가, 이미
  `_load_session_meta` 호출 중). read API 는 mount 당 1회 POST 로
  무시 가능
- 가용성: 메타 파일 corrupt / 부재 시 `last_read_at=null` 로
  fallback. 기존 세션 (메타 없음) 은 "전부 unread" 가 아니라
  "전부 read" 로 간주 (마이그레이션 1회). 그렇지 않으면 첫
  배포 직후 모든 세션이 bold 가 됨
- 사용자 경험: PWA 의 `navigator.setAppBadge` 와 추후 연동 가능
  (이번 plan 범위는 in-app 표시까지)

## 3. 구현 방법 비교

### 방법 A — 세션 디렉터리별 메타 파일 확장 (선택)

- 저장: `<session_dir>/.session_meta.json` 에 `last_read_at` 필드
  추가. Routine 도 동일 파일명을 routine session dir 에 신규 적용
- 판정: `unread = updated_at > last_read_at` (서버에서 계산해
  `unread: boolean` 으로 응답에 포함)
- 장점:
  - 기존 `_load_session_meta` / `_save_session_meta` 인프라
    그대로 활용
  - 세션 삭제 시 메타도 함께 사라짐 (race-free)
  - Atomic write (`tmp + rename`) 이미 구현됨
- 단점:
  - Routine 디렉터리에 hidden file 1개 추가 — git ignore 대상이
    아니지만 `~/.abyss/` 는 runtime data 라 영향 없음

### 방법 B — 중앙 집중형 read_state.json

- 저장: `~/.abyss/read_state.json` 단일 파일에
  `{"sessions": {...}, "routines": {...}}` 로 통합
- 장점: 한 파일로 backup / 동기화 단순. 마이그레이션 없이 신규 키만
  추가됨
- 단점:
  - 세션 삭제 시 stale 엔트리 잔존 — cleanup 로직 별도 필요
  - 동시 쓰기 시 lock 필요 (chat / cron / heartbeat 동시 mark
    가능). 현 `_save_session_meta` 는 디렉터리 격리로 충돌 없음
  - 파일 비대화 시 read I/O 증가
- 결론: 격리성과 코드 재사용 측면에서 방법 A 가 우위

### 선택: 방법 A

이유: 기존 `.session_meta.json` 패턴을 그대로 routine 에 확장하면
백엔드 추가 코드가 최소화되고, 디렉터리 격리로 동시성·삭제 race 가
자연스럽게 해결된다.

## 4. 구현 단계

### 백엔드 (`src/abyss/chat_server.py`)

- [ ] Step 1: `_session_metadata` 가 `last_read_at` 와 `unread`
      (계산값) 을 응답에 포함하도록 수정. `unread` 계산은
      `last_read_at is None or updated_at > last_read_at`. 단,
      "기존 세션은 전부 read" 정책을 위해 `last_read_at` 부재 시
      `unread=False` 로 응답 (마이그레이션 비용 0)
- [ ] Step 2: `_routine_metadata` 동일 확장. routine dir 에도
      `_load_session_meta` 적용 (현재 routine 은 메타 미로딩)
- [ ] Step 3: 신규 핸들러 `_handle_mark_session_read` +
      라우트 `POST /chat/sessions/{bot}/{session_id}/read`. body 없음,
      서버가 `last_read_at = now (UTC ISO)` 로 기록
- [ ] Step 4: 신규 핸들러 `_handle_mark_routine_read` +
      라우트 `POST /chat/routines/{bot}/{kind}/{job_name}/read`
- [ ] Step 5: `log_conversation` 호출 직후 (또는 `_handle_chat` SSE
      `done` 직후) 자동으로 active 세션의 `last_read_at` 을
      업데이트하는 hook은 **추가하지 않음** — 클라이언트가 detail
      mount 시 명시적으로 mark 한다 (idempotent, 단순함)

### 프론트엔드 타입 + helper (`abysscope/src/lib/abyss-api.ts`)

- [ ] Step 6: `ChatSession` 에 `last_read_at?: string | null`,
      `unread?: boolean` 추가
- [ ] Step 7: `RoutineSummary` 에 동일 필드 추가
- [ ] Step 8: `markSessionRead(bot, sessionId)`,
      `markRoutineRead(bot, kind, jobName)` helper 추가 — `POST`
      날리고 결과 무시 (best-effort)

### Next.js API proxy

- [ ] Step 9: `abysscope/src/app/api/chat/sessions/[bot]/[id]/read/route.ts`
      신규 — sidecar 의 동일 경로로 forward
- [ ] Step 10: `abysscope/src/app/api/chat/routines/[bot]/[kind]/[job]/read/route.ts`
      신규

### 목록 UI (`sessions-drawer-panel.tsx`)

- [ ] Step 11: 세션 / routine row 렌더 시 `sess.unread` 가
      `true` 면 좌측에 emerald dot (기존 streaming dot 자리와 별도,
      streaming dot 우선 표시) + label / preview 를
      `font-semibold` / `text-foreground` 강조
- [ ] Step 12: 행 클릭 → 라우팅 직전에 로컬 state 의 `unread`
      를 즉시 false 로 낙관적 업데이트 (서버 mark 는 detail mount
      시 수행)

### 상세 UI

- [ ] Step 13: `MobileChatScreen` mount 시
      `markSessionRead(bot, sessionId)` 호출. 초기 메시지 배열에서
      마지막 read 이후 첫 assistant 메시지를 찾아 그 앞에
      `<UnreadDivider />` 컴포넌트 삽입 ("여기까지 읽음" 좌우
      hairline + 라벨)
- [ ] Step 14: `MobileRoutineScreen` mount 시
      `markRoutineRead(bot, kind, job_name)` 호출 + 동일 divider
      렌더
- [ ] Step 15: 이미 상세 화면에 머무는 동안 SSE `done` 으로 새
      메시지가 들어오면 divider 추가 없이 즉시 read 처리 (mount-
       시 1회만 divider, 이후는 실시간 → 자동 read)

### Web Push 연동

- [ ] Step 16: `web_push.PushPayload` 에 `kind?: "chat" | "cron" |
      "heartbeat"`, `job_name?: string` 필드 추가. `send_push`
      시그니처에도 동일 인자 추가 (default None)
- [ ] Step 17: `cron.py` / `heartbeat.py` 의 `_send_push` 호출에
      `kind="cron"|"heartbeat"`, `job_name=<job>` 전달
- [ ] Step 18: `sw.js` `push` 핸들러에서 routine 일 때 `tag` 를
      `routine:<bot>:<kind>:<job>` 로 분기, `notificationclick` 에서
      `/mobile/routine/<bot>/<kind>/<job>` 로 라우팅
- [ ] Step 19: `markSessionRead` / `markRoutineRead` 성공 후
      `navigator.serviceWorker.controller?.postMessage({type:
      "dismiss-notification", tag})` 호출. `sw.js` 에 신규 handler
      추가 — `getNotifications({tag})` 로 해당 tag 알림만 close
      (기존 visibility 기반 전체 clear 와 별도)
- [ ] Step 20: `useWebPush` 훅 (또는 `MobileShell`) 에서
      `/chat/sessions` + `/chat/routines` 응답의 `unread:true`
      개수 합산 후 `navigator.setAppBadge(count)` 호출. iOS PWA
      16.4+ 만 지원되므로 `'setAppBadge' in navigator` 가드.
      세션/루틴 read mark 후 즉시 다시 호출해 badge 감소

## 5. 테스트 계획

### 단위 테스트 (pytest)

- [ ] 케이스 1: `_session_metadata` — meta 없을 때 `unread=False`
- [ ] 케이스 2: `_session_metadata` — `last_read_at < updated_at`
      이면 `unread=True`, `>=` 면 `False`
- [ ] 케이스 3: `_routine_metadata` 동일 동작
- [ ] 케이스 4: `_handle_mark_session_read` 호출 후 meta 파일에
      `last_read_at` 기록 + 후속 list 응답 `unread=False`
- [ ] 케이스 5: invalid bot / session id → 400/404 (path
      traversal 가드)
- [ ] 케이스 6: corrupt `.session_meta.json` → fallback 동작
      (`unread=False`, mark 시 새로 작성)

### 단위 테스트 (vitest)

- [ ] 케이스 7: `markSessionRead` / `markRoutineRead` 가 올바른
      proxy URL 로 POST 발사
- [ ] 케이스 8: `SessionsDrawerPanel` — `unread=true` 행에 dot +
      bold 클래스 적용
- [ ] 케이스 9: row 클릭 시 로컬 state 의 unread 가 false 로
      전환되고 dot 사라짐

### 통합 테스트

- [ ] 시나리오 1: cron 1회 실행 후 드로어 Routines 탭 → 해당
      routine 이 bold + dot. 상세 진입 후 뒤로 가면 normal
- [ ] 시나리오 2: 채팅에서 봇이 응답 후 다른 세션으로 이동 →
      이전 세션이 unread. 다시 진입 시 첫 assistant 메시지 위에
      divider 1줄
- [ ] 시나리오 3: 상세 화면에 머무는 중 SSE 로 새 응답 도착 →
      divider 추가되지 않고 메시지만 추가됨, 뒤로 갔다 다시
      들어와도 unread 아님
- [ ] 시나리오 4: cron 결과 push 알림 도착 → 알림 탭 시
      `/mobile/routine/<bot>/cron/<job>` 으로 이동, 해당 routine
      알림만 dismiss 되고 다른 unread 알림은 트레이에 남음
- [ ] 시나리오 5: 2개 세션 unread 상태에서 PWA badge `2` → 1개
      세션 진입 후 badge `1`, 모두 read 후 badge 사라짐
- [ ] 시나리오 6: 동일 routine 이 5회 연속 실행되어 push 5개
      도착 → `tag` 기반으로 1개 알림만 트레이에 표시 (renotify)

## 6. 사이드 이펙트

- 기존 `.session_meta.json` 사용자는 `last_read_at` 필드가 없으므로
  `unread=False` 로 표시됨 → 마이그레이션 불필요. 대신 신규 메시지
  도착 시점부터 unread 가 정확히 켜진다
- Routine 디렉터리에 `.session_meta.json` 신규 생성 가능 — 백업/
  로테이션 / `abyss reindex` 등 기존 코드 영향 없음 (FTS5 인덱스는
  conversation md 만 참조)
- `display_name` fallback 처럼 `unread` 가 응답 누락이면 frontend
  는 `false` 로 간주해야 함 (`sess.unread ?? false`)
- 하위 호환성: 신규 API 추가만, 기존 응답 필드는 optional 로 추가
  → 구버전 클라이언트는 동작 유지

## 7. Web Push 통합 동작 정리

| 트리거 | 서버 동작 | SW 동작 | 클라이언트 동작 |
|---|---|---|---|
| chat 응답 완료 (`_handle_chat` `done`) | `send_push(kind="chat", session_id=...)` (기존) | `tag: session:<bot>:<sid>` 로 표시 | 상세 보고 있으면 `skip_visible` 로 push 안감 |
| cron 1회 실행 | `send_push(kind="cron", job_name=...)` | `tag: routine:<bot>:cron:<job>` | 같은 job 연속 실행 시 1개 알림으로 갱신 |
| heartbeat 1회 실행 | `send_push(kind="heartbeat", job_name="default")` | `tag: routine:<bot>:heartbeat:default` | 위와 동일 |
| 사용자가 detail mount | `POST /chat/.../read` | `postMessage` 로 해당 tag dismiss | badge count 감소 후 `setAppBadge` |
| 알림 tap | — | 해당 tag close + window focus → 라우팅 | mount 시 자동 mark-read |

이 표가 곧 push ↔ 읽음 상태 single source of truth. 새 push
채널이 생기면 위 4개 컬럼을 동일하게 채울 수 있어야 한다.

## 8. 보안 검토

- OWASP A01 (Broken Access Control): single-user 환경이지만
  read API 는 `_BOT_NAME_PATTERN`, `_ROUTINE_KIND_PATTERN`,
  `_ROUTINE_JOB_PATTERN` 으로 path-traversal 차단. 기존
  `_resolve_routine_dir` 재사용
- OWASP A03 (Injection): body 없음 (서버가 `now()` 만 기록).
  meta 파일 쓰기는 `tmp + rename` atomic + `_save_session_meta`
  기존 로직 그대로
- OWASP A04 (Insecure Design): `last_read_at` 은 단조 증가하지
  않아도 무방 (사용자가 의도적으로 이전 메시지 다시 보고 싶다면
  manual mark unread 미지원 — 이번 plan 범위 아님)
- 인증/인가 변경: 없음 — chat_server 는 loopback bind + Origin
  allowlist 그대로
- PCI-DSS 영향: 없음
- 민감 데이터: `last_read_at` 은 시각 정보만 — PII 무관
