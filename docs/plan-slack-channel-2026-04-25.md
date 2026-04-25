# Plan: Slack channel adapter

- date: 2026-04-25
- status: draft
- author: claude
- approved-by: (pending)
- depends-on: plan-channel-adapter-2026-04-25.md (must be merged first)

---

## 1. 목적 및 배경

### 문제 정의

abyss는 Telegram에서만 동작한다. 사용자 요구: 같은 abyss 시스템 안에서 봇별로 채널을 다르게 구성하고 싶다 (예: 봇 A는 Telegram, 봇 B는 Slack).

`plan-channel-adapter-2026-04-25.md`가 추상 계층을 만들고, 본 plan은 그 위에 **Slack 어댑터**를 구현하여 두 번째 채널을 첫 실사용 케이스로 삼는다.

### 동기

- **워크스페이스 협업**. Slack은 팀 워크스페이스 도구. abyss 봇을 워크스페이스에 두면 회의 메모, 미션 공유 등 Telegram보다 적합한 use case가 있다.
- **multi-tenant 검증**. 두 번째 어댑터는 추상 인터페이스가 잘 설계되었는지 검증하는 첫 사용처. Slack의 다른 점(스트리밍이 native draft 없음, 마크다운 문법 다름, 슬래시 명령 등록 방식 다름)이 abstraction의 약점을 드러내준다.
- **사용자 본인 워크스페이스 우선**. 외부 배포 (다중 워크스페이스 OAuth) 는 비목표. 자기 워크스페이스에 봇 1개 설치하는 1인용 시나리오만 1차 지원.

### 비목표 (out of scope)

- 다중 워크스페이스 OAuth (Slack App Distribution). 1차 릴리즈는 단일 워크스페이스 + Socket Mode.
- Slack Block Kit 풍부한 UI (버튼, 모달, 폼). 텍스트 메시지 + 파일 + 스트리밍만.
- Slack Workflow Builder 연동.
- Slack Connect (외부 워크스페이스 협업).
- abyss 그룹 ↔ Slack 채널 매핑은 **부분 지원** — 1대1 binding 가능, 다중 채널은 후속.

### 가정

- 사용자는 자기 Slack 워크스페이스에 앱을 만들 권한이 있다 (admin 또는 본인 소유 워크스페이스).
- Socket Mode 사용 → 외부 노출 URL 불필요. 로컬 개발 환경 친화적.

---

## 2. 예상 임팩트

### 영향받는 모듈

| 모듈 | 변경 종류 | 비고 |
|---|---|---|
| `pyproject.toml` | 수정 | `slack-bolt>=1.18.0` 의존성 추가 (httpx 따라옴) |
| `src/abyss/channels/slack.py` | 신규 | `SlackGateway(ChannelGateway)` 구현 + `SlackMessageStream` |
| `src/abyss/channels/__init__.py` | 수정 | `register("slack", SlackGateway)` |
| `src/abyss/onboarding.py` | 수정 | `prompt_channel_credentials("slack")` 분기 + Slack 매니페스트 안내 |
| `src/abyss/channels/slack_manifest.py` | 신규 | App Manifest YAML 생성기 |
| `src/abyss/handlers/groups.py` | 수정 (소량) | Slack 채널 ID 프리픽스 (D/C/G) 기반 DM 판별 — 어댑터에서 정규화하므로 변경 최소 |
| `src/abyss/utils.py` | 수정 | `markdown_to_slack_mrkdwn` 추가 (어댑터 내부에서 호출) — 또는 `channels/slack.py`에 두는 것이 더 깨끗 |
| `tests/test_channels_slack.py` | 신규 | 어댑터 단위 테스트 |
| `tests/evaluation/test_slack_e2e.py` | 신규 | 실 Slack 워크스페이스 호출 (CI 제외) |
| `docs/SLACK_SETUP.md` | 신규 | 사용자 설치 가이드 |
| `abysscope/lib/abyss.ts` | 수정 | Slack 채널 표시 (token 마스킹) |
| `abysscope/src/app/bots/[name]/page.tsx` | 수정 | Slack-specific 필드 (bot_token, app_token) UI |

### API/인터페이스 변경

- `bot.yaml` 신규 옵션: `channel.type: "slack"` + `channel.bot_token`, `channel.app_token`.
- `abyss bot add` 흐름: 채널 선택에 "Slack" 옵션 추가.
- 신규 명령 없음.

### 성능

