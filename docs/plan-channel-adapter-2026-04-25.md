# Plan: Channel adapter abstraction (per-bot multi-channel readiness)

- date: 2026-04-25
- status: draft
- author: claude
- approved-by: (pending)

---

## 1. 목적 및 배경

### 문제 정의

abyss는 현재 Telegram 전용으로 강하게 결합되어 있다.

- `python-telegram-bot.Application`이 `bot_manager.py:_run_bots` (line 38)에서 봇별로 직접 인스턴스화된다.
- `handlers.py` (1715줄)의 17개 슬래시 핸들러와 메시지 핸들러가 모두 `(telegram.Update, ContextTypes.DEFAULT_TYPE)` 시그니처를 받고, `update.message.reply_text(...)`, `context.bot.send_message(...)`, `context.bot.send_chat_action(...)` 등 PTB API를 직접 호출한다.
- `utils.py:markdown_to_telegram_html`, `split_message(limit=TELEGRAM_MESSAGE_LIMIT)`은 Telegram 포맷 가정이 들어가 있다.
- `onboarding.py:validate_telegram_token`, `prompt_telegram_token`, `create_bot`은 Telegram 토큰 1개만 다룬다.
- `bot.yaml` 스키마는 `token: <string>` 필드 1개에 Telegram 토큰을 직접 박아 놓는다.
- `handlers.py:_is_mentioned`, `_should_handle_group_message` 등 그룹 라우팅 로직도 Telegram entity 구조에 직접 의존한다.

이 결합 때문에 두 번째 채널(Slack)을 추가하려면 동일 기능을 두 번 구현해야 한다. 핸들러 17개를 복제하고, 메시지 분할/포맷 함수를 복제하고, 라우팅 로직을 두 곳에 두어야 한다 → 유지보수가 빠르게 깨진다.

### 동기

- **Slack 채널 도입의 선결 조건** (plan-slack-channel-2026-04-25에서 의존). 추상화 없이 Slack을 붙이면 코드 중복이 영구화된다.
- **봇별 채널 구성** — 사용자 요구사항: "한 abyss 시스템에서 봇별로 채널을 구성할 수 있어야 한다." 봇 A는 Telegram, 봇 B는 Slack, 봇 C는 (장래에) 둘 다 — 같은 abyss 프로세스에서 공존해야 한다.
- **테스트 가능성** — 채널 의존성을 인터페이스로 분리하면 `FakeGateway`로 단위 테스트 가능. 현재는 `python-telegram-bot` 모킹이 깊고 깨지기 쉽다.

### 비목표 (out of scope)

- Slack 어댑터 자체는 별도 plan (`plan-slack-channel-2026-04-25.md`).
- 다중 채널 1봇 (한 봇이 Telegram + Slack 동시) — 스키마는 미래에 다중을 허용하도록 설계하지만, 이번 릴리즈에서는 봇당 채널 1개만 검증.
- ChannelEvent 통합 라우팅 (모든 채널 메시지를 한 큐에) — 봇별 게이트웨이 독립성 유지.
- WhatsApp/Discord 등 추가 채널 — 후속 plan.

---

## 2. 예상 임팩트

### 영향받는 모듈

