# Plan: OpenAI-compatible 백엔드 전면 제거 (Claude Code 단일화)

- date: 2026-05-15
- status: done
- author: claude
- approved-by: ash84 (2026-05-15)

## 1. 목적 및 배경

abyss 는 "Claude Code 기반 AI 페르소나 에이전트" 도구다. 현재 LLM 백엔드는 3개:

- `claude_code` (기본, 풀 에이전트: 툴/MCP/스킬/`--resume`)
- `openai_compat` (텍스트 전용, OpenAI 호환 엔드포인트 — `openrouter` / `minimax` / `minimax_china` 프리셋)
- `openrouter` (호환 alias, 내부적으로 `openai_compat` 로 위임)

호환 백엔드는 **툴/MCP/스킬/`--resume` 없음** — 페르소나 에이전트의 핵심 가치를 못 누림. 유지비만 든다:

- 코드: `llm/openai_compat.py` (414줄) + `llm/openrouter.py` (legacy shim) + 관련 테스트 + 평가 테스트
- 문서: `MINIMAX_SETUP.md`, `OPENROUTER_SETUP.md` (총 240줄)
- 의존성: `httpx` (이미 다른 곳에서 쓰이는지 확인 필요)
- 멘탈 모델: 백엔드 선택 가이드, provider preset, env var 분기

> Claude Code 단일 백엔드로 회귀. `LLMBackend` Protocol 추상화는 향후 다른 풀 에이전트 백엔드를 붙일 여지로 유지.

## 2. 예상 임팩트

**영향받는 모듈/파일:**
- `src/abyss/llm/openai_compat.py` (삭제)
- `src/abyss/llm/openrouter.py` (삭제)
- `src/abyss/llm/__init__.py` (registry 등록 1줄 제거)
- `src/abyss/onboarding.py` (백엔드 선택 분기 제거 또는 단순화)
- `tests/test_llm_openai_compat.py`, `tests/test_llm_openrouter.py` (삭제)
- `tests/evaluation/test_openrouter_e2e.py` (삭제)
- `tests/test_llm_registry.py`, `tests/test_llm_base.py` (호환 백엔드 참조 제거)
- `tests/conftest.py` (호환 백엔드 fixture 제거)
- `tests/test_onboarding.py` (백엔드 선택 케이스 제거)
- `docs/ARCHITECTURE.md`, `docs/TECHNICAL-NOTES.md`, `docs/SECURITY.md`, `docs/README.md` (백엔드 섹션 정리)
- `docs/MINIMAX_SETUP.md`, `docs/OPENROUTER_SETUP.md` (삭제)
- `docs/landing/index.html` (백엔드 언급 정리)
- `CLAUDE.md` (LLM Backend Selection 섹션 정리)
- `pyproject.toml` (`httpx` 의존성은 다른 모듈에서 쓰이는지 확인 후 유지/제거)

**호환성:**
- 기존 `bot.yaml` 에 `backend.type: openai_compat | openrouter` 설정이 있는 봇은 시작 시 에러 → "Claude Code 단일 백엔드만 지원" 메시지 + 마이그레이션 안내
- `~/.abyss/bots/*/bot.yaml` 확인: 현재 우리 환경에서는 0개 (사전 조사 완료)
- 단, 외부 사용자가 있다면 영향 — 릴리즈 노트에 명시

**API/사용자 경험:**
- `abyss bot add` 가 백엔드 선택 단계를 묻지 않음 (이미 Claude Code 가 default 라 큰 변화 없음)
- 슬래시 명령/PWA/대시보드 표시 — `backend.type` 안 보이게 됨 (현재도 거의 안 보임)

**성능/가용성:** 변화 없음.

## 3. 구현 방법 비교

### 방법 A: 코드만 삭제, Protocol 유지 (선택)

`LLMBackend` Protocol + registry 는 유지. `claude_code` 만 등록. `openai_compat` / `openrouter` 모듈 + 테스트 + 문서 삭제. 기존 `bot.yaml` 의 비-Claude `backend.type` 은 시작 시 명확한 에러로 거부.