- Socket Mode WebSocket 1개 연결 (봇별). 메시지 수신 지연: 약 50–200ms.
- chat.update API 레이트 리밋: tier 3 (분당 50+회). 스트리밍 throttle을 1초로 설정 (Telegram의 0.5s보다 느림).
- Slack 메시지 길이 한계: 40,000자 (Telegram 4096보다 큼) → 분할 빈도 낮음.

### 사용자 경험 변화

- Slack 워크스페이스에서 abyss 봇과 DM/멘션으로 대화 가능.
- 스트리밍 응답: 첫 메시지 → repeated edit. 커서 표시 (`▌`) 끝에 추가, 완료 시 제거.
- 슬래시 명령은 일부만 지원 (Phase 5에 명시).

### 가용성

- 신규 의존성 `slack-bolt` (라이선스 MIT). 휠 크기 약 +400 KB.
- Socket Mode → 외부 노출 URL 불필요. 사용자 인터넷만 있으면 동작.

---

## 3. 구현 방법 비교

### 방법 A: slack-bolt + Socket Mode (선택)

- `slack-bolt-python`의 AsyncApp + AsyncSocketModeHandler.
- 두 토큰: bot_token (`xoxb-`, 권한 부여), app_token (`xapp-`, 소켓 인증).

**장점**
- 외부 노출 없음 (개인 사용 친화적).
- Slack 공식 SDK, 잘 유지보수됨.
- bolt가 시그니처 검증, 재시도, rate limit 처리.

**단점**
- 의존성 1개 추가 (slack-bolt + 의존 트리).
- Socket Mode는 dev/personal 권장. 운영 규모 (분당 수천 메시지)는 Events API 필요.

### 방법 B: 직접 Web API + Events API + ngrok-like 노출

- httpx로 Slack Web API 직접 호출.
- 메시지 수신은 Events API webhook → 외부 URL 필요 (ngrok 또는 Cloudflare Tunnel).

**장점**
- 의존성 더 가벼움 (httpx는 이미 transitive로 들어옴).

**단점**
- 외부 노출 설정 필요 → 사용자 진입 장벽 큼.
- 시그니처 검증, 재시도, rate limit 직접 구현.
- 사용자가 ngrok 같은 도구 별도 설치.

### 방법 C: `slack-sdk` 직접 사용 (bolt 없이)

- `slack-sdk` (low-level) + 자체 Socket Mode 클라이언트 구현.

**장점**
- bolt의 데코레이터 매직 회피.

**단점**
- 라우팅·검증·재시도를 직접 구현 → 가치 없음.

### 결론

**방법 A (slack-bolt + Socket Mode) 선택.** 1인 personal use에 가장 적합. 운영 규모로 갈 때는 같은 어댑터에서 Events API 모드를 추가 가능 (어댑터 내부 토글).

---

## 4. 구현 단계

### Phase 1 — 의존성 추가

- [ ] Step 1.1 — `pyproject.toml`에 `"slack-bolt>=1.18.0"` 추가. `uv sync`로 lock 갱신.
- [ ] Step 1.2 — `make lint` 통과 확인 (의존성 추가만).

### Phase 2 — 매니페스트 + 온보딩

- [ ] Step 2.1 — `src/abyss/channels/slack_manifest.py` 생성. abyss 봇이 필요한 권한·이벤트·슬래시 명령을 포함한 매니페스트 YAML 템플릿.
  - bot scopes: `chat:write`, `chat:write.public`, `channels:history`, `groups:history`, `im:history`, `mpim:history`, `app_mentions:read`, `files:read`, `files:write`, `commands`, `users:read`.
  - event subscriptions: `app_mention`, `message.im`, `message.channels`, `message.groups`, `message.mpim`, `file_shared`.
  - socket_mode_enabled: true.
  - slash commands: `/cancel`, `/reset`, `/status`, `/skills`, `/help`, `/streaming`, `/model`, `/memory`, `/cron`, `/heartbeat`, `/version` (우선 핵심 11개 — 나머지는 `/help`에서 안내).
- [ ] Step 2.2 — `generate_manifest(bot_display_name: str) -> str` — 매니페스트 YAML 문자열 반환.
- [ ] Step 2.3 — `onboarding.py:prompt_channel_credentials("slack")` 흐름:
  1. 매니페스트 출력 + "Create New App from manifest" 가이드.
  2. 사용자가 워크스페이스에 앱 설치 후 bot_token, app_token 입력.
  3. `SlackGateway.validate_credentials({"bot_token": ..., "app_token": ...})` 호출 → `auth.test`로 검증.
  4. bot user_id, team_id, bot_username 반환.