| 모듈 | 변경 종류 | 비고 |
|---|---|---|
| `src/abyss/channels/__init__.py` | 신규 | 채널 레지스트리 |
| `src/abyss/channels/base.py` | 신규 | `ChannelGateway` Protocol, `ChannelEvent`, `MessageStream`, `BotContext`, `CommandSpec`, `FileRef` |
| `src/abyss/channels/telegram.py` | 신규 | `TelegramGateway(ChannelGateway)` — 기존 PTB 코드 캡슐화 |
| `src/abyss/handlers/__init__.py` | 신규 | `make_event_handler(...)` 진입점 |
| `src/abyss/handlers/commands.py` | 신규 (분할) | 슬래시 명령 핸들러 (channel-agnostic) |
| `src/abyss/handlers/messages.py` | 신규 (분할) | 텍스트·파일 메시지 핸들러 |
| `src/abyss/handlers/groups.py` | 신규 (분할) | 그룹 라우팅 (`_should_handle_group_message` 이전) |
| `src/abyss/handlers/streaming.py` | 신규 (분할) | 스트리밍 응답 빌더 (gateway-agnostic) |
| `src/abyss/handlers/dispatch.py` | 신규 | command 디스패치 테이블 |
| `src/abyss/handlers.py` | 삭제 | 모든 함수가 `handlers/` 패키지로 이동 |
| `src/abyss/utils.py` | 수정 | `split_message`에 `limit` 파라미터 일반화. `markdown_to_telegram_html` → `channels/telegram.py`로 이동 |
| `src/abyss/bot_manager.py` | 수정 | `_run_bots` — 봇별 게이트웨이 클래스 resolve, `start(on_event)` 호출. `set_bot_commands` 이동 |
| `src/abyss/onboarding.py` | 수정 | `prompt_channel_type()` 추가. Telegram 검증은 `channels/telegram.py:validate_credentials` 위임 |
| `src/abyss/config.py` | 수정 | `load_bot_config` — 레거시 `token:` 자동 마이그레이션. `save_bot_config` — 신규 스키마로 저장 |
| `src/abyss/cli.py` | 수정 | `abyss bot add` 흐름에서 채널 선택 |
| `src/abyss/cron.py` | 수정 | 크론 잡 실행 시 게이트웨이 통한 메시지 발송 (현재 PTB 직접 호출) |
| `src/abyss/heartbeat.py` | 수정 | 동일 |
| `src/abyss/skill.py` | 변경 없음 | CLAUDE.md 컴포지션은 채널 무관 |
| `bot.yaml` 스키마 | 변경 | `token` → `channel.type` + `channel.token` |
| `tests/test_channels_telegram.py` | 신규 | 게이트웨이 어댑터 단위 테스트 |
| `tests/test_handlers_*.py` | 수정 | FakeGateway 기반 테스트로 일부 마이그레이션 |
| `tests/conftest.py` | 수정 | `fake_gateway` fixture 추가 |
| `abysscope/lib/abyss.ts` | 수정 | 새 스키마 읽기/쓰기 (대시보드 영향) |
| `abysscope/src/app/bots/[name]/page.tsx` | 수정 | 채널 표시/편집 UI |

### API/인터페이스 변경

- 핸들러 시그니처가 `(Update, ContextTypes)` → `(BotContext)`로 바뀐다. 외부 사용자는 영향 없음 (내부 API).
- bot.yaml 스키마: `token: ...` → `channel: {type: "telegram", token: ...}`. 자동 마이그레이션 제공.
- 신규 사용자 관점에서 `abyss bot add`는 채널 선택 단계가 추가됨 (Telegram 외 옵션이 없는 동안엔 "Telegram"만 자동 선택).

### 성능

- 추상 호출 한 단계 추가 (게이트웨이 메서드 디스패치) → 메시지당 ~1µs 미만, 측정 불가능 수준.
- 게이트웨이 인스턴스가 봇별 1개 → 메모리 소량 증가 (~1KB/bot).

### 사용자 경험 변화

- **외관상 변화 없음**. 기존 Telegram 봇은 동일하게 동작.
- `abyss bot add` 흐름에 "Channel: telegram" 단계가 한 줄 추가됨 (현재 옵션은 telegram 1개).
- abysscope 대시보드 봇 상세 페이지에 채널 칩이 표시됨.

### 가용성

- 의존성 변경 없음. python-telegram-bot 그대로.
- 마이그레이션 자동화로 기존 사용자는 추가 액션 불필요.

---

## 3. 구현 방법 비교

### 방법 A: Protocol 기반 추상 + 게이트웨이 캡슐화 (선택)

- `ChannelGateway`는 `typing.Protocol` (덕 타이핑). 강제 상속 없음.
- `TelegramGateway`는 PTB Application + 발송 메서드를 캡슐화.
- 핸들러 함수는 `BotContext`만 받음 (이벤트 + 게이트웨이 + 봇 상태).
- 게이트웨이가 `start(on_event)`로 콜백 등록 → 모든 메시지를 단일 콜백으로 흘림.

**장점**
- 추상화 비용 낮음 (Protocol).
- 어댑터가 PTB 의존성을 자기 안에만 가둠.
- FakeGateway 테스트 용이.

**단점**
- 핸들러 1714줄 리팩터 필요. 변경 범위 큼.

### 방법 B: 두 번째 채널 직접 추가 (추상화 없이)

- Slack용 `slack_handlers.py` 새로 만들고 `bot_manager`에서 분기.

**장점**
- 단기 변경 최소.

