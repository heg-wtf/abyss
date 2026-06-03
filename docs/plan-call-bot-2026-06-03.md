# Plan: Phase 7.0 — call_bot MCP (orchestrator pattern)

- date: 2026-06-03
- status: approved
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

`docs/plan-coevolution-2026-05-19.md` Phase 7 (Multi-bot Collaboration v2)의 첫 단계. 현재는 각 봇이 독립 세션에서만 동작 — 한 봇이 다른 봇의 전문성을 필요로 할 때 사용자가 직접 다른 봇 세션으로 옮겨가야 한다.

Phase 7.0 은 **`call_bot(name, message)` MCP 도구**만 도입한다. 어떤 봇이든 orchestrator 가 될 수 있고, 다른 봇을 호출해 답을 받아 자기 응답에 녹여낸다. 세션 키텍처는 그대로 유지 — `@mention` 라우팅이나 멀티-봇 UI 는 Phase 7.1+ 로 미룬다.

> 비교: 기존 `delegate to subagent` (Task tool) 와의 차이 — Task tool 은 같은 LLM 컨텍스트의 sub-agent 를 띄우고 끝나면 사라진다. `call_bot` 은 **다른 봇의 personality / skills / MEMORY / SELF / facts** 까지 그대로 들고 응답한다. 즉 "킴에게 물어봐줘" 의 시맨틱.

## 2. 예상 임팩트

### 영향 모듈
- 신규: `src/abyss/mcp_servers/call_bot.py`
- 변경: `src/abyss/claude_runner.py` (MCP 자동 주입), `src/abyss/cli.py` (옵션 — 디버깅용 `abyss call-bot`), `docs/TECHNICAL-NOTES.md`, `CLAUDE.md`
- 디스크: 호출 받는 봇의 별도 세션 디렉토리 (`bots/<peer>/peer_call_sessions/from_<caller>/`) — 호출 컨텍스트 격리

### 성능
- 한 호출 = 별도 LLM 라운드트립 + 별도 SDK 세션. orchestrator 응답시간 = 자기 시간 + peer 시간 + 자기 정리 시간
- Loop guard: max 3-depth (call_bot → 그 봇이 또 call_bot → ... 무한루프 방지)
- Timeout: 호출당 기본 120s

### 격리
- Peer 봇은 자기 `CLAUDE.md` + `MEMORY.md` + `SELF.md` + facts + skills 그대로 사용
- Peer 응답은 caller 의 conversation log 에 `[via <peer>]` annotation 으로 기록
- Peer 의 자체 conversation log 에는 호출 흔적이 안 남음 (격리). 단, audit 가 필요하면 `peer_call_sessions/from_<caller>/` 에 별도 log

## 3. 구현 방법 비교

### 방법 A: SDK pool 재사용 — 별도 session_key ✅
- `get_or_create(peer_bot, peer_bot_config)` 로 peer SDK 클라이언트 가져옴 (이미 chat / cron 과 공유 풀)
- `LLMRequest(session_key=f"peer_call:{caller}:{peer}:{turn_id}")` — 호출별 격리, 각 호출은 한 턴짜리 fresh session
- 장점: 기존 인프라 그대로. 봇 personality / skills 모두 자동 적용
- 단점: 매 호출 fresh — peer 가 컨텍스트 누적 못함 (단발 의도라 OK)

### 방법 B: Peer 의 기본 chat session 재사용
- Peer 의 `chat_web_<id>` 세션에 메시지 던지고 응답 받기
- 장점: peer 가 이전 대화 기억 누적
- 단점: 누가 호출했는지 모름 → personality 일관성 깨질 가능성. 사용자 본인 채팅과 섞임 (혼란)

### 방법 C: HTTP REST 통신 (chat_server)
- caller 가 chat_server 의 `/chat` 엔드포인트 POST
- 장점: 외부 도구도 동일 패턴
- 단점: 같은 프로세스 안에서 self-call → 비효율. 인증/허락 처리 복잡

**선택: 방법 A.** SDK pool 재사용 + 격리 session_key. 단순하고 빠름.

## 4. 구현 단계

### 4.1 MCP server (`call_bot.py`)
- [ ] stdio MCP — single tool `call_bot(bot, message, timeout?)`. 입력 검증: bot 존재, 자기 자신 호출 거부, message 길이 cap (4KB)
- [ ] Loop-depth guard — env `ABYSS_CALL_BOT_DEPTH` 카운트. 호출할 때 +1, 3 도달하면 reject. 자식 MCP 서버 환경에 누적되도록 spawn 시 env 전파
- [ ] Caller resolve — cwd 워크로 bot 식별 (다른 MCP 서버와 동일 패턴)
- [ ] `get_or_create(peer)` → `LLMRequest(working_directory=<peer's call sessions>, session_key=f"peer_call:{caller}:{peer}:{ts}", user_prompt=message, timeout=...)` → `result.text` 리턴
- [ ] 답에 `[via <peer>]` prefix 안 붙음 (caller LLM 이 자기 prose 에 녹임)
- [ ] 단위 테스트: happy / 자기 호출 거부 / 미존재 봇 / depth cap / timeout 전파

