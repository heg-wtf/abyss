# Plan: LLM backend abstraction with OpenRouter adapter

- date: 2026-04-25
- status: draft
- author: claude
- approved-by: (pending)

---

## 1. 목적 및 배경

### 문제 정의

abyss는 LLM 백엔드를 Claude Code (CLI 서브프로세스 + Agent SDK)에 강하게 결합되어 있다.

- `claude_runner.py:run_claude`, `run_claude_streaming` (라인 145, 353) — `claude -p` 서브프로세스 호출
- `claude_runner.py:run_claude_with_sdk`, `run_claude_streaming_with_sdk` (라인 531, 611) — `claude-agent-sdk`의 `query`/`SDKClientPool` 사용
- `handlers.py:_call_with_resume_fallback` (라인 697) — 위 4개 함수를 직접 호출
- `bot.yaml`의 `model:` 필드는 항상 Claude 모델 ID (opus / sonnet / haiku) 가정

이 결합 때문에 다음이 불가능하다.

1. 더 저렴하거나 빠른 모델 (DeepSeek, Qwen, GPT-5-mini, Gemini 등) 사용.
2. Claude API 한도에 도달했을 때 fallback.
3. 봇 단위로 모델 제공자 분리 (botA = Claude, botB = GPT-4o).
4. 비용 민감한 use case에 별도 백엔드 적용 (예: 단순 응답 봇은 haiku급 OSS 모델).

### 동기

비교 분석 (`docs/comparisons/Comparison-Hermes-OpenClaw-Abyss`)에서 가장 자주 언급된 차이가 **모델 이식성**이다. Hermes는 200+ 모델을 `hermes model` 한 번으로 전환한다. 사용자 베이스가 이 기능을 원한다는 것이 이미 검증됨.

abyss의 베팅("Claude Code가 두뇌")은 유지하되, **백엔드 추상**을 만들어 봇별로 다른 LLM 제공자를 선택할 수 있게 한다. OpenRouter는 단일 API로 200+ 모델 게이트웨이라서 한 어댑터로 폭넓은 모델 풀을 얻는다.

### 솔직한 한계 (사용자에게 명시할 것)

OpenRouter는 **단순 LLM API** (OpenAI 호환). Claude Code의 에이전트 하니스가 아니다. 따라서 OpenRouter 백엔드는 다음을 **잃는다**.

| 기능 | Claude Code 백엔드 | OpenRouter 백엔드 |
|---|---|---|
| 빌트인 도구 (Read/Write/Edit/Bash/Grep/Glob) | ✅ | ❌ |
| MCP 서버 도구 호출 | ✅ | ❌ (1차 릴리즈) |
| 스킬 (mcp.json 포함) | ✅ | 마크다운만 시스템 프롬프트로 (도구 없음) |
| 세션 resume (`--resume`) | ✅ | 직접 메시지 히스토리 관리 (.md 로그에서 N개 replay) |
| 서브에이전트 spawning | ✅ | ❌ |
| 토큰 압축 워크플로 | ✅ (token_compact.py) | 동작은 하지만 효과 제한 (도구 호출 없음) |
| 회상 검색 (conversation_search MCP) | ✅ (plan 1에서 추가) | ❌ (1차 릴리즈) |

**1차 릴리즈 OpenRouter 백엔드는 "단순 채팅 봇" 한정.** 사용자가 봇 추가 시 명시적으로 알린다. 도구 호출이 필요한 봇은 Claude Code 백엔드 유지 (기본).

### 비목표 (out of scope)

- OpenRouter에서 OpenAI function calling으로 MCP 도구 호출 (후속 plan).
- 다중 백엔드 fallback 자동화 (Claude 한도 초과 시 자동 OpenRouter 전환). 봇 단위 명시 선택만.
- LiteLLM 같은 멀티 제공자 게이트웨이 도입. OpenRouter 1개 어댑터로 충분.
- 자체 호스팅 모델 (Ollama, vLLM). 본 plan은 OpenRouter HTTP 엔드포인트만.
- `hermes model` 같은 인터랙티브 모델 스위처. 봇별 설정 기반.

---

## 2. 예상 임팩트

### 영향받는 모듈

