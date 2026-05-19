# Plan: abyss 인간-AI 공진화 (Co-evolution) 로드맵

- date: 2026-05-19
- status: in-progress
- author: claude
- approved-by: ash84 (Phase 1 — 권장 범위)

## 목적 및 배경

abyss 는 현재 "사용자가 메모리·skill·cron 을 일방향으로 작성하고 AI 가 그걸 읽는" 구조다.
Personal AI 가 사람과 함께 시간에 따라 **진화**하려면 양방향 학습 루프가 필요하다.
이 문서는 전체 시스템 진단 + 공진화에 필요한 8개 축 + 인프라급 보강 + 우선순위
+ 첫 단계(숫자 피드백 시그널, 구조화된 사용자 모델) 상세 설계를 담는다.

## 현재 상태 진단

### 저장 계층
- `bots/<name>/MEMORY.md` — 봇별 자유서식 markdown (AI write 가능)
- `~/.abyss/GLOBAL_MEMORY.md` — 전역 read-only (CLI 만 수정)
- `bots/<name>/conversation-YYMMDD.md` — 일별 대화 로그
- `bots/<name>/conversation.db` — SQLite FTS5 (BM25 키워드만)
- QMD HTTP MCP — 외부 markdown 지식

### 반영 계층
- `compose_claude_md()` 가 start/restart 시 personality + memory + skill 합성
- 첫 메시지에 global → bot memory → conversation 부트스트랩 1회 주입
- `--resume` 이후엔 Claude SDK 자체 컨텍스트

### 자기관찰 / 사전행동
- `tool_metrics.py` — 도구 호출 latency p50/p95/p99 만
- `heartbeat.py` — 사용자 정의 체크리스트. 외부 상태 점검용. 자기성찰 아님
- `cron.yaml` — 사용자가 직접 만듦. 봇이 스스로 cron 만들지 못함
- `token_compact.py` — 단순 압축. 모순 해결·계보 없음

### 결여 항목 요약
- 사용자 → 봇 피드백 시그널 채널 없음
- AI 가 사용자 모델을 능동적으로 갱신 못함 (GLOBAL_MEMORY read-only)
- 봇 자기반성 메커니즘 없음
- conversation → 사실 추출 파이프 없음
- 임베딩 기반 의미 검색 없음 (BM25 only, 한국어 형태소 미지원)
- 다중 봇 협업 surface 삭제됨 (v2026.05.14 group 제거)
- provenance / drift 감지 없음
- skill autonomy 없음 (봇이 skill 필요해도 사람이 import)

## 공진화 8개 축

### 1. Bidirectional Feedback Signal (숫자 입력)
- 봇 응답 직후 1-탭 평가: `1=좋음 2=별로 3=틀림`
- 저장: `bots/<name>/feedback.jsonl`
- 음성 모드: "일", "이", "삼" voice trigger
- 5턴 연속 `3` → persona 점검 alert
- 누적 데이터 → SELF.md 자가갱신 + 향후 DPO 데이터셋

### 2. Structured User Model (USER_MODEL/)
- `~/.abyss/USER_MODEL/` 카테고리별 분리:
  - `identity.md`, `relationships.md`, `preferences.md`, `routines.md`,
    `current_focus.md`, `health.md`, `values.md`, `INDEX.md`
- 각 항목 frontmatter:
  ```yaml
  key: wife-name
  value: "지혜"
  confidence: high
  source: bots/anne/conversation-260418.md#turn-12
  added: 2026-04-18
  last_confirmed: 2026-05-10
  status: confirmed   # or propose
  ```
- AI write 권한: 새 사실 발견 시 `status: propose` 로 추가 → dashboard 알림
  → 사용자 1탭 승인 → `confirmed`
- auto-confirm 조건: confidence=high + 사용자가 2회 이상 반복 언급
- 충돌 감지: 기존 `confirmed` 와 모순 → 봇이 사용자에게 질문
- 봇 주입: `compose_claude_md` 가 `INDEX.md` (한줄 요약) 만 주입
- 봇이 상세 필요시 MCP tool `user_model.get(category)` 호출

### 3. Self-Reflection (`SELF.md`)
- 봇별 `bots/<name>/SELF.md`
- 자기 실수 패턴, 자주 막히는 토픽, 짜증 트리거, 자기보정 규칙
- 주간 reflection cron — conversation + feedback 읽고 작성
- `compose_claude_md` 가 personality 다음에 SELF 섹션으로 주입

