# Plan: MiniMax 직결 백엔드 지원

- date: 2026-04-26
- status: done
- author: claude
- approved-by: ash84

---

## 1. 목적 및 배경

abyss 봇은 현재 두 가지 백엔드를 지원한다.

| 백엔드 | 용도 | 비고 |
|---|---|---|
| `claude_code` (default) | 풀 에이전트 (tools, MCP, skills, `--resume`) | Anthropic 직결 |
| `openrouter` | OpenAI 호환 텍스트 채팅 (200+ 모델) | OpenRouter 게이트웨이 |

사용자가 **MiniMax** 에 직접 결제한 크레딧을 가지고 있다. OpenRouter 를 거치면 라우팅 마진(~5%) 이 추가로 발생한다. MiniMax API 는 OpenAI 호환 엔드포인트(`/v1/chat/completions`) 를 제공하므로, 기존 `OpenRouterBackend` 의 `base_url` / `api_key_env` 옵션만 바꿔도 동작은 한다.

문제는 이 설정이 **공식 지원이 아님**:

- `abyss bot add` onboarding 마법사가 MiniMax 옵션을 노출하지 않음
- `bot.yaml` 에 raw base URL/env 이름을 사용자가 직접 적어야 함
- 백엔드 이름이 `openrouter` 인데 실제로는 MiniMax 호출 — 로그/에러 메시지 혼란
- MiniMax 와 OpenRouter 가 응답 포맷·에러 코드·streaming 프레임에서 미묘하게 다를 가능성 (`reasoning_content`, `tool_calls`, finish reason 등) 검증 필요
- MiniMax 국제판(`api.minimaxi.chat`) 과 중국판(`api.minimax.chat`) 분리 — 어느 쪽 가입했는지 사용자가 명시해야 함

요구사항: **abyss 가 MiniMax 를 1급 백엔드로 직접 인식**, onboarding 에서 선택 가능하며, `bot.yaml` 에서 명시적으로 `type: minimax` 또는 `provider: minimax` 로 표현되도록 한다. OpenRouter 는 그대로 유지.

## 2. 예상 임팩트

### 영향 범위
- `src/abyss/llm/` — 새 백엔드 모듈 또는 기존 모듈 일반화
- `src/abyss/llm/registry.py` — 백엔드 등록
- `src/abyss/bot_manager.py` — 봇 부팅 시 백엔드 인스턴스화 분기 (변경 없을 가능성, registry 통하므로)
- `docs/OPENROUTER_SETUP.md` 또는 새 `docs/MINIMAX_SETUP.md`
- `tests/test_llm_*.py` — 새 테스트

**범위 외 (별도 plan):**
- `src/abyss/onboarding.py` — backend/provider 선택 UX 개선
- `abysscope/` — 봇 편집 UI 의 backend 드롭다운

### 성능/가용성
- 현재 `openrouter` 가 작동하는 봇은 영향 없음 (변경 안 건드림)
- MiniMax 직결 봇: 네트워크 1 hop 단축 (게이트웨이 제거), 마진 0
- MiniMax API 다운 시 fallback 없음 — OpenRouter 의 multi-provider fallback 손실

### 사용자 경험
- 환경변수 `MINIMAX_API_KEY` 표준화 (또는 사용자 지정)
- bot.yaml 에 `type: openai_compat`, `provider: minimax` 로 의도 명시
- 1차에서는 사용자가 yaml 수동 편집 또는 `abyss bot edit` 으로 설정. onboarding 통합은 후속 plan.

## 3. 구현 방법 비교

### 방법 A — 매뉴얼 설정만 안내 (코드 0줄)

기존 `openrouter` 백엔드 그대로, `docs/MINIMAX_SETUP.md` 만 추가.

```yaml
backend:
  type: openrouter
  base_url: https://api.minimaxi.chat/v1
  api_key_env: MINIMAX_API_KEY
  model: MiniMax-M1
```

**장점**
- 코드 0줄 변경
- 즉시 사용 가능

**단점**
- 백엔드 이름이 거짓말 (openrouter → minimax)
- onboarding 미지원, 사용자가 yaml 직접 편집
- MiniMax 응답 포맷 차이 발생 시 수정처가 모호
- 신규 사용자에게 발견 가능성 낮음

### 방법 B — 별도 `MiniMaxBackend` 클래스 (분리)

`src/abyss/llm/minimax.py` 생성. `OpenRouterBackend` 코드를 복제하거나 상속.

```yaml
backend:
  type: minimax
  region: international   # international | china
  model: MiniMax-M1
  api_key_env: MINIMAX_API_KEY   # optional, default
```

`region` → `base_url` 자동 매핑:
- `international` → `https://api.minimaxi.chat/v1`
- `china` → `https://api.minimax.chat/v1`

**장점**
- 명시적, 의도 분명
- MiniMax 전용 기능 (긴 컨텍스트 모델 파라미터, T2A/I2I API 등) 확장 여지
- 로그/에러 메시지에 `minimax` 라고 정확히 표시