| 모듈 | 변경 종류 | 비고 |
|---|---|---|
| `src/abyss/llm/__init__.py` | 신규 | 백엔드 레지스트리 |
| `src/abyss/llm/base.py` | 신규 | `LLMBackend` Protocol, `LLMRequest`, `LLMResult`, `LLMStreamChunk` |
| `src/abyss/llm/claude_code.py` | 신규 | `ClaudeCodeBackend` — 기존 claude_runner 함수 캡슐화 |
| `src/abyss/llm/openrouter.py` | 신규 | `OpenRouterBackend` — httpx 기반 async chat completions |
| `src/abyss/llm/registry.py` | 신규 | `get_backend(bot_config)` 헬퍼 |
| `src/abyss/handlers/messages.py` | 수정 | `_call_with_resume_fallback` 등 → `backend.run()` / `backend.run_streaming()` |
| `src/abyss/cron.py` | 수정 | 크론 잡도 backend.run() 사용 |
| `src/abyss/heartbeat.py` | 수정 | 동일 |
| `src/abyss/token_compact.py` | 수정 | 백엔드별 압축 가능 — Claude Code는 기존, OpenRouter는 단순 LLM 요약 |
| `src/abyss/onboarding.py` | 수정 | 봇 추가 시 백엔드 선택 단계 + OpenRouter 모델 선택 |
| `src/abyss/config.py` | 수정 | bot.yaml 스키마 — `backend` 블록 추가, 기존 `model:` 필드는 claude_code 백엔드일 때만 의미 있음 |
| `src/abyss/cli.py` | 수정 | `abyss model list` 명령 (옵션) — 사용 가능 백엔드 + 모델 표시 |
| `pyproject.toml` | 수정 | `httpx>=0.27.0` 명시적 추가 (이미 transitive로 들어옴 — 명시화) |
| `tests/test_llm_*.py` | 신규 | 단위 + 통합 테스트 |
| `abysscope/lib/abyss.ts` | 수정 | 봇 백엔드 정보 표시 |
| `abysscope/src/app/bots/[name]/page.tsx` | 수정 | 백엔드 칩, OpenRouter 시 모델 표시 |

### API/인터페이스 변경

- 신규 bot.yaml 필드 `backend.type`. 미설정 시 `claude_code` (기본).
- 신규 환경 변수 (옵션): `OPENROUTER_API_KEY` (기본 키 이름).
- handlers/cron/heartbeat의 LLM 호출 경로가 `backend.run(...)`으로 통일됨 (내부 API).

### 성능

- Claude Code 백엔드: 기존 동작 유지. 추상 호출 1단계 추가 (마이크로초 단위).
- OpenRouter 백엔드: 응답 지연 = 모델 + 네트워크. haiku급은 ~500ms first token, opus급은 ~2s. Claude Code 서브프로세스 spawn (~1s)을 절약하므로 일부 모델은 더 빠름.
- 메시지 히스토리 replay: N개 (default 20) 마크다운 파싱 → 파일 I/O ~10ms.

### 사용자 경험 변화

- 기본은 변경 없음 (Claude Code 백엔드).
- 새 봇 추가 시 "Backend: Claude Code (default) / OpenRouter" 선택 단계 등장.
- OpenRouter 봇은 도구 사용 없는 단순 채팅 — 사용자에게 onboarding에서 명시 안내.

### 가용성

- `slack-bolt`처럼 휠 크기 영향 미미 (`httpx`는 이미 transitive).
- OpenRouter API 자체의 가용성은 외부 의존 — 사용자가 인지하고 선택.

---

## 3. 구현 방법 비교

### 방법 A: 백엔드 Protocol + 봇별 명시 선택 (선택)

- `LLMBackend` Protocol 정의.
- `ClaudeCodeBackend`, `OpenRouterBackend` 두 구현.
- 봇 단위로 `bot.yaml`의 `backend.type`으로 선택.
- 한계 명시: OpenRouter는 도구 없음 (사용자가 알고 선택).

**장점**
- 명확한 책임 분리.
- 봇별 독립 설정.
- 향후 백엔드 추가 (Anthropic API direct, OpenAI direct, Gemini direct, Ollama)에 동일 패턴 사용.

**단점**
- 추상 인터페이스 설계 비용.
- Claude Code 고유 기능 (resume, MCP, 서브에이전트)을 인터페이스가 표현 못 함 → 백엔드별로 동작이 다르다는 점을 명시해야 함.

### 방법 B: LiteLLM 도입

- LiteLLM (litellm 패키지)이 100+ 제공자를 통합 인터페이스로 제공.
- `litellm.completion(model="anthropic/claude-3-haiku", ...)` 같은 호출.

