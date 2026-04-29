# Plan: Claude Code 최신 changelog 기능 abyss 적용
- date: 2026-04-29
- status: in-progress
- author: claude
- approved-by: (pending)

## 1. 목적 및 배경

abyss 는 Claude Code (`claude -p` subprocess + Python Agent SDK) 위에 만들어졌다. 2026-03 ~ 2026-04 사이 Claude Code 가 다음을 추가했다.

- 1시간 prompt cache TTL (`ENABLE_PROMPT_CACHING_1H`)
- non-interactive 환경에서 forked subagent 활성화 (`CLAUDE_CODE_FORK_SUBAGENT=1`)
- `claude -p` MCP 연결 비차단 (`MCP_CONNECTION_NONBLOCKING=true`)
- 작업 디렉터리 마스킹 (`CLAUDE_CODE_HIDE_CWD`)
- subprocess 식별 (`AI_AGENT`)
- MCP `alwaysLoad` 옵션 + 결과 크기 확장 (`_meta["anthropic/maxResultSizeChars"]` ≤ 500K)
- PreCompact hook (exit code 2 차단)
- Hook 메타데이터 (`duration_ms`) 및 조건부 hook (`if` 필드)
- `disableSkillShellExecution` 보안 옵션
- `sandbox.network.deniedDomains` 도메인 차단

이 중 abyss 패턴 (heartbeat/cron 빈번 호출, MCP 다수, GitHub 임포트 skill, 장시간 대화) 에 직접 효과가 큰 것을 단계별로 적용한다.

## 2. 예상 임팩트

### 영향 모듈
- `src/abyss/claude_runner.py` — subprocess env 주입
- `src/abyss/sdk_client.py` — Agent SDK env 주입
- `src/abyss/mcp_servers/conversation_search.py` — `_meta` 크기 확장, `alwaysLoad`
- `src/abyss/skill.py` — MCP config `alwaysLoad`, hook composition
- `src/abyss/token_compact.py` — PreCompact hook 마이그레이션
- `src/abyss/bot_manager.py` — 시작 시 env 점검
- `abysscope/` — hook telemetry 패널 (Phase 4)

### 성능/가용성
- prompt cache 1h TTL → idle 봇 재호출 시 API 비용/latency 감소 (Max plan 사용자도 quota 절감)
- MCP nonblocking → cold-start 1~3s 단축
- forked subagent → heartbeat/cron 병렬 처리 가능
- PreCompact hook 도입 시 token_compact 로직 일부 이전 — 동일 결과, 트리거가 자동화됨

### UX 변화
- `CLAUDE_CODE_HIDE_CWD` 활성화 → 모델 응답에서 `~/.abyss/...` 경로 노출 제거 (privacy ↑)
- conversation_search 결과 잘림 감소 → 장기 검색 정확도 향상
- 외부 사용자 영향 없음 (단일 사용자 환경)

## 3. 구현 방법 비교

### 방법 A: 한꺼번에 모든 env/hook 도입
- 장점: 1회 PR. 빠름.
- 단점: 회귀 발생 시 원인 추적 난해. 기존 SDK Pool/streaming 과 상호작용 불확실.
- 보류.

### 방법 B: 단계별 phase, 각 phase 단위로 PR + 검증
- 장점: 회귀 격리, 각 phase 측정 지표 명확. 사용자 검증 후 다음 phase 진행.
- 단점: PR 5~6개. 기간 ↑.
- **선택**.

### 방법 C: Claude Code 의존을 줄이고 Agent SDK 만 사용
- 장점: subprocess 제거, 일부 env 변수 자동 적용.
- 단점: 일부 기능은 CLI 전용 (e.g., `claude ultrareview`). 대대적 리팩토링. 본 plan 범위 초과.
- 별도 plan 으로 분리.

**선택: 방법 B**.

## 4. 구현 단계

### Phase 1: Env Var 통합 주입 (저위험·고가치)