- 장점: 향후 다른 풀 에이전트 백엔드 (예: Gemini CLI, local Claude) 붙일 여지. registry 패턴 일관성. 변경 범위 최소.
- 단점: 추상화는 남는데 구현체는 1개라 약간 over-engineered 느낌.

### 방법 B: LLMBackend Protocol + registry 까지 완전 삭제

`llm/` 디렉토리 통째로 삭제. `handlers.py` / `cron.py` / `heartbeat.py` 가 `claude_runner` 를 직접 호출하도록 환원.

- 장점: 코드 추상화 1단계 줄어듦. 가장 깔끔.
- 단점: 호출 사이트 (`get_or_create`, `cancel`, `close_all`) 다 손봐야 함. 변경 범위 큼. 다른 백엔드 붙일 때 다시 만들어야 함.

### 선택: **방법 A**

`LLMBackend` Protocol 은 이미 안정적이고 캐싱/lifecycle 관리에 쓰이므로 유지. 구현체만 정리. 향후 Gemini CLI 같은 풀 에이전트 백엔드가 들어올 가능성이 있어 추상화 비용 < 재구축 비용.

## 4. 구현 단계

- [ ] **Step 1**: 사전 검증 — `~/.abyss/bots/*/bot.yaml` 에서 `backend.type: openai_compat|openrouter` 사용 여부 확인 (현재 0개 확인됨)
- [ ] **Step 2**: `src/abyss/llm/openai_compat.py` 삭제
- [ ] **Step 3**: `src/abyss/llm/openrouter.py` 삭제
- [ ] **Step 4**: `src/abyss/llm/__init__.py` 에서 import + register 라인 제거. `claude_code` 만 남김
- [ ] **Step 5**: `src/abyss/llm/base.py` 의 docstring/타입 정리 (`openrouter` 언급 제거)
- [ ] **Step 6**: `src/abyss/onboarding.py` — 백엔드 선택 분기 제거 (Claude Code 가 default 면 그대로, 명시적 prompt 가 있으면 제거)
- [ ] **Step 7**: registry 가 알 수 없는 `backend.type` 받았을 때 명확한 에러 메시지 ("Only `claude_code` backend is supported. Remove `backend.type` from bot.yaml or set to `claude_code`.")
- [ ] **Step 8**: `tests/test_llm_openai_compat.py`, `tests/test_llm_openrouter.py`, `tests/evaluation/test_openrouter_e2e.py` 삭제
- [ ] **Step 9**: `tests/test_llm_registry.py`, `tests/test_llm_base.py`, `tests/conftest.py`, `tests/test_onboarding.py` 에서 호환 백엔드 참조 제거
- [ ] **Step 10**: `docs/MINIMAX_SETUP.md`, `docs/OPENROUTER_SETUP.md` 삭제
- [ ] **Step 11**: `docs/ARCHITECTURE.md`, `docs/TECHNICAL-NOTES.md`, `docs/SECURITY.md`, `docs/README.md` 에서 호환 백엔드 섹션 정리
- [ ] **Step 12**: `CLAUDE.md` 의 "LLM Backend Selection" 섹션 단순화 (Claude Code 단일)
- [ ] **Step 13**: `docs/landing/index.html` 의 백엔드 언급 정리 (있으면)
- [ ] **Step 14**: `pyproject.toml` 의 `httpx` 사용처 확인 — Web Push (`pywebpush`) / chat_server proxy 등에서 쓰이면 유지, 호환 백엔드 전용이면 제거
- [ ] **Step 15**: `make lint && make test` 통과
- [ ] **Step 16**: 릴리즈 노트 초안 — breaking change 명시

## 5. 테스트 계획

**단위 테스트:**
- [ ] 케이스 1: `bot.yaml` 에 `backend.type` 없을 때 `claude_code` 기본 동작 (기존 통과 확인)
- [ ] 케이스 2: `bot.yaml` 에 `backend.type: claude_code` 명시했을 때 동작 (기존 통과 확인)
- [ ] 케이스 3: `bot.yaml` 에 `backend.type: openai_compat` 또는 `openrouter` 일 때 — 명확한 에러 발생 (`KeyError` 가 아니라 사용자 친화적 메시지)
- [ ] 케이스 4: `llm/__init__.py` 에서 `get_backend("openai_compat")` 호출 시 에러
- [ ] 케이스 5: `tests/test_llm_registry.py` 가 호환 백엔드 fixture 없이도 통과

