# Plan: Gate Phase 5-7 MCP servers on usage signals

- date: 2026-06-04
- status: draft
- author: claude
- approved-by: (사용자 승인 후 기재)

## 1. 목적 및 배경

대시보드 채팅이 새 세션을 시작할 때 약간 느리다는 사용자 보고. 측정 결과:

- 페이지 로드 자체: 5-10ms (proxy 포함)
- `compose_claude_md`: 1.24ms (영향 없음)
- daemon 로그: slow op 없음
- **MCP cold-spawn × 6 = 150-200ms** ← 새 세션 첫 메시지 비용

Phase 1-4까지는 봇당 항상 켜지는 MCP가 `conversation_search`, `about_me`,
`recall_fact` 3종. Phase 5-7에서 `propose_skill`, `call_bot`, `record_progress`
3종이 더 추가되어 새 세션 spawn fanout이 2배가 됐다. `recall_fact`는 이미
`facts.db` 존재 여부로 gate되어 있지만 Phase 5-7 신규 MCP 3종은 무조건 켜진다.

같은 패턴(usage signal gate)을 신규 MCP에도 적용해 cold-start fanout을 줄인다.

## 2. 예상 임팩트

- 영향 범위: `claude_runner._prepare_skill_config`의 MCP 주입 결정 로직만.
  대상 MCP는 `record_progress`, `call_bot`. `propose_skill`은 always-on 유지.
- 사용자 경험: 새 세션 첫 메시지 지연이 `2×30ms ≈ 60ms` 줄어든다. 측정값
  기준 150-200ms → 90-140ms. 체감 가능한 범위.
- 가용성: 사용자가 `goals.yaml`에 첫 goal 추가하면 다음 새 세션부터 자동
  활성화. `cclaw bot add`로 두 번째 봇 만들면 `call_bot`도 다음 새 세션부터
  자동 활성화. **기존 SDK pool 세션은 재시작 없이 그대로 유지** (regression
  없음).
- 성능: per-session spawn cost 감소 외 다른 영향 없음.

## 3. 구현 방법 비교

### 방법 A — usage-signal gating (선택)

`recall_fact`가 `facts.db` 존재로 gate하듯, `record_progress`는 `goals.yaml`
존재, `call_bot`은 `config.yaml`의 bots 개수 > 1로 gate.

- 장점: 기존 패턴과 완전 일치. 코드 변경 작음 (~20줄). 사용자 행동 한 번이면
  자동 활성화. 단위 테스트로 검증 쉬움.
- 단점: 사용자가 `goals.yaml`을 직접 편집하지 않고 봇한테 “goal 만들어줘”
  하면, 봇은 `record_progress` MCP가 없어서 첫 세션에서는 사용 불가.
  실제로는 봇이 `goals.yaml`을 만들지 않으므로 영향 거의 없음 (CLI/대시보드
  통해 사람이 만든다). 새 세션 시작 시점에는 이미 켜져 있다.

### 방법 B — 신규 MCP 3종을 단일 서버로 묶음

`propose_skill`, `call_bot`, `record_progress`를 `coevolution_tools` 하나로
합쳐 spawn 1회로 줄임.

- 장점: cold-start 3회 → 1회. 메모리도 줄어듦.
- 단점: 코드 변경 큼. 도구별 의존성 (config 위치, depth env 등)이 한 프로세스
  안에 섞임. 기존 stdio 핸들러 시그니처도 모두 깨짐. 테스트 셋업 전부 재작성
  필요. 위험 대비 효과는 방법 A와 비슷한 수준 (60ms vs 90ms 절약).

### 방법 C — lazy spawn (Claude Code 측 변경 필요)

Claude Code SDK가 lazy load를 지원한다면 cold-start를 첫 호출 시점으로
미룰 수 있음.

- 장점: 가장 깔끔.
- 단점: 외부 SDK 변경 필요. 우리 통제 밖.