`claude_runner.py` 와 `sdk_client.py` 에서 subprocess/SDK 양쪽에 동일 env 를 주입하는 헬퍼 추가.

대상 env:
- `ENABLE_PROMPT_CACHING_1H=1`
- `CLAUDE_CODE_FORK_SUBAGENT=1`
- `MCP_CONNECTION_NONBLOCKING=true`
- `CLAUDE_CODE_HIDE_CWD=1`
- `AI_AGENT=abyss`

`config.yaml` 에 토글 추가 (default on, 사용자가 끌 수 있게):
```yaml
claude_code:
  prompt_caching_1h: true
  fork_subagent: true
  mcp_nonblocking: true
  hide_cwd: true
```

- [x] Step 1.1: `config.py` 에 `get_claude_code_env()` 헬퍼 추가
- [x] Step 1.2: `claude_runner.py::_prepare_skill_config` 에서 `environment_variables` 에 머지
- [x] Step 1.3: `sdk_client.py` 에서도 동일 env 주입 (claude_runner 의 _prepare_skill_config 결과를 SDK 풀에 그대로 전달하는 기존 경로 활용)
- [x] Step 1.4: `bot_manager.py` 시작 로그에 활성화된 env 출력
- [x] Step 1.5: `docs/TECHNICAL-NOTES.md` 에 env 표 추가

### Phase 2: MCP 최적화

`alwaysLoad` 옵션과 `_meta["anthropic/maxResultSizeChars"]` 응답 헤더 적용.

- [x] Step 2.1: conversation_search 와 QMD MCP 엔트리에 `alwaysLoad: true` 옵션화 — `claude_code.mcp_always_load` 토글 (default on)
- [x] Step 2.2: `mcp_servers/conversation_search.py` 응답에 `_meta = {"anthropic/maxResultSizeChars": 500000}` 추가 (정상 + 에러 분기 모두)
- [x] Step 2.3: `docs/TECHNICAL-NOTES.md` 에 `alwaysLoad` / `_meta` 섹션 추가
- [x] Step 2.4: QMD MCP 동일 처리 — `_qmd_mcp_server(always_load)` 헬퍼로 옵션 적용. QMD 자체 응답의 `_meta` 는 외부 서버라 abyss 측에서 손댈 수 없음 → 호출자 측 `alwaysLoad` 만 적용

### Phase 3: PreCompact Hook 도입

`token_compact.py` 의 트리거를 PreCompact hook 으로 위임.

**중요 — Hook 격리 원칙**: abyss 는 절대 `~/.claude/settings.json` (사용자 글로벌) 을 건드리지 않는다. 사용자가 abyss 외부에서 Claude Code 를 쓸 때 hook 이 발동하면 안 됨. 모든 hook 은 봇 단위 `~/.abyss/bots/<name>/.claude/settings.json` 에 격리.

설정 파일 탐색: Claude Code 는 working_directory (`~/.abyss/bots/<name>/sessions/chat_<id>/`) 에서 상위 traversal 하며 `.claude/settings.json` 수집 → `~/.abyss/bots/<name>/.claude/settings.json` 가 자동 픽업됨.

추가 안전장치: hook 스크립트 진입부에서 `AI_AGENT == "abyss"` env 체크 (Phase 1 의존). 누락 시 즉시 exit 0 — 만약 사용자가 settings 를 잘못 머지해도 abyss 외부에서 무동작.