**장점**
- 더 많은 제공자.

**단점**
- 의존성 무거움 (~30 MB, 많은 transitive deps).
- abyss의 Claude Code 워크플로 (서브프로세스 + Agent SDK)와 LiteLLM은 직접 호환되지 않음 → 결국 같은 어댑터 코드를 써야 함. 이득 작음.
- OpenRouter 자체가 이미 게이트웨이 — 중복.

### 방법 C: claude-agent-sdk가 OpenAI 호환 endpoint 받게 설정

- 일부 SDK는 base_url 변경으로 다른 제공자 사용 가능.

**장점**
- 코드 변경 최소.

**단점**
- `claude-agent-sdk`는 Anthropic 제공자 전용 — OpenRouter로 변경 안 됨 (확인 시점 2026-04-25).
- Claude 메시지 형식과 OpenAI 형식이 다름.

### 결론

**방법 A 선택.** OpenRouter HTTP API 직접 호출 (의존성 가벼움) + 명시적 백엔드 선택. 추상 인터페이스가 향후 다른 어댑터의 토대.

---

## 4. 구현 단계

### Phase 1 — 추상 타입

- [ ] Step 1.1 — `src/abyss/llm/__init__.py` 패키지 시작.
- [ ] Step 1.2 — `src/abyss/llm/base.py`:
  ```python
  from typing import Protocol, ClassVar, AsyncIterator, Awaitable, Callable, Any
  from dataclasses import dataclass, field
  from pathlib import Path

  @dataclass(frozen=True, slots=True)
  class LLMRequest:
      bot_name: str
      session_directory: Path
      bot_config: dict
      attached_skills: list[str]
      system_prompt: str        # composed CLAUDE.md content
      user_prompt: str
      images: tuple[Path, ...] = ()
      session_key: str | None = None  # for cancel
      max_history: int = 20

  @dataclass(frozen=True, slots=True)
  class LLMResult:
      text: str
      input_tokens: int | None = None
      output_tokens: int | None = None
      session_id: str | None = None    # claude_code 만 의미
      stop_reason: str | None = None
      raw: Any = None

  class LLMBackend(Protocol):
      type: ClassVar[str]   # "claude_code" | "openrouter"

      async def run(self, req: LLMRequest) -> LLMResult: ...
      async def run_streaming(
          self,
          req: LLMRequest,
          on_chunk: Callable[[str], Awaitable[None]],
      ) -> LLMResult: ...
      async def cancel(self, session_key: str) -> bool: ...
      async def supports_tools(self) -> bool: ...
      async def supports_session_resume(self) -> bool: ...
  ```
- [ ] Step 1.3 — `src/abyss/llm/registry.py`:
  ```python
  BACKENDS: dict[str, type[LLMBackend]] = {}

  def register(name: str, cls: type[LLMBackend]) -> None: ...
  def get_backend(bot_config: dict) -> LLMBackend: ...   # reads bot_config["backend"]["type"]
  ```

### Phase 2 — Claude Code 백엔드 (현행 유지)

- [ ] Step 2.1 — `src/abyss/llm/claude_code.py`:
  ```python
  class ClaudeCodeBackend:
      type = "claude_code"
      
      def __init__(self, bot_name: str, backend_config: dict):
          self.bot_name = bot_name
          self.use_sdk = is_sdk_available()  # from sdk_client
      
      async def run(self, req):
          if self.use_sdk:
              return await self._run_sdk(req)
          return await self._run_subprocess(req)
      
      async def run_streaming(self, req, on_chunk):
          if self.use_sdk:
              return await self._run_streaming_sdk(req, on_chunk)
          return await self._run_streaming_subprocess(req, on_chunk)
      
      async def cancel(self, session_key):
          # SDK pool interrupt + subprocess fallback
          ...
      
      async def supports_tools(self): return True
      async def supports_session_resume(self): return True
  ```
- [ ] Step 2.2 — 기존 `claude_runner.py`의 `run_claude`, `run_claude_streaming`, `run_claude_with_sdk`, `run_claude_streaming_with_sdk` 호출을 메서드 내부에서 wrap. 시그니처 매핑.
- [ ] Step 2.3 — `register("claude_code", ClaudeCodeBackend)`.

### Phase 3 — OpenRouter 백엔드

