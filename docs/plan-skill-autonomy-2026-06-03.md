# Plan: Phase 5 — Skill Autonomy

- date: 2026-06-03
- status: approved
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

`docs/plan-coevolution-2026-05-19.md` 공진화 5번째 축. 현재 봇이 도구 부족을 느끼면 사용자가 직접 skill 을 찾아 attach 해줘야 한다. Phase 5 는 **봇이 자기에게 부족한 도구를 인지하고 후보를 제안**, 사람은 dashboard 에서 1탭 승인하면 import + attach 까지 자동.

이미 `skill.py:import_skill_from_github(url)` + `attach_skill_to_bot(bot, name)` 가 있어 import 기계는 완성돼있다. 누락된 것은:

1. 봇이 "이 skill 이 있으면 좋겠다" 제안할 표면 (MCP tool)
2. 제안을 누적·중복제거 저장할 store (`skill_proposals.yaml`)
3. 사람이 검토·승인·거절하는 표면 (dashboard 페이지 + REST + CLI)
4. 승인 시 import + attach + CLAUDE.md regenerate 한 흐름으로 묶기
5. 새 제안 land 시 Web Push 알림

## 2. 예상 임팩트

### 영향 모듈
- 신규: `src/abyss/skill_proposals.py`, `src/abyss/mcp_servers/propose_skill.py`, abysscope `/skills/proposals` 페이지
- 변경: `src/abyss/chat_server.py` (라우트), `src/abyss/cli.py` (서브앱 확장), `src/abyss/claude_runner.py` (MCP 자동 주입), `src/abyss/skill.py` (CLAUDE.md 에 propose_skill 사용 안내 1줄)
- 디스크: 봇별 `bots/<name>/skill_proposals.yaml` (수십~수백 줄, 평소엔 비어있음)

### 성능
- propose_skill 은 봇이 능동 호출 → idle 비용 0
- 승인 시 import = `git clone` (네트워크) + write SKILL.md. 기존 surface 그대로
- Web Push: 새 제안 1건당 1회 전송

### UX
- 새 제안 land 시 dashboard 에 빨간 배지 + 사이드바 알림
- 사람 워크플로우: 알림 클릭 → 제안 본 후 ✅ Approve / ✗ Reject. Approve 면 import + attach + 봇 CLAUDE.md regenerate

## 3. 구현 방법 비교

### 방법 A: MCP tool 만 ✅
- `propose_skill(reason, candidate_url, alternative_urls?)` MCP 만 봇에 제공
- 봇은 stuck 일 때 / reflection / heartbeat 어느 흐름에서든 호출 가능
- 장점: 단일 진입점. 봇이 능동 판단
- 단점: 호출 빈도 봇 의지에 의존 → 안 부르면 영원히 비어있음

### 방법 B: MCP + reflection cron 자동 분석
- A + reflection cron 끝에 "지난 주 도구 부족 흔적 있나?" 별도 분석
- 장점: 봇이 자각 못 해도 자동 감지
- 단점: 별도 prompt + 토큰 추가, false positive 가능. SELF.md 흐름이랑 섞이면 헷갈림

### 방법 C: 휴리스틱 분석
- conversation 로그에서 "I don't have a tool for X" 패턴 grep 후 ChatGPT 에 매핑
- 장점: 봇 의지 무관
- 단점: 휴리스틱이 깨지기 쉬움. 환각 기반 매핑 불안

**선택: 방법 A.** 봇 자율성을 살리고 표면을 최소화. 호출 빈도 부족이 문제가 되면 Phase 5.5 에서 cron 동행 추가.

## 4. 구현 단계