- [x] Step 3.1: `token_compact.run_compact(bot_name)` 가 이미 hook 진입점에서 직접 호출 가능 (분리 불필요). 신규 모듈 `abyss/hooks/precompact_hook.py` 가 wrapping
- [x] Step 3.2: hook 등록 위치 변경 — 봇-레벨 `bots/<name>/.claude/settings.json` 대신 **세션-레벨** `<session>/.claude/settings.json` 에 등록. 기존 `_write_session_settings` 가 deeper merge 우선이라 봇-레벨이 clobber 되는 문제 회피. 사용자 글로벌 `~/.claude/settings.json` 은 절대 건드리지 않음
- [x] Step 3.3: hook 스크립트 진입부에서 `AI_AGENT == "abyss"` 체크, 누락/불일치 시 exit 0
- [x] Step 3.4: hook 모든 실패 경로 (빈 stdin, 잘못된 JSON, run_compact 예외) 가 exit 0 — 차단 없음
- [x] Step 3.5: cron/heartbeat 의 수동 compact 트리거 유지 (코드 미변경)
- [x] Step 3.6: `bot.yaml.hooks_enabled` 토글 (default true) — false 면 PreCompact entry 만 생략, settings.json 자체는 여전히 생성 (allowedTools 정상 동작 위함)

### Phase 4: Hook Telemetry & 조건부 Hook

abysscope 에 도구별 실행시간 패널 추가 + skill 별 hook 게이팅.

**Hook 위치**: Phase 3 와 동일 — `~/.abyss/bots/<name>/.claude/settings.json` 에만 등록. 사용자 글로벌 `~/.claude/settings.json` 건드리지 않음.

- [x] Step 4.1: PostToolUse hook 스크립트 `abyss/hooks/log_tool_metrics.py` — `duration_ms` 파싱, `AI_AGENT` 가드, 모든 실패 경로 exit 0
- [x] Step 4.2: hook 등록 위치는 Phase 3 와 동일 — 세션-레벨 `<session>/.claude/settings.json` 의 `hooks.PostToolUse` (사용자 글로벌 settings 무관)
- [x] Step 4.3: 저장 경로 `~/.abyss/bots/<name>/tool_metrics/YYMMDD.jsonl` (per-day) — append 시 마다 7일 초과 파일 자동 삭제 (`abyss.tool_metrics.append_event`)
- [x] Step 4.4: abysscope `Metrics` 탭 + `ToolLatencyPanel` 컴포넌트 — `getToolMetrics(name)` 가 jsonl 읽어 p50/p95/p99/count/errors 집계
- [x] Step 4.5: skill `if` 필드 — `skill.yaml.hooks.<Event>` 블록을 `collect_skill_hooks(skills, event)` 로 수집해 세션 settings 에 verbatim 머지. `if` 필드는 Claude Code 가 평가하므로 그대로 통과
- [ ] Step 4.6: builtin_skill 마이그레이션 — 보류. 현재 abyss 쪽에서 유의미한 조건부 hook 예시가 부재. Phase 5 의 `disableSkillShellExecution` 와 함께 고려할 가치 있음 → 별도 plan 으로 분리

### Phase 5: 보안 강화

- [x] Step 5.1: `import_skill_from_github` 가 `untrusted: true` + `source.{type,url}` 자동 기재. `_write_session_settings` 가 첨부 스킬 중 untrusted 가 있으면 `disableSkillShellExecution: true` 주입
- [x] Step 5.2: `bot.yaml.sandbox.denied_domains` (snake_case) / `deniedDomains` (camelCase alias) 옵션 노출 → `compose_bot_sandbox(bot_config)` 가 settings.json 의 `sandbox.network.deniedDomains` 로 변환
- [x] Step 5.3: `DEFAULT_SANDBOX_DENIED_DOMAINS` — 클라우드 메타데이터 엔드포인트 7종 (GCP/AWS/Azure/Tencent/Aliyun). RFC1918 IP CIDR 은 CC 의 deniedDomains 가 도메인-only 라 도입 보류
- [x] Step 5.4: `docs/SECURITY.md` Phase 5 Hardening 섹션 추가 — 두 옵션의 위협모델 + 사용법

### Phase 6: ultrareview 패턴 + Skill effort 변수 (선택)