- [ ] Step 3.1 — `src/abyss/llm/openrouter.py`:
  ```python
  class OpenRouterBackend:
      type = "openrouter"

      def __init__(self, bot_name: str, backend_config: dict):
          self.bot_name = bot_name
          self.api_key_env = backend_config.get("api_key_env", "OPENROUTER_API_KEY")
          self.model = backend_config["model"]
          self.max_history = backend_config.get("max_history", 20)
          self.max_tokens = backend_config.get("max_tokens", 4096)
          self.base_url = backend_config.get("base_url", "https://openrouter.ai/api/v1")
          self._client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0))
          self._tasks: dict[str, asyncio.Task] = {}
      
      async def run(self, req):
          messages = self._build_messages(req)
          payload = {
              "model": self.model,
              "messages": messages,
              "max_tokens": self.max_tokens,
              "stream": False,
          }
          headers = self._auth_headers()
          response = await self._client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
          response.raise_for_status()
          data = response.json()
          text = data["choices"][0]["message"]["content"]
          usage = data.get("usage", {})
          return LLMResult(
              text=text,
              input_tokens=usage.get("prompt_tokens"),
              output_tokens=usage.get("completion_tokens"),
              stop_reason=data["choices"][0].get("finish_reason"),
              raw=data,
          )
      
      async def run_streaming(self, req, on_chunk):
          payload = {... "stream": True}
          accumulated = []
          async with self._client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as response:
              response.raise_for_status()
              async for line in response.aiter_lines():
                  if not line.startswith("data: "): continue
                  data_str = line[6:].strip()
                  if data_str == "[DONE]": break
                  data = json.loads(data_str)
                  delta = data["choices"][0].get("delta", {}).get("content")
                  if delta:
                      accumulated.append(delta)
                      await on_chunk(delta)
          full_text = "".join(accumulated)
          return LLMResult(text=full_text, ...)

      async def cancel(self, session_key):
          task = self._tasks.get(session_key)
          if task and not task.done():
              task.cancel()
              return True
          return False

      async def supports_tools(self): return False  # 1차 릴리즈
      async def supports_session_resume(self): return False
  ```
- [ ] Step 3.2 — `_build_messages(req)` — 시스템 프롬프트 + 마크다운 히스토리 N개 + 현재 prompt:
  ```python
  def _build_messages(self, req):
      messages = [{"role": "system", "content": req.system_prompt}]
      history = self._load_history(req.session_directory, limit=req.max_history)
      messages.extend(history)
      user_content = self._build_user_content(req)
      messages.append({"role": "user", "content": user_content})
      return messages
  ```
- [ ] Step 3.3 — `_load_history(session_directory, limit)` — 가장 최근 conversation-YYMMDD.md 읽기, 헤더 마커 (`## YYYY-MM-DD HH:MM:SS user|assistant`) 파싱, 마지막 N개 turn 추출 → OpenAI message 형식.
- [ ] Step 3.4 — 이미지 첨부: `req.images`가 있으면 OpenRouter의 vision 형식 (`{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`) — base64 인코딩.
- [ ] Step 3.5 — `_auth_headers()`:
  ```python
  api_key = os.getenv(self.api_key_env)
  if not api_key:
      raise RuntimeError(f"{self.api_key_env} not set")
  return {"Authorization": f"Bearer {api_key}", "HTTP-Referer": "https://abyss.heg.wtf", "X-Title": "abyss"}
  ```
- [ ] Step 3.6 — 에러 처리: 4xx (인증/할당량), 5xx (모델 일시 장애), timeout. 로그 + 사용자에게 명확한 메시지.
- [ ] Step 3.7 — `register("openrouter", OpenRouterBackend)`.
- [ ] Step 3.8 — `close()` 메서드 — `_client.aclose()`. abyss 종료 시 호출.

### Phase 4 — 호출 사이트 리팩터

- [ ] Step 4.1 — `handlers/messages.py:_call_with_resume_fallback` — `backend.run` / `run_streaming` 호출로 변경. 시그니처는 `LLMRequest`로 통일.
  - 기존 resume fallback 로직은 ClaudeCodeBackend 내부로 이전 (`run_streaming`이 내부에서 retry).
- [ ] Step 4.2 — `_send_streaming_response`, `_send_non_streaming_response` — 백엔드 추출 후 호출.
- [ ] Step 4.3 — `cron.py` — 크론 잡 메시지 처리도 `backend.run()` 통과.
- [ ] Step 4.4 — `heartbeat.py` — 동일.
- [ ] Step 4.5 — `token_compact.py` — Claude Code 백엔드일 때는 기존 `claude -p` 호출, OpenRouter일 때는 단순 LLM 요약 프롬프트 (시스템: "Compact this content to 2000 tokens", 사용자: 원본).

