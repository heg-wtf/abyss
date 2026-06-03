# Plan: Phase 8.0 — Persona drift detection

- date: 2026-06-03
- status: approved
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

`docs/plan-coevolution-2026-05-19.md` 8번째 (마지막) 축 중 **persona drift** 만 집중. 봇의 personality 가 시간에 따라 어떻게 변하는지 — 특히 token_compact / SELF.md rewrite / ABOUT_ME 변동 / goals 추가 등의 누적 효과로 **봇이 더 이상 같은 봇이 아닌** 상황을 감지하고 사람에게 알린다.

가장 흔한 시나리오:
- compact 가 personality 섹션을 깎아서 톤이 무미건조해짐
- SELF.md 가 자기검열 방향으로 누적돼서 점점 소극적으로 변함
- goals 가 추가/제거되면서 우선순위가 흔들림

Provenance + conflict detection 은 8.1 / 8.2 로 미룬다.

## 2. 예상 임팩트

### 영향 모듈
- 신규: `src/abyss/persona_drift.py`, abysscope `/persona` 페이지
- 변경: `src/abyss/chat_server.py` (REST), `src/abyss/cli.py` (subapp), `src/abyss/cron.py` (digest dispatch), `src/abyss/hooks/precompact_hook.py` (post-compact diff)
- 디스크: 봇별 `bots/<name>/persona_snapshots.jsonl` (일평균 한 줄, 1줄 ~1KB)

### 성능
- 일일 snapshot = `compose_claude_md` 1회 호출 + sha256 + jsonl append. <50ms
- 주간 digest = LLM 1회 호출/주
- Compact 후 비교 = sha256 + section diff. <100ms

### UX
- Drift 발생 시 dashboard 알림 + Web Push
- 사용자는 `/persona` 페이지에서 daily snapshot 타임라인 + 섹션별 size sparkline 확인

## 3. 구현 방법 비교

### 방법 A: 일일 cron snapshot ✅
- 매일 새벽 (default `0 4 * * *`) cron 이 `compose_claude_md` 실행 → sha256 + 섹션 size 측정 → jsonl append
- 장점: 단순. 기존 cron 패턴 재사용
- 단점: 봇이 자기 personality 보지 않는 시점이라도 hash 는 변함 (외부 변경에도 반응)

### 방법 B: 매 응답마다 hash 갱신
- chat handler 가 응답 후 자동 계산
- 장점: real-time
- 단점: 모든 봇 응답에 overhead. 변동 없을 때 무의미

### 방법 C: 사람이 명시적으로 snapshot
- `abyss persona snapshot <bot>` 만 트리거
- 장점: 사용자 통제
- 단점: 자동성 없어 drift 추적 안 됨

**선택: 방법 A.** 일일 1회면 충분. cron 패턴 일관성.

## 4. 구현 단계

### 4.1 Storage (`persona_drift.py`)
- [ ] Dataclass `PersonaSnapshot` — `ts`, `hash` (sha256 of composed claude.md), `total_bytes`, `section_sizes` (dict: section_name → byte_count), `event` (string: "daily" / "post-compact" / "manual")
- [ ] `snapshots_path(bot)` → `bots/<name>/persona_snapshots.jsonl`
- [ ] `take_snapshot(bot, event="daily")` — composes claude.md, hashes, parses `## Section` headers to compute section sizes, appends
- [ ] `iter_snapshots(bot, since=None, limit=None)` — newest first
- [ ] `compute_drift(bot, window_days=7)` — compare latest vs window-ago — returns `{total_delta_bytes, section_deltas, hash_changed}`
- [ ] 단위 테스트: take/iter/compute_drift/missing file/malformed

### 4.2 PreCompact / PostCompact hooks
- [ ] `hooks/precompact_hook.py` 가 이미 있음 — 확장: pre snapshot 저장
- [ ] 신규 `hooks/postcompact_hook.py` — post snapshot + compute_drift(window=now-just-now) — Web Push if total shrinkage > 10%
- [ ] settings.json 에 `PostCompact` 훅 등록 자동화 (skill.py 처럼)
- [ ] 단위 테스트: snapshot 비교