- [ ] Step 6.1: `claude ultrareview` 호출 래퍼 함수 (`claude_runner.run_ultrareview()`)
- [ ] Step 6.2: 신규 builtin skill `code_review` 추가 — Telegram 으로 PR URL 던지면 ultrareview 결과 회신
- [ ] Step 6.3: SKILL.md 템플릿에 `${CLAUDE_EFFORT}` 변수 사용 예시 추가
- [ ] Step 6.4: `bot.yaml` `effort` 필드 (기본 `high`) 추가, `claude_runner` 가 환경에 inject

## 5. 테스트 계획

### 단위 테스트

**Phase 1**
- [x] `tests/test_config.py::test_get_claude_code_env_defaults_no_config` — 기본값 5개 모두 활성
- [x] `tests/test_config.py::test_get_claude_code_env_user_disable` — `config.yaml` 에서 false 설정 시 누락 확인
- [x] `tests/test_config.py::test_get_claude_code_env_invalid_section_falls_back` — 잘못된 섹션 → 기본값 fallback
- [x] `tests/test_config.py::test_default_claude_code_config_keys` — 토글 키 4종 일관성
- [x] `tests/test_claude_runner.py::test_run_claude_injects_claude_code_env_without_skills` — 스킬 없어도 주입
- [x] `tests/test_claude_runner.py::test_run_claude_skill_env_overrides_claude_code_env` — 스킬 env 우선 머지
- [ ] `tests/test_sdk_client.py::test_sdk_env_injection` — `_prepare_skill_config` 단일 진입점이라 별도 SDK 테스트 불필요 (기존 테스트가 plumbing 검증)

**Phase 2**
- [x] `tests/test_conversation_search_mcp.py::test_tools_call_result_carries_max_size_meta` — 성공 분기 `_meta` 검증
- [x] `tests/test_conversation_search_mcp.py::test_tools_call_meta_present_on_error_branches` — 에러 분기 `_meta` 검증
- [x] `tests/test_conversation_search_inject.py::test_conversation_search_marked_always_load_by_default` — alwaysLoad 기본 주입
- [x] `tests/test_conversation_search_inject.py::test_conversation_search_omits_always_load_when_disabled` — 토글 false 시 미주입
- [x] `tests/test_conversation_search_inject.py::test_qmd_mcp_server_helper_marks_always_load` — QMD 헬퍼 동작
- [x] `tests/test_config.py::test_default_claude_code_config_includes_mcp_always_load` + `test_is_mcp_always_load_enabled_*` 3종 — config 헬퍼

**Phase 3**
- [x] `tests/test_precompact_hook.py::test_main_no_op_when_ai_agent_missing` + `test_main_no_op_when_ai_agent_other` — AI_AGENT 가드
- [x] `tests/test_precompact_hook.py::test_main_handles_*` 3종 — empty/invalid/non-object stdin 안전 처리
- [x] `tests/test_precompact_hook.py::test_resolve_bot_name_from_*` 3종 (DM, heartbeat, cron) + `test_resolve_bot_name_returns_none_when_outside_bots`
- [x] `tests/test_precompact_hook.py::test_main_no_op_when_cwd_outside_bots` — bots/ 외부 cwd 시 run_compact 미호출
- [x] `tests/test_precompact_hook.py::test_main_invokes_run_compact_with_resolved_bot` — 정상 경로
- [x] `tests/test_precompact_hook.py::test_main_swallows_run_compact_exception` — 실패해도 exit 0
- [x] `tests/test_claude_runner.py::test_write_session_settings_*` 7종 — settings.json 에 PreCompact entry 주입, 토글 false 시 생략, hook command 형식 검증, 기존 hook 보존

**Phase 4**
- [x] `tests/test_tool_metrics.py` 11종 — append/rotation/aggregation/percentile/corrupt-line tolerance
- [x] `tests/test_log_tool_metrics_hook.py` 9종 — guard, stdin handling, happy path, nested duration, exception swallow
- [x] `tests/test_claude_runner.py` 추가 4종 — PostToolUse 주입, hooks_enabled=false 옵트아웃, skill hook 머지 (`if` 필드)
- [x] `tests/test_skill.py::collect_skill_hooks` 4종 — supported events, malformed entries skipped, multi-skill concat
- [x] `abysscope/src/lib/__tests__/abyss.test.ts::getToolMetrics` 5종 — empty/aggregation/sort/malformed-line/multi-day ordering