### 4.2 claude_runner 자동 주입
- [ ] 모든 봇에 항상 inject (propose_skill 와 동일 패턴, 게이트 조건 없음)
- [ ] `CALL_BOT_ALLOWED_TOOLS = ["mcp__call_bot__call_bot"]`
- [ ] env 에 `ABYSS_CALL_BOT_DEPTH` 전파 — 기본값 "0" 으로 set

### 4.3 Caller 의 대화 로그 annotation
- [ ] MCP 결과 텍스트에 `[via <peer>]` 접두 + 컴팩트 metadata (peer 이름, latency ms)
- [ ] caller 의 LLM 이 자기 응답에 인용하는 것은 본인 책임 — MCP 결과 텍스트가 명확하면 자연스럽게 인용됨

### 4.4 CLI (선택 — 디버깅용)
- [ ] `abyss call-bot <caller> <peer> "message"` — depth=0 시뮬레이션. 실제 사용 사례는 봇이 직접 호출
- [ ] 단위 테스트 3건

### 4.5 문서
- [ ] `CLAUDE.md` Core Modules 표에 `mcp_servers/call_bot.py` 추가
- [ ] `docs/TECHNICAL-NOTES.md` Phase 7.0 섹션 — depth guard / session 격리 / loop 방지
- [ ] `docs/plan-coevolution-2026-05-19.md` Phase 7 ✅ (부분 완료 표시)

## 5. 테스트 계획

**단위 테스트 (예상 ~20):**
- MCP: happy path / self-call reject / unknown bot 404 / depth cap / message 길이 / timeout / bot resolve fail
- claude_runner: always-on 주입 확인
- CLI: 3개 케이스

**통합 테스트:**
- 봇 A 가 `call_bot(B, "...")` 호출 → B 가 자기 personality 로 답변 → A 가 자기 응답에 녹임 (수동)
- depth=3 도달 시 reject 동작 확인

## 6. 사이드 이펙트

- **기존 chat / cron / heartbeat 영향 없음** — 별도 session_key 사용
- **SDK pool**: peer 봇의 클라이언트가 캐시됨 → 메모리 약간 증가 (이미 정책상 OK)
- **`/skill_proposals.yaml` 등 다른 yaml/db 영향 없음**
- **하위 호환 100%** — 봇이 도구 안 부르면 동작 변화 0

## 7. 보안 검토

- **A01 (Broken Access Control)**: caller bot 식별은 cwd-walk → spoofing 불가능 (다른 MCP 서버와 동일 모델). peer bot 호출 시 peer 의 config 그대로 적용 → 권한 escalation 없음
- **A04 (Insecure Design)**:
  - 무한 루프 → depth guard 3
  - DoS → timeout 120s + max 4KB message + caller 봇이 자기 토큰으로 비용 부담
- **A07 (Identification Failures)**: peer 가 caller 의 정체를 모름 — 의도된 설계 (peer 가 caller 신원으로 행동 변경 안 함). 필요 시 message 본문에 caller 가 자기 정체 명시
- **A09 (Logging)**: 모든 호출 logger.info. peer 의 `peer_call_sessions/from_<caller>/conversation-YYMMDD.md` 에 audit log

## 8. 완료 조건

- 단위 + 통합 테스트 통과
- ruff + pytest + abysscope green
- CI green
- 봇 1쌍으로 실제 call_bot 호출 → 응답 받음 확인
- PR merge + daemon restart

## 9. 중단 기준

- depth guard 가 의도와 다르게 동작 (자식 MCP env 미전파 등) → 즉시 중단
- SDK pool conflict (peer client 가 caller client 와 race) → 중단, 별도 client 분리
- Peer 봇이 자기 chat session 의 메모리를 오염시킴 (의외의 부작용) → working_directory 격리 강화

## 10. Phase 7.1+ 로 미루는 것

- **@mention 라우팅** (chat_server `/chat` 핸들러 변경) — UI/UX 영향이 커서 별도 PR
- **멀티-봇 PWA 세션** (한 화면에 여러 봇 표시) — 디자인 결정 필요
- **Peer 의 자체 chat session 사용** — 현재는 격리 세션. 사용자 명시 요청 시 변경

## 11. 핵심 결정

1. **세션 격리**: 매 호출 fresh, `peer_call_sessions/from_<caller>/` 디렉토리
2. **Depth guard**: 3 (env 전파)
3. **자기 호출**: reject
4. **자동 주입**: 모든 봇 (propose_skill 와 동일)
5. **타임아웃**: 120s, 호출당 cap
6. **메시지 크기**: 4KB
