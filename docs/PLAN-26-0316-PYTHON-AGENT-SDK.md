# Plan: Node.js Bridge → Python Agent SDK 전환

> **Date**: 2026-03-16
> **Branch**: `feature/python-agent-sdk`
> **Status**: Planning

## 배경

cclaw은 Claude Code와 통신하기 위해 두 가지 경로를 사용한다:

1. **subprocess** — `claude -p` 프로세스를 매번 스폰
2. **Node.js bridge** — `@anthropic-ai/claude-agent-sdk`의 v1 `query()`를 호출하는 상주 Node.js 프로세스 (Unix socket JSONL)

Node.js bridge가 필요했던 이유는 Agent SDK가 TypeScript/Node.js 패키지로만 존재했기 때문이다. 이제 **Python Agent SDK (`claude-agent-sdk`)**가 정식 출시되어 bridge 레이어를 제거하고 Python에서 직접 호출할 수 있다.

## 목표

- Node.js bridge (`bridge.py`, `bridge/server.mjs`, `bridge_data/`) 제거
- Python `claude-agent-sdk`의 `ClaudeSDKClient`로 대체
- 기존 fallback 구조(bridge → subprocess) 유지하되, bridge 대신 SDK client 사용
- 테스트 커버리지 유지

## Python Agent SDK 핵심 API

```python
# 일회성 쿼리
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(prompt="...", options=ClaudeAgentOptions(...)):
    print(message)

# 세션 유지 (대화 계속)
from claude_agent_sdk import ClaudeSDKClient

async with ClaudeSDKClient(options=ClaudeAgentOptions(...)) as client:
    await client.connect("첫 메시지")
    async for message in client.receive_response():
        ...
    await client.query("후속 메시지")  # 같은 세션, 컨텍스트 유지
    async for message in client.receive_response():
        ...
```

### query() vs ClaudeSDKClient

| 기능 | `query()` | `ClaudeSDKClient` |
|---|---|---|
| 세션 | 매번 새로 생성 | 동일 세션 재사용 |
| 대화 계속 | 불가 | 가능 |
| 인터럽트 | 불가 | 가능 (`client.interrupt()`) |
| 커스텀 도구/훅 | 불가 | 가능 |

### 이점

1. **Node.js/npm 의존성 제거** — 런타임에 Node.js 불필요
2. **브리지 프로세스 관리 제거** — 소켓, 프로세스 수명주기, 드레인 스레드 등 불필요
3. **진짜 세션 유지** — `ClaudeSDKClient`로 프로세스 재스폰 없이 메시지 추가
4. **인터럽트 지원** — `/cancel` 명령에서 `client.interrupt()` 사용 가능
5. **커스텀 도구/훅** — `@tool` 데코레이터로 Python 함수를 MCP 도구로 등록 가능
6. **코드 단순화** — bridge.py (420줄) + server.mjs (249줄) + bridge_data/ 제거

## 영향 범위

### 제거 대상

| 파일 | 설명 |
|---|---|
| `src/cclaw/bridge.py` | Bridge client (420줄) |
| `bridge/server.mjs` | Node.js bridge 서버 (249줄) |
| `bridge/package.json` | npm 의존성 |
| `src/cclaw/bridge_data/server.mjs` | 패키지 번들용 복사본 |
| `src/cclaw/bridge_data/package.json` | 패키지 번들용 복사본 |
| `tests/test_bridge.py` | Bridge 테스트 |

### 수정 대상

| 파일 | 변경 내용 |
|---|---|
| `src/cclaw/claude_runner.py` | `run_claude_with_bridge()`, `run_claude_streaming_with_bridge()` → SDK client 호출로 교체 |
| `src/cclaw/bot_manager.py` | bridge 시작/종료 로직 제거, SDK client 수명주기로 교체 |
| `src/cclaw/handlers.py` | import 경로 변경 (함수 시그니처는 유지) |
| `src/cclaw/onboarding.py` | bridge health check 제거 |
| `src/cclaw/cli.py` | bridge 관련 서브커맨드 정리 |
| `pyproject.toml` | `claude-agent-sdk` 의존성 추가, bridge 관련 force-include 제거 |
| `tests/test_claude_runner.py` | bridge mock → SDK mock으로 교체 |
| `tests/test_bot_manager.py` | bridge 시작/종료 mock 교체 |

## 구현 단계

### Phase 1: SDK 통합 모듈 생성

1. `pyproject.toml`에 `claude-agent-sdk` 의존성 추가
2. `src/cclaw/sdk_client.py` 신규 생성 — Python SDK 래퍼
   - `SDKClientPool`: 봇별 `ClaudeSDKClient` 인스턴스 관리
   - `sdk_query()`: `bridge_query()` 대체 (non-streaming)
   - `sdk_query_streaming()`: `bridge_query_streaming()` 대체 (streaming)
   - `sdk_close_session()`: 세션 종료
   - fallback: SDK 사용 불가 시 subprocess로 폴백