### 4.1 Storage (`skill_proposals.py`)
- [ ] Dataclass `Proposal` — `id` (uuid), `bot`, `candidate_url`, `reason`, `alternative_urls`, `proposed_at` (ISO), `status` (`pending` / `approved` / `rejected`), `resolved_at`
- [ ] `proposals_path(bot)` → `bots/<name>/skill_proposals.yaml`
- [ ] `add_proposal(bot, candidate_url, reason, alts=[])` — dedup by `candidate_url`; same url 다시 들어오면 기존 id 반환, `reason` 누적 (`reasons: [...]`)
- [ ] `list_proposals(bot, status_filter=...)`, `get_proposal(bot, id)`, `update_proposal(bot, id, status)`
- [ ] Atomic write (tmp + os.replace)
- [ ] 단위 테스트: append/dedup/status update/missing file/yaml malformed

### 4.2 Approve flow (`skill_proposals.py`)
- [ ] `approve(bot, proposal_id)` — `import_skill_from_github(url)` → `attach_skill_to_bot(bot, name)` → `update_proposal(... status='approved')` → `compose_claude_md` 갱신은 호출자가 함 (skill.py 의 regenerate 함수 재사용)
- [ ] 실패 시 status 유지 + 에러 메시지 반환 (raise 안 하고 dict 반환)
- [ ] 단위 테스트: mock `import_skill_from_github` + `attach_skill_to_bot`, happy path / clone fail / attach fail

### 4.3 MCP server (`propose_skill.py`)
- [ ] stdio MCP — single tool `propose_skill(candidate_url, reason, alternative_urls?)`
- [ ] cwd-walk 로 봇 resolve (conversation_search / recall_fact 와 동일 패턴)
- [ ] 검증: `candidate_url` 은 `https://github.com/` prefix 강제 (안 그러면 import 단계에서 실패 → 노이즈)
- [ ] 호출 시 `add_proposal` + 즉시 `web_push.send_push` (best-effort, 실패 swallow)
- [ ] 단위 테스트: happy path / 비-GitHub URL 거부 / dedup / bot resolve 실패

### 4.4 claude_runner 자동 주입
- [ ] `RECALL_FACT` 와 동일 패턴 — 모든 봇에 항상 inject (facts.db 같은 조건 없음, 봇이 언제든 부를 수 있어야 함)
- [ ] `PROPOSE_SKILL_ALLOWED_TOOLS = ["mcp__propose_skill__propose_skill"]`
- [ ] CLAUDE.md 본문에 짧은 안내 1줄 — 어떤 상황에 호출하라

### 4.5 chat_server REST 라우트
- [ ] `GET /skill-proposals/{bot}?status=` — 리스트
- [ ] `POST /skill-proposals/{bot}/{id}/approve` — approve flow 호출 + 결과 반환
- [ ] `POST /skill-proposals/{bot}/{id}/reject` — status='rejected'
- [ ] `_validate_bot_name` traversal 가드 재사용
- [ ] 단위 테스트: 각 라우트 happy + 404 + 400 + traversal

### 4.6 CLI
- [ ] `abyss skills proposals show <bot> [--status pending]`
- [ ] `abyss skills proposals approve <bot> <id>`
- [ ] `abyss skills proposals reject <bot> <id>`
- [ ] 단위 테스트: 8 케이스

### 4.7 Dashboard
- [ ] `abysscope/src/app/skills/proposals/page.tsx`
- [ ] `abysscope/src/components/skills/proposals-client.tsx` — bot picker + 카드형 리스트 (URL / reason / alternative_urls) + Approve / Reject 버튼 + 결과 토스트
- [ ] `lib/abyss-api.ts` — `fetchSkillProposals`, `approveSkillProposal`, `rejectSkillProposal`
- [ ] sidebar 사이드 entry — `/skills/proposals` link (skills 카테고리 하단)
- [ ] pending 카운트 배지 — sidebar 의 skills 항목에 (전체 봇 합산)
- [ ] render 테스트 — 빈 / pending 있음 / approve / reject

### 4.8 알림
- [ ] `propose_skill` MCP 호출 시 `web_push.send_push(title=f"💡 {bot} 새 skill 제안", body=reason[:120])` — best-effort