**통합 테스트:**
- [ ] 시나리오 1: `abyss start` → 모든 봇 정상 부팅 (Claude Code 만 사용)
- [ ] 시나리오 2: 채팅 / cron / heartbeat 모두 Claude Code 백엔드로 동작
- [ ] 시나리오 3: 잘못된 `backend.type` 설정한 봇 시작 시 에러 메시지 + 다른 봇은 정상 동작
- [ ] 시나리오 4: `make lint` 0 issues, `make test` 100% 통과
- [ ] 시나리오 5: `git grep "openai_compat\|openrouter\|minimax\|MiniMax\|OpenRouter"` 0 hits (테스트 fixture 제외)

## 6. 사이드 이펙트

- **하위 호환성 깨짐**: 기존에 `backend.type: openai_compat|openrouter` 설정한 봇은 부팅 실패. **로컬 환경 사전 조사 결과 0개** — 외부 사용자는 릴리즈 노트로 안내
- **마이그레이션 가이드** 필요: `bot.yaml` 에서 `backend:` 블록 삭제 또는 `type: claude_code` 로 변경
- **API 키 환경변수 정리**: `OPENROUTER_API_KEY`, `MINIMAX_API_KEY` 등은 그냥 무시되도록 둠 (코드에서 안 읽음). 별도 정리 작업 불필요
- **`abyss/llm/registry.py` 의 `close_all`**: openai_compat 의 `httpx.AsyncClient.aclose()` 호출이 없어짐 — 단순화 가능
- **abyss release version bump**: `2026.05.15` 또는 다음 일자

## 7. 보안 검토

- **OWASP A02 (Cryptographic Failures)**: 호환 백엔드는 사용자 API 키 (`OPENROUTER_API_KEY` 등) 를 env 로 읽음. 제거하면 잠재적 키 노출 surface 가 줄어듦 (보안적으로 +)
- **OWASP A03 (Injection)**: 호환 백엔드는 외부 HTTP 엔드포인트로 사용자 메시지를 전송. 제거하면 abyss → 외부 endpoint surface 감소
- **인증/인가 변경**: 없음
- **민감 데이터**: 호환 백엔드 경유 메시지 전송이 없어져 third-party LLM provider 로의 데이터 유출 surface 감소
- **PCI-DSS 영향**: 해당 없음

## 8. 작업 순서

1. **이 plan 승인** (사용자 리뷰 → `approved-by` 기재)
2. 브랜치 `chore/drop-openai-compat` 생성
3. Step 1-15 순차 실행 (테스트 PR-ready 상태 유지하면서)
4. PR 생성 → CI 통과 → 머지
5. 릴리즈 (버전 bump, GitHub 릴리즈, 트윗 초안, landing page 업데이트)
6. plan 상단 `status: done` 기재 후 다음 작업으로

## 9. 완료 조건

- [ ] Step 1-15 체크리스트 100%
- [ ] 단위/통합 테스트 체크리스트 100%
- [ ] `make lint && make test` 통과
- [ ] `git grep "openai_compat\|openrouter\|minimax"` 0 hits (의도된 마이그레이션 메시지 제외)
- [ ] 릴리즈 노트 작성
- [ ] 본 plan 문서 `status: done`

## 10. 중단 기준

- `httpx` 가 다른 모듈에서 쓰여서 dependency 정리가 plan 범위 벗어남 → plan 범위 줄여서 의존성 유지
- 추상화(`LLMBackend` Protocol) 까지 제거하는게 더 깔끔하다는 판단이 들면 → 즉시 중단, 방법 B 로 plan 갱신 후 재승인
- 외부 사용자가 호환 백엔드에 의존 중인 증거 발견 → 즉시 중단, deprecation 경로로 plan 변경