### 4. Episodic → Semantic 추출
- nightly cron — 어제 conversation 에서 fact / event / decision 추출
- `episodes.jsonl` (타임라인) + `facts.db` (주장-증거-신뢰도)
- 모순 발견 시 reconciliation prompt
- claude-mem 플러그인 패턴 참고

### 5. Skill Autonomy
- 봇이 skill gap 감지 → `skill_proposals.yaml` 작성 → dashboard 알림
- 사용자 1탭 → GitHub import + attach
- `skill.py:import_skill_from_github` 재사용

### 6. Goal Tracking
- 봇별 `goal.md` — sub-goal, KPI, last_progress_at
- heartbeat 가 갱신
- 주간 digest: "지난주 대비 X 진척"
- 측정가능 봇 (financebot 엘리·바비) 즉시 유효

### 7. Multi-bot Collaboration v2 (PWA-native)
- `@mention` routing — 한 세션에 여러 봇
- orchestrator = 일반 봇이 MCP tool `call_bot(name, message)` 호출
- 답은 같은 conversation log 에 봇별 prefix
- ROADMAP 명시 항목 (`docs/ROADMAP.md`)

### 8. Trust + Provenance + Drift
- 모든 MEMORY / USER_MODEL 항목 `source: <conversation-YYMMDD#turn-N>`
- 충돌 시 봇이 "예전엔 X, 지금 Y. 어느 쪽?" 확인
- persona drift 감지: 주간 personality hash 비교
- compact 가 personality 깎으면 alert

## 인프라 보강

- **임베딩 hybrid retrieval** — `conversation.db` 에 vector 컬럼, local sentence-transformers
- **한국어 형태소** — nori / mecab SQLite extension
- **Memory git versioning** — `~/.abyss/` auto-commit cron, rollback 가능
- **Privacy audit log** — 봇이 접근한 파일·MCP·URL jsonl, dashboard 검토
- **Attention rhythm 학습** — 응답 latency·시각 패턴 → 알림 타이밍 자동 조정
- **Preference dataset** — 피드백 + paired 응답 → 향후 fine-tune / DPO

## 우선순위

| 순위 | 항목 | 노력 | 영향 | 사유 |
|---|---|---|---|---|
| 1 | 숫자 피드백 시그널 | 소 | 대 | 다른 모든 진화의 연료 |
| 2 | USER_MODEL/ + AI write | 중 | 대 | 진짜 personal 됨 |
| 3 | SELF.md + reflection cron | 소 | 중 | 같은 실수 감소 |
| 4 | episodic → semantic 파이프 | 중 | 중 | 검색·일관성 |
| 5 | embedding hybrid + 한국어 | 중 | 중 | recall 즉시 개선 |
| 6 | multi-bot @mention | 대 | 중 | ROADMAP 명시 |
| 7 | provenance + drift | 중 | 중 | 신뢰성 |
| 8 | skill auto-propose | 소 | 소 | 편의 |

## 구현 단계

### Phase 1 — 숫자 피드백 시그널 (이번 PR, "권장" 범위)
- [x] `chat_server.py` `POST /feedback` 엔드포인트
- [x] `bots/<name>/feedback.jsonl` append (ts, turn_id, bot, session_id, signal, note)
- [x] PWA chat UI — 메시지 footer 에 `1` `2` `3` 버튼 (localStorage 영속)
- [ ] 음성 모드 — "일/이/삼" 인식 시 피드백 트리거 (다음 PR)
- [x] `abyss feedback show <bot>` CLI 통계
- [ ] 5연속 `3` → push notification "persona 점검 필요" (다음 PR)
- [x] 테스트: 단위(8) + 통합(6) + CLI(4) + 프론트엔드(6)

### Phase 2 — ABOUT_ME/ + AI write

#### Phase 2a (이번 PR) — foundation
- [x] `ABOUT_ME/` 디렉토리 schema (7 카테고리 + INDEX.md)
- [x] `about_me.py` 모듈 (frontmatter parse / upsert / list / rebuild_index)
- [x] `compose_claude_md` 에 INDEX 주입 (read-only)
- [x] CLI: `abyss about-me init | show | list | edit | migrate`
- [x] GLOBAL_MEMORY.md → ABOUT_ME/ 마이그레이션 (claude haiku 분류)
- [x] 테스트: 단위 15 + CLI 11 + compose 회귀 3