**단점**
- 핸들러 17개 복제. 미래에 세 번째 채널은 두 배 비용.
- 기존 Telegram 코드도 같이 깨끗해질 기회 상실.

### 방법 C: 외부 라이브러리 도입 (예: `botbuilder`, `errbot`)

**장점**
- 다채널 추상이 이미 있음.

**단점**
- 의존성 무거움.
- abyss의 "Claude Code 우선" 모델, 그룹 오케스트레이터 패턴 등을 외부 프레임워크에 끼워 맞추기 어려움.
- 라이브러리 학습 곡선.

### 결론

**방법 A (Protocol 기반 + 캡슐화) 선택.** 한 번의 리팩터로 미래 채널 N개를 위한 토대를 만든다. PTB 의존성을 어댑터 1개에 가두면 채널 추가가 어댑터 1개 추가로 환원된다.

---

## 4. 구현 단계

### Phase 1 — 추상 타입 정의

- [ ] Step 1.1 — `src/abyss/channels/__init__.py` 패키지 시작.
- [ ] Step 1.2 — `src/abyss/channels/base.py` 작성:
  ```python
  from typing import Protocol, ClassVar, Awaitable, Callable, Any
  from dataclasses import dataclass
  from datetime import datetime
  from pathlib import Path

  @dataclass(frozen=True, slots=True)
  class FileRef:
      file_id: str
      filename: str
      mime_type: str | None
      size_bytes: int | None

  @dataclass(frozen=True, slots=True)
  class ChannelEvent:
      event_id: str
      channel: str
      chat_id: str
      user_id: str
      user_display_name: str
      bot_username: str
      text: str | None
      files: tuple[FileRef, ...]
      is_dm: bool
      is_mention: bool
      timestamp: datetime
      raw: Any

  @dataclass(frozen=True, slots=True)
  class CommandSpec:
      name: str          # "cancel", "reset", ...
      description: str

  class MessageStream(Protocol):
      async def update(self, text: str) -> None: ...
      async def finalize(self, text: str) -> str: ...
      async def cancel(self) -> None: ...

  EventHandler = Callable[[ChannelEvent], Awaitable[None]]

  class ChannelGateway(Protocol):
      type: ClassVar[str]
      bot_name: str
      bot_username: str

      async def start(self, on_event: EventHandler) -> None: ...
      async def stop(self) -> None: ...
      async def send_text(self, chat_id: str, text: str, *, reply_to: str | None = None) -> str: ...
      async def edit_text(self, chat_id: str, message_id: str, text: str) -> None: ...
      async def send_typing(self, chat_id: str) -> None: ...
      async def send_file(self, chat_id: str, file_path: Path, caption: str | None = None) -> str: ...
      async def download_file(self, file_ref: FileRef, dest: Path) -> Path: ...
      async def begin_stream(self, chat_id: str, *, reply_to: str | None = None) -> MessageStream: ...
      async def register_commands(self, commands: list[CommandSpec]) -> None: ...
  ```
- [ ] Step 1.3 — `src/abyss/channels/registry.py`:
  ```python
  GATEWAYS: dict[str, type[ChannelGateway]] = {}
  def register(name: str, cls: type[ChannelGateway]) -> None: ...
  def get_gateway_class(name: str) -> type[ChannelGateway]: ...
  ```
- [ ] Step 1.4 — `BotContext` 타입을 `handlers/__init__.py`에 정의:
  ```python
  @dataclass(frozen=True)
  class BotContext:
      event: ChannelEvent
      gateway: ChannelGateway
      bot_name: str
      bot_path: Path
      bot_config: dict[str, Any]
      group_config: dict[str, Any] | None
  ```

### Phase 2 — Telegram 어댑터

- [ ] Step 2.1 — `src/abyss/channels/telegram.py` 신설. 기존 `bot_manager.py:_run_bots`의 PTB 초기화 코드와 `handlers.py`의 PTB 호출을 한곳에 모음.
- [ ] Step 2.2 — `TelegramGateway` 구현:
  ```python
  class TelegramGateway:
      type = "telegram"
      
      def __init__(self, bot_name: str, channel_config: dict, bot_path: Path):
          self.bot_name = bot_name
          self.token = channel_config["token"]
          self.application = Application.builder().token(self.token).build()
          self.bot_username = ""  # set in start
      
      async def start(self, on_event: EventHandler) -> None:
          # Single MessageHandler captures all updates
          self.application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, self._on_message))
          self.application.add_handler(MessageHandler(filters.COMMAND, self._on_command))
          await self.application.initialize()
          self.bot_username = self.application.bot.username or ""
          await self.application.start()
          await self.application.updater.start_polling(drop_pending_updates=True)
          self._on_event = on_event
      
      async def _on_message(self, update, context):
          event = self._to_event(update, is_command=False)
          if event:
              await self._on_event(event)
      
      async def _on_command(self, update, context):
          event = self._to_event(update, is_command=True)
          if event:
              await self._on_event(event)
      ...
  ```