- [ ] Step 2.4 — `docs/SLACK_SETUP.md` — 단계별 안내 (스크린샷은 추후).

### Phase 3 — SlackGateway

- [ ] Step 3.1 — `src/abyss/channels/slack.py` 생성. `SlackGateway` 클래스 골격:
  ```python
  class SlackGateway:
      type = "slack"
      
      def __init__(self, bot_name: str, channel_config: dict, bot_path: Path):
          self.bot_name = bot_name
          self.bot_token = channel_config["bot_token"]
          self.app_token = channel_config["app_token"]
          self.app: AsyncApp | None = None
          self.handler: AsyncSocketModeHandler | None = None
          self.bot_user_id = ""
          self.bot_username = ""
      
      async def start(self, on_event):
          self.app = AsyncApp(token=self.bot_token)
          # auth.test for bot identity
          ident = await self.app.client.auth_test()
          self.bot_user_id = ident["user_id"]
          self.bot_username = ident["user"]
          
          @self.app.event("app_mention")
          async def _on_mention(event, ack): ...
          
          @self.app.event({"type": "message"})
          async def _on_message(event, ack): ...
          
          # slash commands
          for cmd in REGISTERED_COMMANDS:
              self.app.command(f"/{cmd}")(self._make_command_handler(cmd))
          
          self.handler = AsyncSocketModeHandler(self.app, self.app_token)
          await self.handler.start_async()
          self._on_event = on_event
      
      async def stop(self):
          if self.handler:
              await self.handler.close_async()
  ```
- [ ] Step 3.2 — `_to_event(event_payload, kind)` 변환기. 텍스트, 파일, 멘션 처리.
  - chat_id: Slack channel ID (D*/C*/G*).
  - is_dm: `chat_id.startswith("D")`.
  - is_mention: `<@{bot_user_id}>`가 본문에 있거나 event.type == "app_mention".
  - 본문에서 봇 mention 토큰 제거 후 `text` 필드.
  - user_display_name: `users.info` lookup (캐시 — 작업 단위 dict).
  - timestamp: Slack `ts` ISO 변환.
  - event_id: `f"slack:{event['ts']}"`.
- [ ] Step 3.3 — `send_text(chat_id, text, *, reply_to=None) -> str`:
  - `text`를 `markdown_to_slack_mrkdwn`로 변환.
  - 40,000자 초과 시 `split_message`로 분할 + 순차 발송.
  - `reply_to`가 있으면 `thread_ts` 인자로 전달.
  - 반환값: 첫 발송된 메시지 `ts`.
- [ ] Step 3.4 — `edit_text(chat_id, message_id, text)`:
  - `chat.update(channel=chat_id, ts=message_id, text=mrkdwn(text))`.
- [ ] Step 3.5 — `send_typing(chat_id)`:
  - Slack은 native typing indicator 미지원 (RTM에만 있었음).
  - 옵션: 무시 (no-op) + 스트리밍 첫 청크를 즉시 발송. SlackGateway는 `send_typing`을 no-op으로 구현.
- [ ] Step 3.6 — `send_file(chat_id, file_path, caption=None)`:
  - `files.getUploadURLExternal` → PUT 업로드 → `files.completeUploadExternal`.
  - V2 API 사용 (V1 deprecated).
  - 캡션은 별도 메시지로 thread.
- [ ] Step 3.7 — `download_file(file_ref, dest)`:
  - `file_ref.file_id` (Slack file ID) → `files.info` → `url_private_download` 가져옴 → bot_token 헤더로 GET.
- [ ] Step 3.8 — `SlackMessageStream` 구현:
  - `__init__(client, channel, thread_ts=None)`. 첫 `update`에서 `chat.postMessage`로 메시지 생성, `ts` 저장.
  - 후속 `update`는 `chat.update`. throttle 1초 (Slack rate limit 대응).
  - `finalize`: 마지막 텍스트로 `chat.update`. 커서 마커 제거.
  - `cancel`: 메시지에 "[취소됨]" 추가하고 종료.
- [ ] Step 3.9 — `register_commands(commands)`:
  - Slack은 슬래시 명령을 매니페스트에 정의. 런타임 등록 불가능.
  - 본 메서드는 매니페스트 검증 + 누락 명령 경고. 실제 등록은 매니페스트.