### Phase 5 — 스키마 + 온보딩

- [ ] Step 5.1 — bot.yaml 스키마 변경:
  ```yaml
  # 기본 (claude_code, 변경 없음 동작)
  model: opus
  
  # OpenRouter
  backend:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY
    model: anthropic/claude-haiku-4.5
    max_history: 20
    max_tokens: 4096
  ```
  `backend` 미설정 시 `{type: "claude_code"}`로 fallback.
- [ ] Step 5.2 — `config.py:load_bot_config` — backend 필드 누락 시 기본값 주입 (in-memory).
- [ ] Step 5.3 — `onboarding.py:add_bot` — 백엔드 선택 단계 추가:
  - 옵션: "Claude Code (default, full agent)" / "OpenRouter (simple chat, 200+ models)".
  - OpenRouter 선택 시: API 키 환경 변수 이름 입력 (기본 `OPENROUTER_API_KEY`), 모델 ID 입력.
  - OpenRouter 한계 안내문 출력 (도구 없음, 검색 없음, 등).
- [ ] Step 5.4 — `cli.py` — 신규 `abyss model list` 옵션 (백엔드별 사용 가능 모델 표시 — Claude Code는 정해진 alias, OpenRouter는 자유 입력 안내).

### Phase 6 — abysscope 대시보드

- [ ] Step 6.1 — `abysscope/lib/abyss.ts` — 봇 백엔드 type 표시.
- [ ] Step 6.2 — 봇 상세 페이지에 백엔드 칩 (`Claude Code` / `OpenRouter`). OpenRouter 시 모델, max_history, max_tokens 표시.
- [ ] Step 6.3 — 백엔드 변경 UI는 1차 릴리즈에서 제외 (CLI만). YAML 직접 편집 또는 `abyss bot edit` 후속.

### Phase 7 — 테스트

- [ ] Step 7.1 — `tests/test_llm_base.py` — Protocol 적합성, 데이터클래스 직렬화.
- [ ] Step 7.2 — `tests/test_llm_claude_code.py` — `ClaudeCodeBackend`가 기존 `claude_runner` 함수를 적절히 호출하는지 mock 검증. 회귀 방지.
- [ ] Step 7.3 — `tests/test_llm_openrouter.py` — `OpenRouterBackend`:
  - mock httpx + `_build_messages` 결과 검증.
  - 스트리밍 SSE 파싱.
  - 인증 헤더 누락 시 RuntimeError.
  - 4xx/5xx 에러 처리.
  - cancel — task.cancel 호출.
- [ ] Step 7.4 — `tests/evaluation/test_openrouter_eval.py` — 실 OpenRouter 호출 (API 키 환경 변수 게이트, CI 제외).
- [ ] Step 7.5 — `tests/test_handlers_messages.py` — 백엔드별 분기 (FakeBackend로):
  - Claude Code 백엔드 호출 시 기존 동작 유지.
  - OpenRouter 백엔드 호출 시 LLMRequest 정확히 빌드.

### Phase 8 — 문서화

- [ ] Step 8.1 — `CLAUDE.md` — Tech Stack에 "LLM Backends: Claude Code (default), OpenRouter (200+ models)" 추가. bot.yaml 스키마 예제.
- [ ] Step 8.2 — `docs/ARCHITECTURE.md` — LLM 백엔드 다이어그램. 호출 흐름 (handlers → registry → backend.run).
- [ ] Step 8.3 — `docs/TECHNICAL-NOTES.md` — "LLM Backend" 섹션. 백엔드별 기능 매트릭스 표 (Phase 1.2 표 재사용).
- [ ] Step 8.4 — `docs/OPENROUTER_SETUP.md` 신규 — API 키 발급, 추천 모델, 한계, 비용.
- [ ] Step 8.5 — `README.md` — 백엔드 옵션 한 줄 안내.
- [ ] Step 8.6 — `docs/SECURITY.md` — OpenRouter API 키 환경변수 저장. 평문 YAML 노출 위험 추가 finding (api_key 자체는 YAML에 저장 안 함, env var 이름만).

### Phase 9 — 검증