- [ ] Step 2.3 — `_to_event(update, is_command)` 변환기 — `_is_mentioned` 로직 (`handlers.py:89`) 흡수.
- [ ] Step 2.4 — `send_text`, `edit_text`, `send_typing`, `send_file`, `download_file` 구현. 기존 PTB 호출을 그대로 옮김.
- [ ] Step 2.5 — `TelegramMessageStream(MessageStream)` 구현. sendMessageDraft + 0.5초 throttle + finalize 시 editMessageText fallback. 기존 `_send_streaming_response` (`handlers.py:501`)에서 추출.
- [ ] Step 2.6 — `register_commands` 구현. PTB의 `set_my_commands` 호출. 기존 `set_bot_commands` (`handlers.py:1711`)에서 이전.
- [ ] Step 2.7 — `validate_credentials(channel_config) -> dict | None` — 기존 `onboarding.py:validate_telegram_token` (line 111)에서 이전.
- [ ] Step 2.8 — `channels/__init__.py`에서 `register("telegram", TelegramGateway)`.
- [ ] Step 2.9 — `markdown_to_telegram_html`을 `channels/telegram.py`로 이동. 게이트웨이의 `send_text`/`edit_text`가 내부적으로 호출 (호출자는 markdown 그대로 전달).

### Phase 3 — handlers 분할 + 채널 무관화

- [ ] Step 3.1 — `src/abyss/handlers/` 패키지 생성. 기존 `handlers.py`는 점진 비움.
- [ ] Step 3.2 — `handlers/dispatch.py`:
  ```python
  COMMAND_HANDLERS: dict[str, Callable[[BotContext], Awaitable[None]]] = {}
  def command(name: str): ...   # decorator
  ```
- [ ] Step 3.3 — `handlers/commands.py` — 17개 슬래시 핸들러를 옮긴다. 각 함수 시그니처를 `(ctx: BotContext)`로 변경. PTB 호출은 모두 `ctx.gateway.send_text(...)` 등으로 치환.
  - `start`, `help`, `reset`, `resetall`, `files`, `status`, `send`, `model`, `cancel`, `streaming`, `version`, `memory`, `skills`, `cron`, `heartbeat`, `compact`, `bind`, `unbind`
- [ ] Step 3.4 — `handlers/messages.py` — `message_handler`, `file_handler`, `_process_message`, `_prepare_session_context`, `_call_with_resume_fallback`, `_send_non_streaming_response`, `_send_streaming_response`. PTB 호출 제거. 스트리밍은 `ctx.gateway.begin_stream()` 사용.
- [ ] Step 3.5 — `handlers/groups.py` — `_should_handle_group_message`, `_is_user_allowed`. ChannelEvent 기반으로.
- [ ] Step 3.6 — `handlers/streaming.py` — 스트리밍 응답 페이로드 빌더 (마크다운 청크 누적, throttle 정책). 게이트웨이 무관.
- [ ] Step 3.7 — `handlers/__init__.py`에 진입점:
  ```python
  async def make_event_handler(bot_name, bot_path, bot_config, gateway) -> EventHandler:
      async def on_event(event: ChannelEvent) -> None:
          ctx = BotContext(event=event, gateway=gateway, bot_name=bot_name, bot_path=bot_path, bot_config=bot_config, group_config=...)
          # group routing
          if event.is_dm:
              ...
          else:
              if not should_handle_group_message(ctx):
                  return
              ...
          # command vs message
          if event.text and event.text.startswith("/"):
              await dispatch_command(ctx)
          else:
              await handle_message(ctx)
      return on_event
  ```
- [ ] Step 3.8 — 기존 `handlers.py` 삭제. 모든 import 사이트를 `handlers` 패키지로 변경.

### Phase 4 — bot_manager + cron + heartbeat