- [ ] Step 3.10 — `validate_credentials(channel_config) -> dict | None` (classmethod):
  - bot_token, app_token 형식 검증 (`xoxb-`, `xapp-` prefix).
  - `auth.test` 호출 → 성공 시 `{user_id, user, team_id, team}` 반환.
- [ ] Step 3.11 — `markdown_to_slack_mrkdwn(text: str) -> str`:
  - **bold** (`**` → `*`).
  - *italic* (`*` 단일 → `_`, conflict 주의 — 안전한 정규식).
  - 코드 블록은 ``` 그대로.
  - 인라인 코드 `` ` `` 그대로.
  - [text](url) → `<url|text>`.
  - 헤더 (`#`)는 mrkdwn 미지원 → bold + 줄바꿈.
  - 리스트는 그대로.
- [ ] Step 3.12 — `channels/__init__.py`에 `register("slack", SlackGateway)` 추가.

### Phase 4 — 핸들러 분기 (소량)

- [ ] Step 4.1 — `handlers/groups.py:should_handle_group_message(ctx)` — 채널 무관 로직 유지. Slack 워크스페이스 채널도 group으로 취급. 이미 ChannelEvent 추상으로 처리됨.
- [ ] Step 4.2 — `handlers/messages.py:file_handler` — Slack의 file_shared 이벤트가 ChannelEvent.files에 매핑되도록 어댑터에서 정규화. 핸들러 자체는 변경 없음.
- [ ] Step 4.3 — `handlers/streaming.py` — 스트리밍 청크 throttle을 게이트웨이가 결정 (`gateway.stream_throttle_seconds`). Telegram 0.5s, Slack 1.0s. 핸들러는 throttle 값 모르고 동작.

### Phase 5 — 슬래시 명령 매핑

- [ ] Step 5.1 — Slack 슬래시 명령은 dispatcher로 routing. abyss 명령 17개 중 핵심 11개 매니페스트 등록 (Phase 2.1 목록). 나머지 6개 (`start`, `resetall`, `files`, `send`, `compact`, `bind`, `unbind`)는 Slack에서 미지원 — `/help` 응답에 안내.
- [ ] Step 5.2 — Slack 슬래시 명령 핸들러는 `(ack, command, say)` 시그니처. 어댑터가 `ack()` 호출 후 `ChannelEvent`로 변환하여 `_on_event` 호출.
- [ ] Step 5.3 — 명령 응답이 ephemeral인지 in-channel인지: 기본 in-channel (Telegram 동등). `/cancel`처럼 빠른 응답은 ephemeral 옵션 검토 (후속).

### Phase 6 — abysscope 대시보드

- [ ] Step 6.1 — `abysscope/lib/abyss.ts` — Slack 채널 type 인식. token 마스킹 (앞 4자 + `***` + 뒤 4자).
- [ ] Step 6.2 — 봇 상세 페이지 — 채널 type 칩 + Slack-specific 필드 (workspace name, bot_user_id) 표시.
- [ ] Step 6.3 — 봇 추가 마법사에 Slack 옵션 (대시보드의 onboarding 미러). 1차 릴리즈는 CLI만 지원, 대시보드 마법사는 후속.

### Phase 7 — 테스트

- [ ] Step 7.1 — `tests/test_channels_slack.py`:
  - SlackGateway 메서드 mock 테스트.
  - `_to_event` 변환 정확성.
  - `markdown_to_slack_mrkdwn` 변환 케이스.
  - `validate_credentials` 토큰 prefix 검증.
- [ ] Step 7.2 — `tests/evaluation/test_slack_e2e.py`:
  - 실 워크스페이스 + 환경변수 토큰 (`SLACK_E2E_BOT_TOKEN`, `SLACK_E2E_APP_TOKEN`).
  - 메시지 송수신, 파일 업로드/다운로드, 스트리밍 응답.
  - CI 제외 (`tests/evaluation`은 이미 ignore).

### Phase 8 — 문서화

- [ ] Step 8.1 — `docs/SLACK_SETUP.md`:
  - Slack App 생성 → 매니페스트 붙여넣기.
  - bot_token, app_token 발급 절차.
  - 워크스페이스 설치 + DM 시작.
  - `abyss bot add` 흐름.