- [ ] Step 9.1 — `make lint && make test` 통과.
- [ ] Step 9.2 — 기존 Claude Code 봇 회귀 검증 (모든 시나리오 동등 동작).
- [ ] Step 9.3 — OpenRouter 봇 신규:
  - `abyss bot add` → OpenRouter 선택 → API 키 + 모델 (`anthropic/claude-haiku-4.5`) → 봇 시작.
  - DM에서 텍스트 메시지 → 응답.
  - 스트리밍 응답 (SSE 청크 단위 update).
  - 5턴 대화 → 히스토리 유지 확인 (5번째 응답이 1번째 메시지 회상).
  - `/cancel` → httpx 스트림 중단.
  - 도구 필요 메시지 ("이 파일 읽어줘") → 모델이 도구 없음을 인지하고 정중히 거부.
- [ ] Step 9.4 — 동시 multi-bot: 봇 A (claude_code, opus) + 봇 B (openrouter, gpt-5-mini) 같은 abyss 프로세스 → 독립 동작.
- [ ] Step 9.5 — Claude API 한도 도달 시뮬레이션 (claude_runner 응답 mock) → 사용자가 봇 B로 fallback 시도 가능.

---

## 5. 테스트 계획

### 단위 테스트 (`tests/test_llm_base.py`)

- [ ] 케이스 1: `LLMRequest` 데이터클래스 — frozen, hashable.
- [ ] 케이스 2: `LLMResult` 직렬화 (대시보드용 추후).
- [ ] 케이스 3: `register` + `get_backend` 라운드트립.

### 단위 테스트 (`tests/test_llm_claude_code.py`)

- [ ] 케이스 4: `ClaudeCodeBackend.run` — SDK 사용 가능 시 `run_claude_with_sdk` 호출.
- [ ] 케이스 5: SDK 미사용 시 `run_claude` (subprocess) 호출.
- [ ] 케이스 6: `run_streaming` — `on_chunk` 콜백 호출 검증.
- [ ] 케이스 7: `cancel` — pool interrupt + subprocess kill 둘 다 시도.
- [ ] 케이스 8: `supports_tools` True, `supports_session_resume` True.

### 단위 테스트 (`tests/test_llm_openrouter.py`)

- [ ] 케이스 9: `_build_messages` — system + history + user 순서.
- [ ] 케이스 10: `_build_messages` — history 길이 N으로 제한.
- [ ] 케이스 11: `_load_history` — 마크다운 헤더 형식 정확히 파싱.
- [ ] 케이스 12: `_load_history` — 손상된 헤더는 무시.
- [ ] 케이스 13: `_auth_headers` — 환경 변수 누락 시 RuntimeError.
- [ ] 케이스 14: `_auth_headers` — Bearer + Referer + Title 헤더.
- [ ] 케이스 15: `run` — mock httpx → 응답 텍스트 추출, usage 매핑.
- [ ] 케이스 16: `run_streaming` — SSE 청크 4개 mock → on_chunk 4회 호출 + 누적 결과.
- [ ] 케이스 17: `run_streaming` — `[DONE]` 마커에서 종료.
- [ ] 케이스 18: 4xx (401 invalid key) → 명확한 RuntimeError.
- [ ] 케이스 19: 5xx (502 모델 일시 장애) → 재시도 안 하고 명확한 에러 (사용자가 retry 결정).
- [ ] 케이스 20: 타임아웃 → asyncio.TimeoutError → 명확한 에러.
- [ ] 케이스 21: `cancel` — task.cancel 호출 후 `httpx.stream.aclose` 정리.
- [ ] 케이스 22: `supports_tools` False, `supports_session_resume` False.
- [ ] 케이스 23: 이미지 첨부 — base64 인코딩 + content type 정확.
- [ ] 케이스 24: `close()` — `_client.aclose()` 호출.

### 단위 테스트 (`tests/test_config.py` 확장)

- [ ] 케이스 25: bot.yaml에 backend 필드 없음 → load 시 `{type: claude_code}` 기본값.
- [ ] 케이스 26: backend.type=openrouter → 그대로 보존.
- [ ] 케이스 27: 미지원 backend.type → ValueError.

### 통합 테스트

- [ ] 시나리오 1 (`tests/test_handlers_messages_integration.py`): claude_code 백엔드로 메시지 처리 → 기존 동작 동등.
- [ ] 시나리오 2: openrouter 백엔드로 메시지 처리 — 응답 발송, conversation 로깅.
- [ ] 시나리오 3: 다중 봇 — 백엔드 다른 봇 2개 동시 동작.
- [ ] 시나리오 4: cron 잡 (openrouter 봇) → 응답 메시지 발송.
- [ ] 시나리오 5: heartbeat (openrouter 봇) → 메시지 발송.
- [ ] 시나리오 6: openrouter 봇에 MCP 스킬 부착 시 — onboarding/봇 시작에서 경고 출력.
- [ ] 시나리오 7: token_compact — 백엔드별 동작.