- [ ] Step 4.1 — `bot_manager.py:_run_bots` (line 38) 리팩터:
  ```python
  for bot_name in bot_names:
      bot_config = load_bot_config(bot_name)
      channel_config = bot_config["channel"]
      GatewayClass = get_gateway_class(channel_config["type"])
      gateway = GatewayClass(bot_name, channel_config, bot_directory(bot_name))
      on_event = await make_event_handler(bot_name, bot_directory(bot_name), bot_config, gateway)
      gateways.append(gateway)
      await gateway.start(on_event)
      await gateway.register_commands(default_commands())
  ```
- [ ] Step 4.2 — 종료 시 모든 게이트웨이 `stop()` 호출. `signal_handler` (`bot_manager.py:125`)에서 SDK 풀 종료 + 게이트웨이 종료.
- [ ] Step 4.3 — `set_bot_commands` 위치 이동 → `register_commands` 패턴.
- [ ] Step 4.4 — `cron.py` — 잡 실행 결과 메시지 전송 부분이 PTB Bot을 직접 사용한다면 게이트웨이 인스턴스를 받도록 변경. 게이트웨이는 봇 시작 시 등록한 인스턴스를 모듈 레벨 dict에서 lookup.
- [ ] Step 4.5 — `heartbeat.py` — 동일.

### Phase 5 — bot.yaml 스키마 마이그레이션

- [ ] Step 5.1 — `config.py:load_bot_config` (line 52):
  ```python
  config = yaml.safe_load(...)
  if "token" in config and "channel" not in config:
      config["channel"] = {"type": "telegram", "token": config.pop("token")}
      logger.info(f"Migrated {name} to channel schema")
      save_bot_config(name, config)
  return config
  ```
- [ ] Step 5.2 — `config.py:save_bot_config` (line 61) — `channel` 필드 그대로 직렬화.
- [ ] Step 5.3 — `generate_claude_md` 등 token 관련 다른 함수가 없는지 점검. 영향 시 수정.
- [ ] Step 5.4 — abysscope `lib/abyss.ts`의 봇 읽기/쓰기 — 신규 스키마 + 레거시 호환 (대시보드도 마이그레이션 트리거).
- [ ] Step 5.5 — abysscope `src/app/bots/[name]/page.tsx` — 채널 정보 표시 (type 칩 + token 마스킹).

### Phase 6 — onboarding

- [ ] Step 6.1 — `onboarding.py:add_bot` — 채널 선택 추가:
  ```python
  channel_type = prompt_channel_type()  # 현재는 ["telegram"] 1개만
  validator = get_gateway_class(channel_type).validate_credentials
  channel_config = prompt_channel_credentials(channel_type)
  ```
- [ ] Step 6.2 — `prompt_channel_credentials("telegram")` → 기존 `prompt_telegram_token` 재사용.
- [ ] Step 6.3 — `create_bot(channel_type, channel_config, profile)` 시그니처 변경. 기존 `(token, bot_info, profile)`는 deprecated.
- [ ] Step 6.4 — `_display_qmd_status` 등 변경 없음.

### Phase 7 — 테스트

- [ ] Step 7.1 — `tests/conftest.py` — `fake_gateway` fixture:
  ```python
  class FakeGateway:
      type = "fake"
      def __init__(self): 
          self.sent_messages = []
          self.streams = []
          ...
      async def send_text(self, chat_id, text, **kw):
          self.sent_messages.append((chat_id, text))
          return f"msg{len(self.sent_messages)}"
      ...
  ```
- [ ] Step 7.2 — `tests/test_channels_telegram.py` — `TelegramGateway`가 PTB Update를 ChannelEvent로 정확히 변환. 모든 게이트웨이 메서드가 PTB API를 호출함을 mock으로 검증.
- [ ] Step 7.3 — `tests/test_channels_base.py` — Protocol 적합성, ChannelEvent 직렬화.
- [ ] Step 7.4 — `tests/test_handlers_commands.py` — 17개 명령 핸들러를 FakeGateway로 호출 → 기대 발송 메시지 확인.
- [ ] Step 7.5 — `tests/test_handlers_messages.py` — 메시지·파일 핸들러 + FakeGateway.
- [ ] Step 7.6 — `tests/test_handlers_groups.py` — 그룹 라우팅 결정.
- [ ] Step 7.7 — `tests/test_config.py` — 레거시 `token:` → `channel:` 자동 마이그레이션.