- [ ] Step 8.2 — `CLAUDE.md` — Tech Stack에 `slack-bolt` 추가. Channel 표에 Slack 행.
- [ ] Step 8.3 — `docs/ARCHITECTURE.md` — 채널 어댑터 다이어그램에 Slack 추가. 매니페스트 흐름 명시.
- [ ] Step 8.4 — `docs/TECHNICAL-NOTES.md` — Slack-specific 동작 (Socket Mode, 스트리밍 패턴, mrkdwn 변환, 미지원 명령) 섹션.
- [ ] Step 8.5 — `README.md` — "Channels: Telegram, Slack" 한 줄.
- [ ] Step 8.6 — `docs/SECURITY.md` — Slack 토큰 저장 (bot_token + app_token 둘 다 평문 YAML), 노출 위험. backup.py로 보호. 새로운 finding 항목.

### Phase 9 — 검증

- [ ] Step 9.1 — `make lint && make test` 통과.
- [ ] Step 9.2 — Slack 워크스페이스 1개로 수동 검증:
  - `abyss bot add` → Slack 선택 → 매니페스트 출력 → 토큰 입력 → 봇 동작.
  - DM에서 텍스트 메시지 → 응답.
  - 스트리밍 응답 (chat.update repeated).
  - 파일 업로드 (사용자 → 봇).
  - 파일 다운로드 (봇 → 사용자).
  - 슬래시 명령 11개 동작.
  - 채널에 봇 초대 + @mention → 응답.
  - 그룹 모드: Slack 채널을 abyss 그룹과 binding → 오케스트레이터/멤버 패턴 동작.
- [ ] Step 9.3 — 동시 multi-bot: 봇 A (Telegram) + 봇 B (Slack)을 같은 abyss 프로세스에서 실행 → 둘 다 정상.

---

## 5. 테스트 계획

### 단위 테스트 (`tests/test_channels_slack.py`)

- [ ] 케이스 1: `_to_event` — DM 메시지 → `is_dm=True`.
- [ ] 케이스 2: `_to_event` — 채널 메시지 + `<@UBOT>` → `is_mention=True`, text에서 mention 제거.
- [ ] 케이스 3: `_to_event` — 채널 메시지 + 봇 unmention → `is_mention=False`.
- [ ] 케이스 4: `_to_event` — 그룹 DM (G prefix) → `is_dm=False`, `is_mention=` mention 여부.
- [ ] 케이스 5: `_to_event` — file_shared 이벤트 → `files` 채워짐, text는 None.
- [ ] 케이스 6: `send_text` — mock client.chat_postMessage 호출, mrkdwn 변환 적용.
- [ ] 케이스 7: `send_text` — 40,000자 초과 → 분할 + 순차 호출.
- [ ] 케이스 8: `send_text` — `reply_to` 지정 시 `thread_ts` 전달.
- [ ] 케이스 9: `edit_text` — mock client.chat_update 호출.
- [ ] 케이스 10: `SlackMessageStream.update` — 첫 호출은 chat.postMessage, 이후 chat.update.
- [ ] 케이스 11: `SlackMessageStream` — 1초 throttle 검증 (시간 mock).
- [ ] 케이스 12: `SlackMessageStream.finalize` — 마지막 update 호출, 커서 제거.
- [ ] 케이스 13: `download_file` — files.info → url_private_download → bot_token Bearer로 GET.
- [ ] 케이스 14: `send_file` — files.getUploadURLExternal + completeUploadExternal 시퀀스.
- [ ] 케이스 15: `validate_credentials` — bot_token이 `xoxb-` 접두 아니면 None.
- [ ] 케이스 16: `validate_credentials` — `auth.test` 호출 → user_id, team 반환.
- [ ] 케이스 17: `markdown_to_slack_mrkdwn` — `**bold**` → `*bold*`.
- [ ] 케이스 18: `markdown_to_slack_mrkdwn` — `*italic*` → `_italic_`.
- [ ] 케이스 19: `markdown_to_slack_mrkdwn` — `[text](url)` → `<url|text>`.
- [ ] 케이스 20: `markdown_to_slack_mrkdwn` — 코드 블록 그대로.
- [ ] 케이스 21: `markdown_to_slack_mrkdwn` — 헤더 → bold + 줄바꿈.
- [ ] 케이스 22: `register_commands` — 매니페스트에 누락된 명령 경고 출력.

### 매니페스트 테스트 (`tests/test_slack_manifest.py`)