#### Phase 2b (이번 PR) — AI write
- [x] MCP server `about_me` (`mcp_servers/about_me.py`) with 4 tools:
      `about_me_propose`, `about_me_get`, `about_me_list_categories`,
      `about_me_search`. Auto-injected when `ABOUT_ME/` exists.
- [x] Builtin skill `builtin_skills/about_me/` (SKILL.md + skill.yaml + mcp.json)
- [x] Auto-confirm: same value re-proposed → promoted to `confirmed`
- [x] Conflict detection: different value vs existing `confirmed`
      adds a `<key>__conflict_<n>` propose with `conflicts_with` metadata
- [x] chat_server REST API: `/about-me/categories`, `/about-me/entries/{cat}`,
      `POST .../approve`, `POST .../reject`, `PATCH .../entries/{cat}/{key}`
- [x] Dashboard `/about-me` page (Next.js) — category tiles + status filter
      + approve/reject/edit per entry
- [x] Sidebar nav link with 👤 icon
- [ ] Chat-side notification badge → next PR (small follow-up)
- [ ] 봇별 SELF.md 와 연계 — reject 된 propose 가 자기반성에 누적 → Phase 3

### Phase 3 — SELF.md + reflection cron
- [ ] `bots/<name>/SELF.md` 템플릿
- [ ] `reflection.py` — 주간 conversation + feedback 분석
- [ ] cron 자동 등록 (옵션)
- [ ] `compose_claude_md` 주입

### Phase 4+ — 인프라 + 나머지 축
- 4 → 5 → 7 → 6 → 8 순

## 테스트 계획

### 단위 테스트 (Phase 1)
- [ ] `POST /feedback` 유효 score → jsonl append
- [ ] 잘못된 score (0, 4, str) → 400
- [ ] 봇 / 세션 존재하지 않음 → 404
- [ ] path traversal 차단 (`bot=../../../etc`)
- [ ] 5 연속 `3` 감지 → push 트리거

### 통합 테스트 (Phase 1)
- [ ] dashboard chat 에서 1 누르면 jsonl 에 한 줄 추가
- [ ] PWA mobile 에서 동일 동작
- [ ] 음성 모드 "일" → score=1 저장
- [ ] `abyss feedback show <bot>` 통계 출력

## 사이드 이펙트

- **conversation.db 영향 없음** — feedback 은 별도 jsonl
- **CLAUDE.md 영향 없음** — Phase 1 은 수집만, 봇 행동 안 바뀜
- **하위 호환** — 기존 봇 동작 안 깨짐, feedback 미사용 시 추가 비용 0
- **마이그레이션 불필요** — 새 파일만 생김

## 보안 검토

- **A01 (Broken Access Control)**: `/feedback` 도 chat_server 의 Origin allowlist 적용. bot/session 경로 traversal 차단 (`_is_path_under` 재사용)
- **A03 (Injection)**: `note` 필드는 사용자 입력 → jsonl 저장 시 json.dumps 로 escape. SQL 미사용
- **A04 (Insecure Design)**: 음성 트리거 "일/이/삼" 오인식 시 잘못된 score 저장 — 정정 API (`DELETE /feedback/<id>`) 필요
- **A09 (Logging Failures)**: feedback 자체가 로깅. 별도 audit log 불필요
- **개인정보**: `note` 에 민감정보 들어갈 수 있음. 로컬 저장만, 외부 전송 없음. PCI-DSS 무관

## 완료 조건

- Phase 1 체크리스트 100%
- `make lint && make test` 통과
- 실제 PWA + dashboard 에서 1/2/3 동작 확인 (사용자 검증)
- 사이드 이펙트 항목 "해당 없음" 또는 "대응 완료"

## 중단 기준

- jsonl append 가 chat latency 에 측정 가능한 영향 (>50ms p99)
- 음성 트리거 false positive 가 정상 대화 흐름 방해
- PWA UI 가 모바일 narrow 화면에서 가독성 깨짐
- → 즉시 중단, plan 업데이트, 사용자 리뷰
