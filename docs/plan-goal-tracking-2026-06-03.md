# Plan: Phase 6 — Goal Tracking

- date: 2026-06-03
- status: done
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

`docs/plan-coevolution-2026-05-19.md` 공진화 6번째 축. 현재 봇은 `bot.yaml` 의 free-form `goal` 필드 하나만 가지고 있다. 구조화된 sub-goal / 진척도 / KPI 추적이 없어, 봇이 "지난 주 대비 X 만큼 진척했다" 같은 자기 평가를 못 한다.

Phase 6 은 봇별 `goals.yaml` (구조화 sub-goal + 진척 로그) + `record_progress` MCP + 주간 digest cron + dashboard `/goals` 페이지를 도입한다. 측정 가능한 봇 (`cclawfinancebot 엘리`, `bobby 바비`) 부터 즉시 유효.

## 2. 예상 임팩트

### 영향 모듈
- 신규: `src/abyss/goals.py`, `src/abyss/mcp_servers/record_progress.py`, abysscope `/goals` 페이지
- 변경: `src/abyss/chat_server.py` (REST), `src/abyss/cli.py` (subapp), `src/abyss/claude_runner.py` (MCP 주입), `src/abyss/skill.py` (CLAUDE.md goals 섹션 주입), `src/abyss/cron.py` (digest dispatch)
- 디스크: 봇별 `bots/<name>/goals.yaml` (수십~수백 줄)

### 성능
- record_progress MCP = SQLite-free yaml append. 매우 가벼움
- Weekly digest cron = LLM 1회 호출/주 (digest 생성)
- CLAUDE.md 주입 = goals.yaml 요약 (top 3 active goals, 각 1줄) → 토큰 최소

### UX
- 봇이 자기 진척을 능동 기록 → 자기 회상 가능
- 사용자는 dashboard 에서 goal 추가/편집 + progress 로그 검토
- 주간 digest 가 conversation log 에 들어가 PWA Routines 탭에 표시

## 3. 구현 방법 비교

### 방법 A: 단일 `goals.yaml` (사용자 + 봇 공동 편집) ✅
- 사용자가 dashboard 또는 CLI 로 goal 추가
- 봇이 MCP `record_progress(goal_id, note)` 로 진척 append
- 장점: 단순. 모든 데이터 한 곳
- 단점: 동시 쓰기 우려 — atomic write 로 해결

### 방법 B: goal 정의 yaml + progress jsonl 분리
- `goals.yaml` (정의) + `progress.jsonl` (append-only)
- 장점: append 가 빠름, race 없음
- 단점: 파일 2개, 정합성 관리

### 방법 C: SQLite (`goals.db`)
- 장점: 인덱스
- 단점: 인간 친화성 손실, yaml 만큼 매력 없음. 데이터 규모 작아서 과잉

**선택: 방법 A.** atomic write + dedup-by-id 면 충분. 데이터 규모 작음 (봇당 goal 수십개 max).

## 4. 구현 단계

### 4.1 Storage (`goals.py`)
- [ ] Dataclass `Goal` — `id` (slug), `title`, `kpi` (free text, e.g. "MRR $10k"), `target` (optional), `status` (active/done/archived), `created_at`, `progress[]` (`{ts, note, value?}`)
- [ ] `goals_path(bot)` → `bots/<name>/goals.yaml`
- [ ] `list_goals(bot, status_filter=None)`, `get_goal(bot, id)`, `add_goal(bot, ...)`, `update_goal(bot, id, ...)`, `delete_goal(bot, id)`
- [ ] `record_progress(bot, goal_id, note, value=None)` — append to goal.progress
- [ ] Atomic write (tmp + os.replace)
- [ ] 단위 테스트: CRUD + dedup + atomic + missing/malformed

### 4.2 MCP server (`record_progress.py`)
- [ ] stdio MCP — single tool `record_progress(goal_id, note, value?)`
- [ ] cwd-walk caller resolve
- [ ] Validate goal exists for caller bot
- [ ] Best-effort Web Push: optional (silent for low noise)
- [ ] 단위 테스트: happy / unknown goal / empty note / bot resolve fail

### 4.3 claude_runner 자동 주입
- [ ] Always-on per bot (propose_skill / call_bot 패턴)
- [ ] `RECORD_PROGRESS_ALLOWED_TOOLS = ["mcp__record_progress__record_progress"]`

### 4.4 CLAUDE.md 주입 (skill.py)
- [ ] Gate: `goals.yaml` 존재 + active goals ≥ 1
- [ ] 섹션 형식: `## Goals` + active 별 1줄 (`<title> — <kpi> — last progress: <date>`)
- [ ] 봇은 진척 보면 record_progress 호출하도록 유도하는 안내문 한 줄
- [ ] Top 3 만 표시 (토큰 절약)