- [ ] 케이스 23: `generate_manifest("MyBot")` — 봇 표시명 반영.
- [ ] 케이스 24: 출력이 valid YAML.
- [ ] 케이스 25: 필요한 scopes 모두 포함.
- [ ] 케이스 26: 슬래시 명령 11개 모두 등록.

### 통합 테스트

- [ ] 시나리오 1 (`tests/test_channels_integration.py`): SlackGateway start → mock socket으로 메시지 주입 → on_event 콜백 호출 확인.
- [ ] 시나리오 2: SlackGateway + handlers — 명령 핸들러까지 디스패치 정상.
- [ ] 시나리오 3: 동시 Telegram + Slack 봇 (각자 다른 채널) → 독립 동작.
- [ ] 시나리오 4: 봇 종료 → SocketModeHandler close → AsyncApp graceful stop.
- [ ] 시나리오 5: 토큰 invalid → start 실패 + 명확한 에러 메시지.

### E2E 테스트 (`tests/evaluation/test_slack_e2e.py`, CI 제외)

- [ ] 시나리오 E1: 실 워크스페이스 — DM 송수신 라운드트립.
- [ ] 시나리오 E2: 파일 업로드/다운로드.
- [ ] 시나리오 E3: 스트리밍 응답 (chat.update repeated).
- [ ] 시나리오 E4: 슬래시 명령 1개 (`/status`) 응답.

---

## 6. 사이드 이펙트

### 기존 기능에 미치는 영향

| 항목 | 영향 | 대응 |
|---|---|---|
| Telegram 봇 동작 | 변경 없음 | plan-channel-adapter 통과 시 추상이 검증됨 |
| `pyproject.toml` 의존성 트리 | `slack-bolt` + 자식들 추가 | Lock 갱신, 휠 크기 +400KB. 무시 가능 |
| 휠 빌드 | force-include 영향 없음 | 영향 없음 |
| 봇 메모리 사용 | Slack 봇당 WebSocket 1개 + AsyncApp 인스턴스 | ~5 MB/bot. 현재 Telegram 봇 (~5 MB)와 비슷 |
| 다중 봇 시작 시간 | Slack auth.test API 1회 추가 | ~200 ms/bot. 무시 가능 |
| 추상 인터페이스 | 어댑터 2번째 구현 → 인터페이스 미흡 부분 발견 가능 | 본 plan 진행 중 인터페이스 변경 발견 시 plan-channel-adapter도 함께 업데이트 |

### 하위 호환성

- 기존 Telegram 봇은 영향 없음.
- 신규 Slack 봇은 신규 스키마 (`channel.type=slack`).

### 마이그레이션 필요 여부

- 없음. 신규 옵션 추가만.

### 운영/배포

- `uv sync`로 신규 의존성 설치 필요.
- 사용자가 Slack 워크스페이스에서 직접 앱 생성 (Slack 정책상 자동화 어려움).
- `docs/SLACK_SETUP.md` 가이드 필수.

---

## 7. 보안 검토

### OWASP Top 10 관련

| 항목 | 적용 여부 | 검토 |
|---|---|---|
| A01 Broken Access Control | 검토 필요 | Slack의 채널 가시성 = abyss `allowed_users` 화이트리스트 + 채널 라우팅. user_id는 Slack U-prefix 사용. ChannelEvent.user_id는 정규화된 문자열. 화이트리스트 매칭은 channel별 user_id 형식이 다른 점 주의 — `bot.yaml`의 `allowed_users`는 채널별 분리 또는 prefix 명시 권장 |
| A02 Cryptographic Failures | **중요** | 두 토큰 (bot_token + app_token) 평문 YAML 저장. AES-256 backup이 최소한의 보호. Mac Keychain 통합은 후속. |
| A03 Injection | 낮음 | mrkdwn 변환에서 사용자 입력에 의한 코드 인젝션 (예: `<@everyone>` 발송) — 어댑터가 출력 시 escape 처리. `<>` 특수 문자 escape. |
| A04 Insecure Design | 검토 필요 | Socket Mode는 외부 노출 없음 — design 측면에선 안전. Bot user_id를 저장해서 mention 판별에 사용 — spoof 가능성? Slack 자체에서 처리하므로 신뢰 가능. |
| A05 Security Misconfiguration | 검토 필요 | 매니페스트 권한이 과도하지 않은지 검토. `chat:write.public`은 init되지 않은 채널에도 발송 가능 — 필요한가? 검토 후 minimal로 조정 |
| A06 Vulnerable Components | 낮음 | slack-bolt는 공식 SDK, 활발한 유지보수 |
| A07 Authn Failures | 검토 필요 | `auth.test` 호출 결과 신뢰. 토큰 만료/회수 시 명확한 에러 출력 |
| A08 Software/Data Integrity | 낮음 | bot.yaml 손상 시 `abyss bot add` 재실행으로 복구 가능 |
| A09 Logging Failures | 검토 필요 | 토큰을 절대 로그에 남기지 않음. exception 메시지에서도 escape (slack-bolt 라이브러리도 이 점 검증) |
| A10 SSRF | 낮음 | Slack API endpoints는 hardcoded. 사용자 입력이 endpoint를 변경하지 않음 |