**단점**
- 코드 중복 (~200 라인) — `_build_messages`, streaming 파서, history replay 등 OpenRouter 와 거의 동일
- 향후 Groq/Together/Fireworks 등 OpenAI 호환 프로바이더가 늘면 같은 패턴 N번 반복

### 방법 C — `openai_compat` 일반화 + provider preset (추천)

`OpenRouterBackend` 를 `OpenAICompatBackend` 로 리네임/추출. `provider` 키로 base_url/env 프리셋 자동 적용. 기존 `openrouter` 는 alias 로 보존.

```yaml
backend:
  type: openai_compat
  provider: minimax        # minimax | minimax_china | openrouter | groq | together | ...
  model: MiniMax-M1
  api_key_env: MINIMAX_API_KEY   # optional, default per provider
```

provider 레지스트리:

```python
PROVIDER_PRESETS = {
    "openrouter":     {"base_url": "https://openrouter.ai/api/v1",   "api_key_env": "OPENROUTER_API_KEY"},
    "minimax":        {"base_url": "https://api.minimaxi.chat/v1",    "api_key_env": "MINIMAX_API_KEY"},
    "minimax_china":  {"base_url": "https://api.minimax.chat/v1",     "api_key_env": "MINIMAX_API_KEY"},
}
```

기존 봇 호환:
- `type: openrouter` → 자동으로 `type: openai_compat, provider: openrouter` 로 매핑 (alias)
- 기존 `bot.yaml` 수정 불필요

**장점**
- 코드 재사용 100%
- 신규 OpenAI 호환 프로바이더 추가 = preset 1줄
- onboarding 에서 provider 드롭다운 단순
- 기존 `openrouter` 백엔드 봇 무중단

**단점**
- MiniMax 와 OpenRouter 의 응답 포맷 차이가 있을 경우 단일 클래스에 분기 필요 (실측 후 결정)
- `type` 명칭 변경 — alias 유지로 완화

### 선택: **방법 C**

이유:
1. abyss 의 LLM 통합 방향이 "다양한 OpenAI 호환 게이트웨이" 로 확장될 가능성 높음 (Groq, Together, Fireworks, Anthropic 직결 추후 추가 가능)
2. 코드 중복 회피
3. 기존 봇 무중단

방법 B 의 장점 (MiniMax 전용 확장) 은 추후 필요 시 `OpenAICompatBackend` 를 상속한 `MiniMaxBackend` 로 분기 가능.

## 4. 구현 단계

- [ ] **Step 1**: `OpenRouterBackend` → `OpenAICompatBackend` 로 리네임 (`src/abyss/llm/openai_compat.py`). 기존 `openrouter.py` 는 호환용 stub (re-export).
- [ ] **Step 2**: `PROVIDER_PRESETS` dict 추가 (`openrouter`, `minimax`, `minimax_china`). `__init__` 에서 `provider` 키 읽어 `base_url` / `api_key_env` 기본값 채움. `base_url` 이 명시되면 우선.
- [ ] **Step 3**: `registry.py` 에 `openai_compat` 등록. `openrouter` 도 등록 유지 (legacy alias → 동일 클래스, provider=openrouter 강제).
- [ ] **Step 4**: 응답 포맷 실측. MiniMax `/v1/chat/completions` 와 OpenAI 스펙 차이 항목 (필드명, error shape, streaming `data: [DONE]` 처리, `finish_reason` enum) 매핑 필요 시 분기 추가.
- [ ] **Step 5**: `docs/MINIMAX_SETUP.md` 작성. 가입/키 발급/region 선택/bot.yaml 예시 (수동 편집).
- [ ] **Step 6**: `docs/OPENROUTER_SETUP.md` 갱신 — `openai_compat` 일반화 언급, provider 패턴 소개.
- [ ] **Step 7**: `CLAUDE.md` 의 LLM Backend Selection 섹션 업데이트.
- [ ] **Step 8**: 기존 `openrouter` 봇 1개로 회귀 테스트, 신규 MiniMax 봇 1개로 yaml 수동 작성 후 동작 확인.

## 5. 테스트 계획

### 단위 테스트

- [ ] `tests/test_openai_compat.py::test_provider_preset_resolves_base_url` — `provider: minimax` → 올바른 base_url 적용
- [ ] `test_provider_preset_china` — `provider: minimax_china` → 중국 base_url
- [ ] `test_explicit_base_url_overrides_provider` — base_url 명시 시 provider 무시
- [ ] `test_legacy_openrouter_type_still_works` — `type: openrouter` 봇 호환
- [ ] `test_unknown_provider_raises` — 잘못된 provider 명에 대해 명확한 에러
- [ ] `test_default_api_key_env_per_provider` — provider 별 기본 env 변수 이름
- [ ] `test_missing_api_key_env_raises_at_first_call` — 환경변수 없을 때 에러 메시지에 provider 이름 포함
- [ ] MiniMax 응답 모킹 (`httpx.MockTransport`) — 정상/에러/streaming chunk 파싱
- [ ] history replay 가 dedupe 로직 그대로 통과 (`max_history`, 마지막 user turn 중복 제거)