### 4.5 chat_server REST
- [ ] `GET /goals/{bot}?status=` — list
- [ ] `POST /goals/{bot}` — add
- [ ] `PUT /goals/{bot}/{goal_id}` — edit (title/kpi/target/status)
- [ ] `DELETE /goals/{bot}/{goal_id}` — delete
- [ ] `POST /goals/{bot}/{goal_id}/progress` — record progress (사람용; 봇은 MCP 사용)
- [ ] `_validate_bot_name` traversal 가드 재사용
- [ ] 단위 테스트: 각 라우트 happy + 404 + 400 + traversal

### 4.6 CLI
- [ ] `abyss goals show <bot> [--status active]`
- [ ] `abyss goals add <bot> <title> [--kpi ... --target ...]`
- [ ] `abyss goals progress <bot> <goal_id> "note" [--value N]`
- [ ] `abyss goals archive <bot> <goal_id>` / `done <bot> <goal_id>`
- [ ] `abyss goals delete <bot> <goal_id>`
- [ ] 단위 테스트: 10 케이스

### 4.7 Weekly digest cron
- [ ] `GOAL_DIGEST_JOB_NAME = "goal_digest"` reserve
- [ ] `goals.py::build_digest_prompt(bot)` — last 7 days progress + active goals 요약 프롬프트
- [ ] `cron.execute_cron_job` 분기 — episode_extract 와 동일 패턴
- [ ] 결과는 일반 cron output 처럼 `conversation-YYMMDD.md` 에 저장 + PWA Routines 표시
- [ ] CLI: `abyss goals schedule/unschedule`

### 4.8 Dashboard
- [ ] `abysscope/src/app/goals/page.tsx`
- [ ] `abysscope/src/components/goals/goals-client.tsx` — bot picker + active goals 카드 리스트 + 각 카드에 progress timeline (최근 5) + Add/Edit/Done/Archive 버튼
- [ ] `lib/abyss-api.ts` — `fetchGoals/addGoal/updateGoal/deleteGoal/recordProgress`
- [ ] sidebar entry `🎯 Goals` (skills 그룹 옆)
- [ ] render 테스트 — 6 케이스 (빈/active/done/progress/add/delete)

### 4.9 문서
- [ ] `CLAUDE.md` Core Modules 표에 `goals.py` 추가
- [ ] `docs/TECHNICAL-NOTES.md` Phase 6 섹션
- [ ] `docs/plan-coevolution-2026-05-19.md` Phase 6 ✅

## 5. 테스트 계획

**단위 테스트 (예상 ~50):**
- storage: CRUD + dedup + status filter + atomic + malformed (12)
- MCP: 4
- chat_server: 5 routes × 2-3 cases (12)
- CLI: 10
- digest prompt builder: 4
- dashboard render: 6

**통합:**
- 봇 1개에 goal 추가 → record_progress 호출 → goals.yaml 업데이트 → CLAUDE.md 에 active goals 섹션 노출 확인
- Weekly digest cron 수동 트리거 → digest markdown 생성 → PWA 표시

## 6. 사이드 이펙트

- **conversation.db**: digest cron 결과가 conversation log 에 들어가서 FTS5 인덱스에 자동 포함
- **CLAUDE.md**: 신규 섹션 1개 (token overhead ~50-100 per active goal)
- **하위 호환 100%** — goals.yaml 없으면 기존 동작 그대로

## 7. 보안 검토

- **A01**: chat_server 라우트 모두 `_validate_bot_name`. MCP 는 cwd-walk
- **A03**: yaml.safe_dump/safe_load 사용. SQL 없음. note 필드는 자유 입력 → escape 없이 yaml 저장 OK
- **A04**: record_progress 무한 호출 방지 — 봇이 자기 비용. dedup 안 함 (의도된 timeline)
- **A09**: 모든 액션 logger.info
- **개인정보**: progress note 에 민감정보 가능 — 로컬 저장만

## 8. 완료 조건

- 모든 테스트 통과
- ruff + pytest + abysscope green
- CI green
- 1개 봇 (e.g. ash84-blog-writer) 에 실제 goal 1개 추가 → MCP 호출 → 진척 기록 확인
- PR merge + daemon restart

## 9. 중단 기준

- MCP record_progress 가 봇별 일평균 >50회 (스팸) → 봇 측 호출 frequency cap
- Dashboard /goals 페이지 가독성 깨짐 (>20 goals) → 페이지네이션 추가
- Weekly digest LLM 비용 봇당 일 $0.10 초과 → digest 사이즈 cap

## 10. Phase 6 에서 빠진 것 (의도)

- **자동 goal 도출** — bot 이 대화에서 implicit goal 추출 (Phase 6.5)
- **Cross-bot goal 의존성** — bot 단위 격리
- **Quantitative KPI 그래프** — 우선 텍스트 timeline. sparkline 은 Phase 6.5

## 11. 핵심 결정

1. **단일 yaml** (사용자 + 봇 공유 store)
2. **MCP 항상 주입** (propose_skill / call_bot 패턴)
3. **CLAUDE.md gate**: goals.yaml 존재 + active goals 있을 때만
4. **Top 3 only** in CLAUDE.md (토큰 절약)
5. **Digest cron** 기본 `0 9 * * 1` (월요일 오전 9시)
6. **Dedup 없음** — progress 는 timeline 본질