### 인증/인가 변경

- 사용자 화이트리스트 (`allowed_users`) — Slack user_id (`U`로 시작)와 Telegram user_id (정수)가 형식이 다름. 같은 봇이 두 채널 동시 운영을 한다고 가정해도 화이트리스트는 채널별 분리가 자연스러움. 1차 릴리즈는 봇당 채널 1개이므로 이슈 없음. 다중 채널 1봇은 후속 plan에서 다룸.
- bot_user_id로 mention 판별 — Slack이 사인으로 보내는 값 신뢰.

### 민감 데이터 처리

- bot_token + app_token 평문 저장 → `docs/SECURITY.md`에 finding 추가.
- 로그에 토큰 절대 출력 금지 — 로깅 단계 검증 (테스트 케이스 추가: 토큰 포함 메시지 로깅 시 마스킹).
- abysscope 대시보드 — 토큰 표시는 마스킹.

### PCI-DSS 영향

- 해당 없음.

### 추가 위협 모델링

- **위협**: Slack 워크스페이스의 다른 사용자가 봇에 prompt injection 시도.
  - **완화**: `allowed_users` 화이트리스트 (Slack user_id) 강제. 화이트리스트 비어있으면 워크스페이스 모든 사용자 허용 — 명시적 위험 표시.
- **위협**: 매니페스트 권한 과다.
  - **완화**: 매니페스트 작성 시 minimal scope 원칙. 사용자가 install 시 권한 화면에서 검토 가능.
- **위협**: `<@channel>`, `<@here>`, `<!everyone>` 같은 채널 멘션 토큰을 봇이 응답에 그대로 출력 → 채널 전체 멘션 폭탄.
  - **완화**: 어댑터의 `send_text`에서 outgoing payload 검사 + 이런 토큰을 plain text (`@channel` 등 escape)로 변환.
- **위협**: Socket Mode 연결이 끊어진 후 재연결 실패 → 봇 좀비.
  - **완화**: AsyncSocketModeHandler가 자동 재연결. 일정 시간 (예: 60초) 동안 재연결 실패 시 abyss 로그 ERROR + 재시작 시도.

---

## 8. 완료 조건 체크리스트

- [ ] Phase 1~9 구현 단계 100% 완료
- [ ] 단위 테스트 케이스 1~26 통과
- [ ] 통합 테스트 시나리오 1~5 통과
- [ ] E2E 테스트 시나리오 E1~E4 수동 확인
- [ ] `make lint` 통과
- [ ] `make test` 통과
- [ ] `docs/SLACK_SETUP.md` 작성 완료
- [ ] 회귀 검증 (Phase 9.2, 9.3) 모두 통과
- [ ] 사이드이펙트 표 항목 모두 "해당 없음" 또는 "대응 완료"
- [ ] 보안 검토 항목 모두 "검토 완료" 또는 "대응 완료"
- [ ] 문서 (`CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/TECHNICAL-NOTES.md`, `README.md`, `docs/SECURITY.md`) 갱신
- [ ] 본 문서 status를 `done`으로 변경

## 9. 중단 기준

- Slack Socket Mode가 abyss의 1인 사용 시나리오에서 안정적으로 유지되지 않는 경우 (재연결 실패, 메시지 누락이 잦음).
- 매니페스트 기반 설치 흐름이 사용자에게 비현실적으로 어려운 경우 (검증 단계에서 사용자 시뮬레이션 실패).
- ChannelGateway 추상 인터페이스가 Slack 동작을 표현하기에 부족한 점이 발견되어 plan-channel-adapter의 변경이 광범위한 경우.
- → 즉시 중단, plan-channel-adapter 동시 수정 후 사용자 리뷰.