### E2E 테스트 (`tests/evaluation/test_openrouter_eval.py`, CI 제외)

- [ ] 시나리오 E1: 실 OpenRouter API — `anthropic/claude-haiku-4.5`로 한국어 메시지 송수신.
- [ ] 시나리오 E2: 스트리밍 응답 — 청크 단위 도착.
- [ ] 시나리오 E3: 5턴 대화 — 히스토리 컨텍스트 유지.
- [ ] 시나리오 E4: `/cancel` 중간 중단.

---

## 6. 사이드 이펙트

### 기존 기능에 미치는 영향

| 항목 | 영향 | 대응 |
|---|---|---|
| Claude Code 백엔드 동작 | 추상 1단계 추가, 기능 동등 | 회귀 테스트 (Phase 9.2) |
| `claude_runner.py` API | 직접 호출자 → ClaudeCodeBackend로 통일 | 외부 API 아님, grep으로 호출 사이트 일괄 변경 |
| `--resume` 동작 | ClaudeCodeBackend 내부로 캡슐화 | 동작 동등 |
| `/model` 명령 | claude_code 백엔드일 때만 의미. openrouter 봇은 모델 변경이 백엔드 설정 → 명령 응답에 안내 | 명령 핸들러 수정 |
| `token_compact` | 백엔드별 분기 | 명시적 처리 |
| skill MCP | OpenRouter 백엔드는 MCP 서버 띄우지 않음 → 봇 시작 시 경고 | 시작 로그 + 대시보드 표시 |
| conversation_search 자동 주입 (plan 1) | OpenRouter 백엔드는 무의미 — 자동 주입 스킵 | `compose_claude_md`에서 백엔드 type 확인 |
| 봇 메모리 사용 | OpenRouter 봇은 httpx 클라이언트 1개 (~1MB) | 무시 가능 |
| 시작 시간 | OpenRouter 백엔드는 SDK pool 초기화 안 함 | 더 빠름 |

### 하위 호환성

- 기존 bot.yaml에 `backend` 필드 없으면 자동으로 `{type: claude_code}` → 동작 동등.
- 마이그레이션 강제 없음.

### 마이그레이션 필요 여부

- 없음. 기존 봇 그대로.
- 사용자가 OpenRouter로 전환하고 싶으면 bot.yaml 수동 편집 또는 `abyss bot add`로 신규 생성 후 봇명 교체.

### 운영/배포

- `httpx`는 이미 transitive 의존성 — 명시화만.
- `OPENROUTER_API_KEY` 환경변수가 없으면 OpenRouter 봇 시작 실패 (명확한 에러).
- 비용: OpenRouter는 사용량 과금. 사용자에게 명시 안내.

---

## 7. 보안 검토

### OWASP Top 10 관련

| 항목 | 적용 여부 | 검토 |
|---|---|---|
| A01 Broken Access Control | 낮음 | 백엔드 선택은 봇 단위 — 사용자 권한 변경 없음 |
| A02 Cryptographic Failures | **중요** | OpenRouter API 키는 환경변수에서 읽음 (bot.yaml에 평문 저장 안 함) — 다만 환경변수 자체의 보호는 OS 책임. abyss는 키 이름만 yaml 저장 |
| A03 Injection | 낮음 | 사용자 메시지가 LLM API에 들어감 — prompt injection 위험은 LLM 일반 위험 (백엔드 변화로 새로 도입되는 위험 아님) |
| A04 Insecure Design | 검토 필요 | OpenRouter 백엔드가 도구 없음을 사용자가 모르고 의존하면 잘못된 응답 가능. onboarding과 docs로 강하게 안내 |
| A05 Security Misconfiguration | 검토 필요 | `base_url` 옵션 — 사용자가 self-hosted gateway로 쓰고 싶을 때 유용. 다만 잘못 설정 시 키가 잘못된 endpoint로 유출. 기본값을 OpenRouter 공식으로 hard-code, override는 명시적 |
| A06 Vulnerable Components | 낮음 | httpx (이미 사용중), 추가 의존성 없음 |
| A07 Authn Failures | 검토 필요 | OpenRouter 401 → 명확한 에러. 키 만료/회수 시 메시지 명시 |
| A08 Software/Data Integrity | 낮음 | 응답은 LLM 출력 — 일반 LLM 신뢰 모델 |
| A09 Logging Failures | **중요** | API 키를 절대 로그에 출력 금지. httpx 자체 디버그 로그가 헤더를 출력하지 않도록 검증 |
| A10 SSRF | **중요** | `base_url` override는 abyss config에서만 — 사용자 입력 (메시지)에서 수정 불가능. `_load_history`는 디스크에서만 읽음. 웹 fetch 없음 |