### 4.3 Cron — daily snapshot + weekly digest
- [ ] `PERSONA_DAILY_JOB_NAME = "persona_snapshot"` — 매일 04:00, `take_snapshot(bot, event="daily")` 호출
- [ ] `PERSONA_DIGEST_JOB_NAME = "persona_digest"` — 매주 일요일 04:30, `build_drift_digest_prompt(bot)` 로 LLM 호출 → 결과 conversation log
- [ ] `cron.execute_cron_job` 분기 (episode_extract / goal_digest 패턴)
- [ ] CLI: `abyss persona schedule/unschedule`

### 4.4 chat_server REST
- [ ] `GET /persona/{bot}/snapshots?limit=N` — 최근 snapshot 리스트
- [ ] `GET /persona/{bot}/drift?window=7` — drift report
- [ ] `POST /persona/{bot}/snapshot` — 수동 트리거
- [ ] _validate_bot_name traversal 가드
- [ ] 단위 테스트

### 4.5 CLI
- [ ] `abyss persona show <bot>` — 최근 10 snapshot table
- [ ] `abyss persona drift <bot> [--window 7]` — drift report
- [ ] `abyss persona snapshot <bot>` — 수동 trigger
- [ ] `abyss persona schedule/unschedule <bot>`
- [ ] 단위 테스트: 6 cases

### 4.6 Dashboard
- [ ] `abysscope/src/app/persona/page.tsx`
- [ ] `abysscope/src/components/persona/persona-client.tsx` — bot picker + section size sparklines (last 30 days) + drift % badge + recent snapshot table
- [ ] `lib/abyss-api.ts` — `fetchPersonaSnapshots`, `fetchPersonaDrift`, `triggerPersonaSnapshot`
- [ ] sidebar entry `🧬 Persona`
- [ ] render 테스트 — 4 케이스

### 4.7 문서
- [ ] `CLAUDE.md` Core Modules 표에 `persona_drift.py` 추가
- [ ] `docs/TECHNICAL-NOTES.md` Phase 8.0 섹션
- [ ] `docs/plan-coevolution-2026-05-19.md` Phase 8.0 ✅

## 5. 테스트 계획

**단위 테스트 (예상 ~30):**
- storage: snapshot/iter/drift compute/section parse (10)
- hooks: pre/post snapshot + alert threshold (5)
- chat_server: 3 routes × 2-3 cases (8)
- CLI: 6
- dashboard render: 4

**통합:**
- 봇 1개로 snapshot 수동 호출 → jsonl 확인
- CLAUDE.md 일부 섹션 제거 → drift compute 가 shrinkage 감지
- Compact 시뮬레이션 (snapshot 가짜 변경) → alert 동작

## 6. 사이드 이펙트

- **CLAUDE.md compose 비용**: 매일 1회 (~50ms 추가). 무시 가능
- **jsonl 크기**: 봇당 일 1줄 × 365 = 365줄/년. backup 영향 미미
- **하위 호환**: 신규 파일만 생성. 기존 봇 동작 안 깨짐

## 7. 보안 검토

- **A01**: chat_server 라우트 `_validate_bot_name`
- **A03**: yaml/JSON 모두 safe. SQL 없음
- **A09**: drift > 10% 자동 로그 + Web Push
- **개인정보**: snapshot 은 composed CLAUDE.md 의 sha256 + section sizes — 본문은 저장 안 함 (원하면 옵션으로 ABYSS_PERSONA_SNAPSHOT_FULL=true)

## 8. 완료 조건

- 모든 테스트 통과
- ruff + pytest + abysscope green
- CI green
- 1개 봇으로 snapshot 수동 호출 → jsonl 확인
- PR merge + daemon restart

## 9. 중단 기준

- snapshot 비용 응답 latency 영향 (>5%)
- Section parse 가 한국어 / 이모지 section 헤더에 깨짐
- false positive drift alert (정상 변동도 alert)

## 10. Phase 8.1+ 로 미루는 것

- **Provenance** — MEMORY / ABOUT_ME 에 source 추가 (기존 데이터 migration)
- **Conflict detection** — 봇이 모순된 정보 마주칠 때 사용자 confirm 요청 흐름
- **Embedding-based drift** — cosine similarity 사용한 의미적 drift 측정 (현재는 byte size + hash)

## 11. 핵심 결정

1. **저장**: sha256 + section sizes (본문 X, 프라이버시 + 디스크 절약)
2. **빈도**: 일일 cron 04:00 + Compact 후 자동
3. **Alert threshold**: total bytes shrinkage > 10%
4. **Weekly digest**: 일요일 04:30 LLM digest
5. **Drift 측정**: byte-level (Phase 8.5 에서 embedding 도입 고려)