**Phase 5**
- [x] `tests/test_skill.py::test_import_skill_from_github_marks_untrusted` — flag + provenance 자동 기재 (urllib mocking)
- [x] `tests/test_skill.py::test_is_untrusted_skill_*` 2종 + `test_has_untrusted_skill_aggregates`
- [x] `tests/test_config.py::test_default_sandbox_denied_domains_includes_metadata_endpoints` + 5종 — `compose_bot_sandbox` defaults / extras / camelCase / dedupe / malformed
- [x] `tests/test_claude_runner.py::test_write_session_settings_includes_default_sandbox` + 3종 — bot extras merge, untrusted toggle on/off

**Phase 6**
- [ ] `tests/test_claude_runner.py::test_ultrareview_invocation` — 명령 라인 조립

### 통합 테스트

- [ ] **시나리오 1 (Phase 1 검증)**: 봇 1개 시작 → handler 로 메시지 2회 → `claude` subprocess 의 환경에 5개 env 모두 존재 확인 (`ps -E` 또는 mock).
- [ ] **시나리오 2 (Phase 1 효과)**: heartbeat 5분 간격 10회 호출 → 1h cache TTL 효과로 cache_read 토큰 비율 ≥ 80% 확인 (`/usage` 또는 SDK metric).
- [ ] **시나리오 3 (Phase 1 cold-start)**: nonblocking on/off 비교, `claude -p "ping"` 첫 응답까지 시간 측정 — on 이 ≥ 0.5s 빠름.
- [ ] **시나리오 4 (Phase 2)**: conversation_search 가 5MB 분량 결과 반환할 때 truncate 없이 model 에 전달.
- [ ] **시나리오 5 (Phase 3)**: 봇 세션 컨텍스트 90% 도달 → PreCompact hook 자동 발화 → MEMORY.md 압축 결과 동일.
- [ ] **시나리오 6 (Phase 4)**: 봇에서 도구 호출 50회 → abysscope tool latency 패널에 p50/p95 표시.
- [ ] **시나리오 7 (Phase 5)**: GitHub 에서 임포트한 skill 의 SKILL.md 가 shell 명령 내장 → 실행 차단됨, 로그에 거부 이벤트.
- [ ] **시나리오 8 (Phase 6)**: 그룹 채팅에 PR URL 전송 → ultrareview 결과 분할 메시지 회신.

### 회귀 테스트
- [ ] `make lint && make test` 모든 phase 마다 통과
- [ ] SDK Pool 세션 연속성 (`--resume`) 영향 없음
- [ ] 그룹 오케스트레이터 라우팅 영향 없음
- [ ] streaming (`sendMessageDraft`) 영향 없음
- [ ] OpenAI compat backend 영향 없음 (이 plan 은 claude_code backend 한정)

## 6. 사이드 이펙트

### 잠재 부작용
- **prompt_caching_1h**: cache 가 길어져 정책 변경 시점에 stale 응답 가능. 영향 작음 — Anthropic 측 cache key 는 prompt prefix 해시.
- **fork_subagent**: heartbeat 가 자식 프로세스 spawn 빈도 증가. PID 누수 모니터링.
- **mcp_nonblocking**: MCP 가 늦게 붙는 동안 첫 도구 호출 실패 가능 → 재시도 로직(이미 3회) 으로 흡수.
- **hide_cwd**: 모델이 경로 기반 추론 (예: 사용자가 "~/.abyss/bots/ 에 무엇 있어?" 질문) 시 답변 품질 저하 — 사용자가 명시적으로 경로 줄 때는 그대로 유효.
- **PreCompact hook**: 동시에 여러 세션이 compact 트리거하면 LLM 호출 중복. 락(per-bot) 추가 필요.
- **MCP `_meta` size 확장**: 토큰 비용 ↑. conversation_search 가 50만 자 반환하면 한 메시지에 cache miss 시 큰 비용. 결과 limit 옵션 유지.
- **봇별 settings.json 생성 (Phase 3/4)**: `~/.abyss/bots/<name>/.claude/` 디렉터리 자동 생성. 사용자가 직접 편집한 경우 덮어쓰기 위험 → 생성 시 기존 파일 백업 (`.bak`) 후 머지 (단순 overwrite 금지). `~/.claude/settings.json` (사용자 글로벌) 은 절대 read/write 하지 않음.