### 인증/인가 변경

- 변경 없음. 봇 자체의 사용자 인가 (allowed_users)는 백엔드 무관.
- API 키는 env var 기반 — 다중 봇이 같은 key 환경변수를 공유 가능.

### 민감 데이터 처리

- OpenRouter는 사용자 메시지를 외부 (OpenRouter 서버 + 모델 제공자)로 전송. **PII나 민감 데이터를 OpenRouter 봇에 보내지 말 것**을 docs에 명시.
- Claude Code 백엔드도 Claude API에 전송하지만, 사용자가 이미 인지한 신뢰 모델.
- abyss MEMORY/conversation 로그는 디스크 평문 — 변경 없음.

### PCI-DSS 영향

- 해당 없음.

### 추가 위협 모델링

- **위협**: API 키 노출 — env var → 프로세스 메모리 dump.
  - **완화**: abyss 프로세스 권한 = 사용자. 동일 사용자 권한 프로세스가 dump 가능 → OS 책임. 1차 릴리즈에서 추가 조치 없음. 후속에 macOS Keychain 통합.
- **위협**: OpenRouter 응답이 악성 — XSS-like prompt가 다시 사용자에게 노출.
  - **완화**: handlers의 `markdown_to_*` 변환에서 escape — Telegram HTML, Slack mrkdwn 둘 다 escape 정책 검증.
- **위협**: 응답에 큰 토큰 (max_tokens 미지정 시) → 비용 폭발.
  - **완화**: `max_tokens` 기본 4096. 사용자 override 가능. abyss 시작 로그에 모델 + max_tokens 표시.
- **위협**: 사용자가 `base_url`을 악성 endpoint로 변경 → 키 유출.
  - **완화**: bot.yaml은 사용자 본인이 편집하므로 자기책임. abyss 시작 시 base_url이 OpenRouter 공식이 아니면 경고 출력.
- **위협**: prompt injection이 OpenRouter 봇의 system prompt (CLAUDE.md)를 무력화 → 봇 페르소나 이탈.
  - **완화**: 일반 LLM 위험. abyss 책임은 system prompt를 첫 메시지로 두는 것. 강건한 페르소나 유지는 모델 책임.

---

## 8. 완료 조건 체크리스트

- [ ] Phase 1~9 구현 단계 100% 완료
- [ ] 단위 테스트 케이스 1~27 통과
- [ ] 통합 테스트 시나리오 1~7 통과
- [ ] E2E 테스트 E1~E4 수동 확인 (CI 제외)
- [ ] `make lint` 통과
- [ ] `make test` 통과
- [ ] 회귀 검증 (Phase 9.2) 모두 통과
- [ ] OpenRouter 신규 봇 검증 (Phase 9.3, 9.4) 통과
- [ ] `docs/OPENROUTER_SETUP.md` 작성 완료
- [ ] 사이드이펙트 표 항목 모두 "해당 없음" 또는 "대응 완료"
- [ ] 보안 검토 항목 모두 "검토 완료" 또는 "대응 완료"
- [ ] 문서 (`CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/TECHNICAL-NOTES.md`, `README.md`, `docs/SECURITY.md`) 갱신
- [ ] 본 문서 status를 `done`으로 변경

## 9. 중단 기준

- LLMBackend Protocol이 ClaudeCodeBackend의 다층적 동작 (subprocess + SDK + resume + cancel)을 표현하기에 부족하여 추상이 깨지는 경우.
- OpenRouter 응답 품질이 동일 모델 (Claude haiku) Claude Code 백엔드 응답 대비 현저히 떨어지는 경우 (E2E 평가에서 확인).
- 백엔드 추상 도입이 기존 Claude Code 동작에 회귀를 일으키는 경우.
- → 즉시 중단, plan 업데이트 후 사용자 리뷰.