### Phase 8 — 문서화

- [ ] Step 8.1 — `CLAUDE.md` Core Modules 표 업데이트 (`channels/`, `handlers/` 패키지 도입).
- [ ] Step 8.2 — `docs/ARCHITECTURE.md` — 채널 어댑터 다이어그램 (Mermaid). bot.yaml 새 스키마 명세.
- [ ] Step 8.3 — `docs/TECHNICAL-NOTES.md` — "Channel adapter" 섹션 신설. 이벤트 모델, 디스패치, 스트리밍 어댑팅, 마이그레이션 절차.
- [ ] Step 8.4 — `README.md` — bot.yaml 예제 새 스키마.
- [ ] Step 8.5 — `docs/SECURITY.md` — 토큰 저장 위치는 변경 없음 (`channel.token` 필드). 토큰 마스킹 정책 재확인.

### Phase 9 — 검증

- [ ] Step 9.1 — `make lint && make test` 통과.
- [ ] Step 9.2 — 기존 봇 1개로 회귀 검증:
  - 텍스트 메시지 정상 처리.
  - 슬래시 명령 17개 모두 동작 확인 (수동 체크리스트).
  - 파일 업로드/다운로드.
  - 스트리밍 모드 (sendMessageDraft) 확인.
  - 그룹 모드 (오케스트레이터/멤버) 메시지 라우팅.
  - 크론 잡 실행 → 메시지 도착.
  - 하트비트 발송.
- [ ] Step 9.3 — abysscope 대시보드에서 봇 상세 페이지 정상 렌더링 (채널 칩 표시).
- [ ] Step 9.4 — 기존 사용자 시뮬레이션: 레거시 `token:` 필드만 있는 bot.yaml을 두고 봇 시작 → 자동으로 새 스키마로 저장됨 확인.

---

## 5. 테스트 계획

### 단위 테스트

#### `tests/test_channels_telegram.py`
- [ ] 케이스 1: `_to_event` — 텍스트 메시지 → ChannelEvent 필드 정확.
- [ ] 케이스 2: `_to_event` — 명령 메시지 (`/cancel`) → text가 그대로 보존.
- [ ] 케이스 3: `_to_event` — 그룹 메시지 + 봇 @mention → `is_mention=True`.
- [ ] 케이스 4: `_to_event` — DM → `is_dm=True`, 그룹 → `is_dm=False`.
- [ ] 케이스 5: `_to_event` — 파일 첨부 → `files` 채워짐.
- [ ] 케이스 6: `send_text` → PTB `bot.send_message` 호출 + reply_to_message_id 매핑.
- [ ] 케이스 7: `send_text` — 4096자 초과 → 자동 분할 (`split_message` 호출).
- [ ] 케이스 8: `send_text` — 마크다운 → HTML 변환 후 발송.
- [ ] 케이스 9: `begin_stream` → MessageStream 인스턴스 반환. `update`는 sendMessageDraft 호출, `finalize`는 마지막 편집.
- [ ] 케이스 10: `begin_stream` — sendMessageDraft 실패 시 editMessageText로 fallback.
- [ ] 케이스 11: `download_file` → 파일 ID로 PTB `getFile` + 다운로드.
- [ ] 케이스 12: `register_commands` → `set_my_commands` 호출.
- [ ] 케이스 13: `start`/`stop` 라이프사이클 — 두 번 start 호출 시 적절한 에러.

#### `tests/test_handlers_commands.py`
- [ ] 케이스 14~30: 17개 명령 (`start`, `help`, `reset`, `resetall`, `files`, `status`, `send`, `model`, `cancel`, `streaming`, `version`, `memory`, `skills`, `cron`, `heartbeat`, `compact`, `bind`, `unbind`) 각각 — FakeGateway 호출 → 기대 응답 메시지 발송 검증.

#### `tests/test_handlers_messages.py`
- [ ] 케이스 31: 텍스트 메시지 → conversation 로깅 + 게이트웨이로 응답 발송.
- [ ] 케이스 32: 파일 메시지 → workspace 다운로드 + Claude 호출 + 응답.
- [ ] 케이스 33: 미인가 사용자 → 게이트웨이로 거부 메시지.
- [ ] 케이스 34: 그룹 메시지 — 봇 @mention 없으면 무시.
- [ ] 케이스 35: 그룹 메시지 — 오케스트레이터 봇은 모든 사용자 메시지 처리.
- [ ] 케이스 36: 스트리밍 모드 — `begin_stream` 호출 + 청크별 update.
- [ ] 케이스 37: 비스트리밍 모드 — 최종 응답만 send_text.