### Phase 2: claude_runner.py 전환

3. `run_claude_with_bridge()` → `run_claude_with_sdk()` 리네임 및 내부 구현 교체
4. `run_claude_streaming_with_bridge()` → `run_claude_streaming_with_sdk()` 리네임 및 내부 구현 교체
5. 기존 subprocess fallback 로직 유지

### Phase 3: 수명주기 전환

6. `bot_manager.py`에서 bridge 시작/종료 → SDK client pool 시작/종료로 교체
7. `onboarding.py` bridge health check 제거 또는 SDK health check로 교체
8. `cli.py` bridge 관련 정리

### Phase 4: Bridge 코드 제거

9. `bridge.py` 삭제
10. `bridge/` 디렉토리 삭제
11. `bridge_data/` 디렉토리 삭제
12. `pyproject.toml`에서 bridge force-include 제거

### Phase 5: 테스트

13. `tests/test_sdk_client.py` 신규 생성
14. `tests/test_claude_runner.py` SDK mock으로 업데이트
15. `tests/test_bot_manager.py` SDK lifecycle mock으로 업데이트
16. `tests/test_bridge.py` 삭제
17. 전체 테스트 통과 확인

### Phase 6: 문서 업데이트

18. `CLAUDE.md` — bridge 관련 설명 제거, SDK client 설명 추가
19. `docs/ARCHITECTURE.md` — 아키텍처 다이어그램 업데이트
20. `docs/TECHNICAL-NOTES.md` — bridge 프로토콜 섹션 → SDK client 섹션으로 교체

## 세션 관리 설계

### 현재 (bridge)

```
메시지 → bridge_query(session_key, prompt, cwd, session_id, resume)
       → Unix socket → Node.js → SDK query() → Claude API
       → 응답 텍스트 반환
```

매 쿼리마다 SDK 내부에서 Claude Code 프로세스 스폰. `--resume`으로 세션 이어감.

### 변경 후 (Python SDK)

```
첫 메시지 → ClaudeSDKClient.connect(prompt) → Claude API → 응답
후속 메시지 → ClaudeSDKClient.query(prompt) → Claude API → 응답 (같은 세션)
```

프로세스 재스폰 없이 동일 세션에서 대화 계속. 봇별로 `ClaudeSDKClient` 인스턴스 유지.

### SDKClientPool 설계

```python
class SDKClientPool:
    """봇별 ClaudeSDKClient 인스턴스를 관리한다."""

    _clients: dict[str, ClaudeSDKClient]  # key: session_key (e.g. "chat_12345")

    async def get_or_create(self, session_key, options) -> ClaudeSDKClient
    async def close_session(self, session_key) -> None
    async def close_all(self) -> None
```

## 리스크

| 리스크 | 대응 |
|---|---|
| Python SDK가 CLAUDE.md를 자동으로 읽지 않을 수 있음 | `system_prompt` 옵션으로 직접 주입, `setting_sources` 옵션 확인 |
| SDK가 Bash/Read/Write 도구를 지원하지 않을 수 있음 | SDK 문서에서 `permission_mode`, `allowed_tools` 확인 필요. 미지원 시 subprocess fallback 유지 |
| ClaudeSDKClient 세션이 오래 유지되면 메모리 누수 | 일정 시간/메시지 수 후 세션 재생성 |
| claude-agent-sdk 패키지가 아직 불안정할 수 있음 | subprocess fallback을 항상 유지 |

## 검증 항목

- [ ] `uv run pytest` 전체 통과
- [ ] `uv run ruff check . && uv run ruff format .` 통과
- [ ] 단일 봇 메시지 송수신 정상
- [ ] 세션 연속성 (후속 메시지에서 이전 컨텍스트 기억)
- [ ] 스트리밍 응답 정상
- [ ] `/cancel` 인터럽트 정상
- [ ] `/reset` 세션 초기화 정상
- [ ] Cron/Heartbeat 정상 동작
- [ ] Group collaboration 정상 동작
- [ ] SDK 불가 시 subprocess fallback 정상
- [ ] Node.js 미설치 환경에서 정상 동작

## 의존성 변경

```toml
# pyproject.toml
[project]
dependencies = [
    # 추가
    "claude-agent-sdk>=0.1.0",
    # 기존 유지
    ...
]

# 제거
[tool.hatch.build.force-include]
# "bridge/server.mjs" = "..." 제거
# "bridge/package.json" = "..." 제거
```