### 4.9 문서
- [ ] `CLAUDE.md` Core Modules 표에 `skill_proposals.py` 추가
- [ ] `docs/TECHNICAL-NOTES.md` Phase 5 섹션 — storage / approve flow / MCP / 자동 주입 정책
- [ ] `docs/plan-coevolution-2026-05-19.md` Phase 5 ✅

## 5. 테스트 계획

**단위 테스트 (예상 ~40개):**
- storage: append/dedup/status/missing/malformed (8)
- approve flow: happy + 2 fail modes (3)
- MCP: happy + non-GitHub reject + bot-resolve fail + dedup (4)
- chat_server: 5 라우트 × happy+error (10)
- CLI: 8 케이스
- dashboard render: 5 케이스

**통합:**
- 봇 1개로 실제 propose_skill MCP 호출 → yaml 확인 → API GET → CLI approve → bot.yaml 갱신 + CLAUDE.md 에 skill 섹션 추가 확인
- Reject 시 yaml 만 갱신, bot 영향 X

## 6. 사이드 이펙트

- 기존 `skills` skill 페이지 (`/skills/builtin`, `/skills/custom`)와 충돌 없음 — proposals 는 별도 path
- `import_skill_from_github` 재사용 → 행위 변경 없음
- 봇 startup 시 모든 봇에 propose_skill MCP 자동 주입 — spawn 비용 미세 증가 (가벼운 stdio 서버 1개)

## 7. 보안 검토

- **A01**: chat_server Origin allowlist + `_validate_bot_name` 재사용
- **A03**: `candidate_url` GitHub host 강제. `git clone` 은 기존 import 흐름이 안전 (subprocess.run, fixed argv)
- **A04**: 무한 propose 방지 — dedup + bot 자기 호출이므로 사용자 입력 아님. Worst case 같은 URL 반복 → 1건만 저장
- **A06**: import 되는 skill 자체는 외부 코드 — 기존 `skill import-github` 와 동일 위험 모델. 사용자 명시 승인 (1탭) 필요
- **A09**: propose 실패 / approve 실패 모두 logger.warning
- **개인정보**: reason 에 사용자 정보 들어갈 가능성 — 로컬 저장만, 외부 전송 없음

## 8. 완료 조건

- [ ] 모든 단위 + 통합 테스트 통과
- [ ] ruff + pytest + abysscope lint/tsc/vitest green
- [ ] CI green
- [ ] 1개 봇으로 propose → approve → bot.yaml 갱신 확인
- [ ] PR squash merge + daemon restart 검증

## 9. 중단 기준

- propose_skill 호출이 봇별 일 평균 >20 회 (스팸) → 봇 측 호출 frequency cap 추가
- 같은 URL 이 repeated rejected 후 또 들어옴 → "rejected previously" 결과로 응답 (봇이 학습)
- approve 시 `git clone` 실패율 > 10% → URL 검증 강화

## 10. Phase 5 에서 빠진 것 (의도)

- **자동 reflection 분석** — Phase 5.5 로 미룸. 일단 MCP만으로 신호 충분한지 관찰
- **휴리스틱 conversation grep** — false positive 위험 vs 가치 미확정
- **Cross-bot 제안 공유** — 봇별 격리. 같은 skill 을 다른 봇이 또 제안하면 별도 row

## 11. 핵심 결정 사항 (사용자 확인)

1. **검출 방식**: MCP propose_skill 만 (방법 A)
2. **저장**: yaml (사람 친화)
3. **승인 시**: import + attach + CLAUDE.md regenerate 일괄
4. **거절**: 같은 URL 다시 들어오면 dedup 으로 1건. status 만 갱신
5. **GitHub URL 강제**: 호출 시 검증
6. **모든 봇에 자동 주입**: facts.db 같은 조건 없이 항상