### 하위 호환성
- 모든 변경은 default-on 이지만 `config.yaml` 에서 끌 수 있음.
- bot.yaml 스키마 추가 (`effort`, `sandbox`) 는 옵셔널.
- 기존 builtin skill / 사용자 skill 변경 없이 동작.
- OpenAI compat backend 영향 없음.

### 마이그레이션
- 기존 봇 재시작 시 자동 적용. 별도 마이그레이션 스크립트 불필요.
- abysscope tool latency 패널은 신규 데이터부터 표시.

## 7. 보안 검토

- **A01 Broken Access Control**: `disableSkillShellExecution` 자동 부여로 GitHub import skill 의 임의 명령 실행 위험 ↓. 통과.
- **A02 Cryptographic Failures**: cache 1h TTL 에 민감 정보 포함될 수 있음. CLAUDE.md 에 secret 미포함 정책 유지. 통과.
- **A03 Injection**: env 주입 시 사용자 입력 직접 사용 안 함 (config 값만). 통과.
- **A05 Security Misconfiguration**: `deniedDomains` 기본값에 메타데이터 IP/RFC1918 포함하여 SSRF 완화. 통과.
- **A08 Software/Data Integrity**: PreCompact hook 실행 → 신뢰된 abyss 코드만. exit code 2 차단 미사용 (가용성 우선). 통과.
- **A10 SSRF**: `sandbox.network.deniedDomains` 로 일부 차단. handler 의 외부 호출은 별도 plan 에서 다룸.
- 인증/인가 변경 없음. PCI-DSS 무관 (개인 데이터 비결제). 민감 데이터 처리 방식 변경 없음 (`hide_cwd` 는 모델 출력 마스킹만).

## 8. 완료 조건

- 각 Phase 의 구현 단계 체크리스트 100%
- 단위 + 통합 테스트 100%
- `make lint && make test` 통과
- 사이드 이펙트 7개 항목 각각 "해당 없음" 또는 "대응 완료" 명시
- `docs/TECHNICAL-NOTES.md`, `docs/SECURITY.md` 갱신 완료
- 본 문서 상단 `status: done` 기재

## 9. 중단 기준

- Phase 1 시나리오 2 에서 cache hit 비율이 50% 미만 → Anthropic 캐시 정책 재확인 후 plan 수정.
- Phase 2 통합 테스트 시 `_meta` 가 무시되는 SDK 버전 확인 → SDK 업그레이드 후 재시도.
- Phase 3 에서 PreCompact hook 이 SDK Pool 세션과 충돌 → token_compact 기존 경로 유지로 롤백.
- Phase 4 에서 telemetry 가 핫패스 latency 를 5% 이상 증가 → async batch flush 로 재설계.
- 보안 검토에서 신규 리스크 발견 → 즉시 중단.

## 10. PR 분할

| PR | Phase | 예상 LOC | 검증 우선순위 |
|----|-------|---------|--------------|
| #1 | Phase 1 | 200 | high |
| #2 | Phase 2 | 150 | high |
| #3 | Phase 3 | 300 | medium |
| #4 | Phase 4 | 500 (abysscope 포함) | medium |
| #5 | Phase 5 | 200 | high (보안) |
| #6 | Phase 6 | 400 | low (선택) |

각 PR 은 독립 검증, Phase 1/2/5 우선 머지.