#### `tests/test_config.py`
- [ ] 케이스 38: 레거시 `token:` 필드만 있는 bot.yaml 로드 → `channel.token`으로 자동 변환.
- [ ] 케이스 39: 신규 `channel.type=telegram, channel.token=...` bot.yaml 로드 → 그대로.
- [ ] 케이스 40: 신규 스키마 저장 → 디스크 파일이 `channel:` 블록을 가짐.
- [ ] 케이스 41: 미지원 `channel.type=foo` → 명확한 ValueError.

### 통합 테스트

- [ ] 시나리오 1 (`tests/test_bot_manager_integration.py`): 봇 1개 (telegram) 시작 → 메시지 1개 시뮬레이션 → 응답 발송 확인.
- [ ] 시나리오 2: 봇 2개 (둘 다 telegram, 다른 토큰) 동시 시작 → 게이트웨이 인스턴스 2개 독립 동작.
- [ ] 시나리오 3: 봇 시작 → SIGINT → 모든 게이트웨이 graceful stop.
- [ ] 시나리오 4: 그룹 미션 — 오케스트레이터 + 멤버 봇 (둘 다 같은 telegram 채널) → 역할 라우팅 정상.
- [ ] 시나리오 5: 크론 잡 실행 → 게이트웨이 통한 메시지 도착.
- [ ] 시나리오 6: 하트비트 활성 시간 내 → 게이트웨이 통한 메시지.
- [ ] 시나리오 7: 레거시 bot.yaml로 봇 시작 → 자동 마이그레이션 + 정상 동작.

---

## 6. 사이드 이펙트

### 기존 기능에 미치는 영향

| 항목 | 영향 | 대응 |
|---|---|---|
| 기존 봇 동작 | 추상 계층 추가. 기능적 동등성 유지 목표 | Phase 9 회귀 검증 |
| 메시지 처리 지연 | 추상 호출 1단계 | 측정 후 무시 가능 (마이크로초) |
| `handlers.py` import 경로 | 모든 사이트 변경 | 검색·치환으로 일괄 처리. mypy/ruff가 깨진 import 잡음 |
| `cron.py` / `heartbeat.py` 메시지 발송 | 게이트웨이 lookup으로 변경 | 모듈 레벨 게이트웨이 레지스트리 (`bot_name → gateway`) 도입 |
| abysscope 대시보드 | bot.yaml 스키마 변화 | `lib/abyss.ts` + 페이지 컴포넌트 수정 |
| 사용자 토큰 위치 | `token:` → `channel.token` | 자동 마이그레이션 |
| docs 예제 | 모두 새 스키마로 업데이트 | Phase 8 문서화 |

### 하위 호환성

- bot.yaml 레거시 스키마 자동 마이그레이션 — 사용자 액션 불필요.
- 마이그레이션 후 첫 저장에서 디스크 파일이 신규 스키마로 갱신.
- 외부 코드가 `bot_config["token"]`을 직접 읽는 경우 없는지 확인 → grep으로 잡음.

### 마이그레이션 필요 여부

- 자동 (load 시 변환). 강제 마이그레이션 명령 (`abyss migrate`)은 추가하지 않음.
- 사용자 안내: 첫 부팅 로그에 "Migrated <bot> to channel schema" 표시.

### 운영/배포

- 의존성 변경 없음.
- 패키지 구조 변경 → wheel 다시 빌드. force-include 영향 없음.
- 신규 사용자: `abyss bot add` 흐름이 채널 선택 단계 한 줄 추가됨.

---

## 7. 보안 검토

### OWASP Top 10 관련