### 통합 테스트

- [ ] 시나리오 1: bot.yaml 에 `type: openai_compat, provider: minimax` 수동 작성 → 봇 시작 → Telegram 메시지 1회 → MiniMax 호출 → 응답 텔레그램 전달
- [ ] 시나리오 2: 동일 chat 에서 후속 메시지 → conversation-YYMMDD.md history replay 동작
- [ ] 시나리오 3: `MINIMAX_API_KEY` 미설정 → 에러 메시지가 `MINIMAX_API_KEY` 명시
- [ ] 시나리오 4: 기존 OpenRouter 봇과 신규 MiniMax 봇 동시 실행, 서로 영향 없음
- [ ] 시나리오 5: tests/evaluation 에 실제 MiniMax 키로 한 번만 호출하는 e2e 케이스 (CI 제외)

## 6. 사이드 이펙트

- **bot.yaml 스키마 변경 없음** — `backend.type`, `backend.provider`, `backend.base_url`, `backend.api_key_env`, `backend.model`, `backend.max_history`, `backend.max_tokens` 모두 기존 필드 또는 신규 옵셔널
- **기존 `openrouter` 봇 호환** — alias 로 처리. yaml 수정 강요하지 않음
- **onboarding/UI** — 1차에서는 yaml 수동 편집. `abyss bot add` 흐름과 abysscope 편집 UI 통합은 별도 plan
- **로그/에러 메시지** — provider 이름 포함하도록 갱신. 사용자에게 원인 파악 단순화
- **MiniMax 응답 포맷 차이** — 실측 후 분기 필요한 경우만 추가. 미발견 시 코드 변경 0
- **마이그레이션 도구 불필요** — 기존 봇 그대로 동작

## 7. 보안 검토

OWASP Top 10 + abyss 보안 정책 검토:

- **A02 Cryptographic Failures / Secret Handling**: API 키는 환경변수로만 읽고 디스크/로그/에러 메시지에 절대 출력 금지. 기존 `OpenRouterBackend` 의 키 마스킹 패턴 그대로 유지.
- **A05 Security Misconfiguration**: provider preset 의 base_url 은 hardcode (사용자 입력 우회 시에만 명시 override 허용). HTTPS 만 허용.
- **A07 Identification and Authentication Failures**: 환경변수 미설정 시 첫 호출에 명확히 실패 (silent skip 금지).
- **A08 Software and Data Integrity Failures**: TLS 검증 비활성화 옵션 추가하지 않음. `httpx.AsyncClient` 기본값 사용.
- **A09 Security Logging and Monitoring**: 요청/응답 본문은 INFO 레벨 로그에 기록 안 함. DEBUG 에서만, 키는 마스킹.
- **PCI-DSS 영향 없음** — 결제 데이터 미취급.
- **민감 데이터 처리 변경 없음** — Telegram 메시지 → MiniMax 로 전송되는 부분은 OpenRouter 와 동일 흐름. 사용자에게 백엔드별 데이터 거버넌스 차이는 setup 문서에서 명시.
- **인증/인가 변경 없음** — Telegram 봇 토큰 흐름 동일.
- **신규 외부 의존성 없음** — `httpx` 기존 사용 중.
- **MiniMax 의 데이터 보존 정책** — setup 문서에 링크 추가 (사용자 인지).

## 완료 조건

- 구현 단계 8개 100% 완료
- 단위 테스트 + 통합 테스트 100% pass
- `make lint && make test` (또는 `uv run ruff check . && uv run pytest`) 통과
- 기존 `openrouter` 봇 회귀 없음 확인
- 사이드 이펙트 항목 각각 "해당 없음" 또는 "대응 완료" 명시
- 본 문서 status `done` 으로 갱신

## 중단 기준

- MiniMax 응답 포맷이 OpenAI 스펙과 너무 달라 단일 클래스로 처리 불가능 → 방법 B (별도 클래스) 로 plan 재작성
- MiniMax API 정책상 server-side proxy 호출이 ToS 위반 → 사용자에게 알리고 plan abort

## 후속 작업 (별도 plan)

- **onboarding 백엔드/프로바이더/모델 선택 UX** — 별도 plan. 현재 `prompt_backend_choice` 가 backend 만 분기, 모델은 자유 텍스트. provider 프리셋 드롭다운 + 모델 카탈로그 도입 범위 산정 필요.
- **abysscope 봇 편집 UI** — backend 블록 폼화 (드롭다운 + 동적 필드)
- 추가 OpenAI 호환 프로바이더 (Groq, Together, Fireworks, DeepSeek 직결, Cerebras) 프리셋 일괄 추가
- 백엔드별 streaming 정합성 테스트 매트릭스