**선택: 방법 A.** 기존 `recall_fact` gating 패턴 답습. 위험 작고 효과 명확.

## 4. 구현 단계

- [ ] Step 1: `_record_progress_mcp_server(bot_dir: Path)` 시그니처 변경,
  `bot_dir/goals.yaml` 부재 또는 빈 리스트면 `None` 반환.
- [ ] Step 2: `_call_bot_mcp_server()` 변경 — `load_config()`로 bots 수 확인,
  2 미만이면 `None` 반환. config 로드 실패 시(테스트 격리 환경 등)는 보수적
  으로 활성화 유지 (`recall_fact`처럼 가시적 비활성화는 명시 signal일 때만).
- [ ] Step 3: `_prepare_skill_config`의 두 주입 블록 수정 — `bot_dir` 전달,
  `None` 반환 시 주입 스킵. 주석에 gate 근거 명시.
- [ ] Step 4: 신규 테스트 파일 `tests/test_mcp_gating.py` 추가.
- [ ] Step 5: `make lint` + `uv run pytest`.
- [ ] Step 6: feature 브랜치 + PR.

## 5. 테스트 계획

**단위 테스트** (`tests/test_mcp_gating.py`):

- [ ] `test_record_progress_skipped_without_goals_yaml`: 봇 디렉터리만 있고
  `goals.yaml` 없을 때 `_record_progress_mcp_server`가 `None` 반환.
- [ ] `test_record_progress_skipped_when_goals_yaml_empty`: 파일은 있지만
  yaml `[]`/`null`일 때 `None` 반환.
- [ ] `test_record_progress_attaches_when_goals_present`: 활성 goal 1개
  있을 때 entry dict 반환 + `record_progress` 키 포함.
- [ ] `test_call_bot_skipped_with_single_bot`: config.yaml에 봇 1개일 때
  `None` 반환.
- [ ] `test_call_bot_attaches_with_multiple_bots`: 2개 이상일 때 entry 반환.
- [ ] `test_call_bot_attaches_when_config_missing`: load_config 실패 환경
  (config 부재)에서는 보수적으로 entry 반환 — 운영 환경에서 갑자기 끊기지
  않도록.
- [ ] `test_prepare_skill_config_skips_gated_mcps`: 위 조건들을 통합한
  `_prepare_skill_config` 시나리오 — 새로 만든 빈 봇 디렉터리에 대해
  `record_progress` / `call_bot` 모두 `.mcp.json`에 등록되지 않음.
- [ ] `test_prepare_skill_config_propose_skill_always_attached`: 위 시나리오
  에서도 `propose_skill`은 항상 등록 (regression 방지).

**통합 테스트:**

- [ ] daemon 재기동 후 `cclawlifebot` 새 세션 1회 만들어보고 (goals 있고
  봇 여러 개) — `record_progress` + `call_bot` 둘 다 `.mcp.json`에
  나타나는지 확인. 즉 정상 환경에서는 동일하게 작동함을 확인.

## 6. 사이드 이펙트

- **하위 호환성**: gate 활성화 후 사용자가 `goals.yaml`을 만들거나 두 번째
  봇을 생성하면 다음 새 세션부터 MCP가 자동 부착된다. 이미 spawn된 SDK pool
  세션은 재시작 시점까지 기존 상태 유지. 즉 "끊긴 기능"이 갑자기 생기지
  않는다.
- **기존 기능**: `recall_fact` gating 동작과 동일 — 검증된 패턴.
- **마이그레이션**: 불필요.

## 7. 보안 검토

- OWASP Top 10: 해당 없음. 외부 입력 추가 없고, 권한 변경 없고, 민감 데이터
  경로 변경 없음.
- 인증/인가: 변경 없음.
- 민감 데이터: 변경 없음.
- PCI-DSS: 해당 없음.
- 추가 고려: `config.yaml` 읽기는 이미 다른 곳에서 수행. 새로 도입되는
  파일 접근 없음.