| 항목 | 적용 여부 | 검토 |
|---|---|---|
| A01 Broken Access Control | 검토 필요 | `_should_handle_group_message`, `_is_user_allowed` 로직이 `handlers/groups.py`로 이동. 동작은 변경 없음 |
| A02 Cryptographic Failures | 검토 필요 | 토큰 저장 위치만 `channel.token`으로 변경. 평문 YAML 저장은 기존과 동일 (`docs/SECURITY.md`에 이미 finding) |
| A03 Injection | 낮음 | ChannelEvent → 핸들러 흐름에 SQL/명령어 삽입 경로 없음 (마크다운 본문은 Claude에 전달, abyss는 실행 안 함) |
| A04 Insecure Design | 검토 필요 | 게이트웨이 인터페이스가 채널 구현 상세 (rate limit, retry)을 가림 — 각 어댑터가 책임짐 |
| A05 Security Misconfiguration | 낮음 | 신규 설정 키 (`channel.type`) — 미지원 값은 즉시 ValueError |
| A06 Vulnerable Components | 변경 없음 | python-telegram-bot 그대로 |
| A07 Authn Failures | 검토 필요 | `validate_credentials` 어댑터별 구현 — Telegram의 `getMe` 호출 그대로 |
| A08 Software/Data Integrity | 검토 필요 | 자동 마이그레이션이 기존 bot.yaml 덮어씀. 마이그레이션 전 백업 권장 → 부팅 시 `bot.yaml.bak` 자동 생성 |
| A09 Logging Failures | 낮음 | 마이그레이션 로그 레벨 INFO. 토큰은 절대 로그하지 않음 (어댑터 단위 검증) |
| A10 SSRF | 낮음 | 게이트웨이가 외부 API를 호출 — 어댑터별 endpoint는 라이브러리 책임 |

### 인증/인가 변경

- 사용자 화이트리스트 (`allowed_users`) 동작 변경 없음. ChannelEvent의 `user_id`가 화이트리스트 키.
- 토큰 검증 흐름 동일. Telegram 어댑터의 `validate_credentials`가 기존 `validate_telegram_token` 동등.

### 민감 데이터 처리

- bot.yaml에 토큰 평문 저장 — 기존과 동일.
- abysscope 대시보드의 채널 표시 시 토큰 **마스킹** 필수 (`***0123` 형태). UI에 노출 금지.
- 로그에 토큰이 들어가는 코드 경로가 있는지 어댑터 작성 시 점검 (특히 에러 메시지).

### PCI-DSS 영향

- 해당 없음.

### 추가 위협 모델링

- **위협**: 마이그레이션 코드의 버그로 토큰 손실.
  - **완화**: 마이그레이션 전 `bot.yaml.bak` 자동 백업. Phase 9 검증에 명시.
- **위협**: 어댑터 사이의 동작 차이 (예: Telegram의 chat_id가 음수 정수, Slack은 문자열) — 통일 안 하면 핸들러 로직 깨짐.
  - **완화**: ChannelEvent에서 chat_id/user_id를 항상 `str`로 정규화. 핸들러는 문자열 가정.
- **위협**: 게이트웨이가 종료되지 않고 좀비 상태로 남음.
  - **완화**: `stop()` 메서드 + signal_handler에서 `gather` + `timeout`. 어댑터 단위 테스트로 종료 검증.

---

## 8. 완료 조건 체크리스트

- [ ] Phase 1~9 구현 단계 100% 완료
- [ ] 단위 테스트 케이스 1~41 통과
- [ ] 통합 테스트 시나리오 1~7 통과
- [ ] `make lint` 통과
- [ ] `make test` 통과
- [ ] 회귀 검증 체크리스트 (Phase 9.2) 모두 통과
- [ ] abysscope 대시보드 렌더링 정상 (Phase 9.3)
- [ ] 자동 마이그레이션 검증 (Phase 9.4)
- [ ] 사이드이펙트 표 항목 모두 "해당 없음" 또는 "대응 완료"
- [ ] 보안 검토 항목 모두 "검토 완료" 또는 "대응 완료"
- [ ] 문서 (`CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/TECHNICAL-NOTES.md`, `README.md`, `docs/SECURITY.md`) 갱신
- [ ] 본 문서 status를 `done`으로 변경

## 9. 중단 기준

- 핸들러 분할 중 기능적 회귀가 발견되어 단순 수정으로 복구 불가능한 경우 (예: 그룹 라우팅이 깨지는데 원인이 ChannelEvent 모델 자체에 있는 경우).
- bot.yaml 자동 마이그레이션이 기존 사용자 데이터를 손상시키는 시나리오가 발견된 경우.
- 추상 계층이 스트리밍 응답 지연을 의미 있게(>50 ms) 늘리는 것이 측정된 경우.
- → 즉시 중단, plan 업데이트, 사용자 리뷰.
