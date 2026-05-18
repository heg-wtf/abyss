# Plan: ABOUT_ME — 모든 봇이 공유하는 사용자 백과사전

- date: 2026-05-19
- status: in-progress
- author: claude
- approved-by: ash84 (Phase 2a 진행 승인)

## 목적 및 배경

`docs/plan-coevolution-2026-05-19.md` Phase 2 의 구체화.

현재 `~/.abyss/GLOBAL_MEMORY.md` 는:
- 평문 한 파일에 사용자 정보 다 섞임
- AI read-only — 새 사실 발견해도 다음 세션에 또 물어봄
- 출처·시점 메타 없음 — 오래된 정보 못 거름
- 봇 간 일관성 위해 모든 봇이 같은 파일 로드

본 작업은 이를 **카테고리별 마크다운 + frontmatter 메타** 구조 (`~/.abyss/ABOUT_ME/`) 로 바꾸고, 향후 AI propose / user confirm 양방향 편집 으로 확장 가능한 토대를 만든다.

## Phase 분리

### Phase 2a (이번 PR)
**Foundation — read-only schema + CLI + INDEX 주입**

- `~/.abyss/ABOUT_ME/` 디렉토리 구조 + frontmatter schema
- `src/abyss/about_me.py` — 로드 / 카테고리 목록 / 항목 CRUD (CLI 만, AI 는 아직 못 씀)
- `compose_claude_md()` 가 `INDEX.md` 주입 (모든 봇이 자동 참조)
- `abyss about-me` CLI: `init` / `show` / `list` / `edit` / `migrate`
- 마이그레이션 — 기존 `GLOBAL_MEMORY.md` 를 카테고리별 분할 (사용자 명시 invoke, 자동 X)

### Phase 2b (다음 PR)
**AI write — propose / confirm 양방향**

- MCP server `mcp_servers/about_me.py` — 봇이 새 사실 propose
- Auto-confirm: 같은 key 가 2회 propose → 승격
- 충돌 감지: `confirmed` 와 모순 → 봇이 사용자 확인 질문
- Dashboard 승인 UI — `/about-me` 페이지 + chat-side notification

## 데이터 모델 (Phase 2a)

### 디렉토리

```
~/.abyss/ABOUT_ME/
├── INDEX.md            # 한줄 요약, CLAUDE.md 에 주입
├── identity.md         # 이름·생일·직업·거주지
├── relationships.md    # 가족·동료·친구
├── preferences.md      # 좋아함/싫어함
├── routines.md         # 일과·운동·수면
├── current_focus.md    # 지금 몰입 중인 일
├── health.md           # 건강 상태
└── values.md           # 가치관·의사결정 기준
```

### 항목 포맷 (마크다운 본문 + 항목별 frontmatter)

각 카테고리 파일은 여러 **항목** 을 담는다. 항목 단위 frontmatter (`---` 구분자) 로 메타 기록.

`identity.md` 예시:
```markdown
# Identity

---
key: name
value: ash84
confidence: high
source: manual
added: 2026-05-19
last_confirmed: 2026-05-19
status: confirmed
---

본명 사용자명. 모든 봇이 호칭으로 사용.

---
key: email
value: ash84@payhere.in
confidence: high
source: manual
added: 2026-05-19
status: confirmed
---
```

### INDEX.md 포맷

`compose_claude_md` 주입용 한줄 요약. 봇 토큰 절약.

```markdown
# About Me — Index

- identity: 이름=ash84, 직업=엔지니어/CTO, 회사=Payhere
- relationships: wife(지혜), 자녀(2)
- preferences: 한국어 응답, 표 회피, 이모지 OK, 짧은 답 선호
- routines: 아침 운동, 야간 업무 회피
- current_focus: abyss 진화, financebot 운영
- health: (none)
- values: 엔지니어링 + 인플루언서 정체성
```

INDEX 갱신: 항목 추가/수정 시 자동 재생성 (`rebuild_index()`). 카테고리별 한 줄, value 짧은 항목만 (긴 항목은 "see X" 로 대체).

## 모듈 (`src/abyss/about_me.py`)

```python
ABOUT_ME_DIRNAME = "ABOUT_ME"
ABOUT_ME_CATEGORIES = (
    "identity", "relationships", "preferences",
    "routines", "current_focus", "health", "values",
)

def about_me_directory() -> Path:
    """Return ~/.abyss/ABOUT_ME."""

def about_me_file(category: str) -> Path:
    """Return ABOUT_ME/<category>.md."""

def ensure_about_me_scaffold() -> None:
    """Create ABOUT_ME/ + empty category files + INDEX.md (idempotent)."""

@dataclass
class AboutEntry:
    key: str
    value: str
    confidence: str = "high"          # high | medium | low
    source: str = "manual"             # manual | conversation:<path>
    added: str = ""                    # YYYY-MM-DD
    last_confirmed: str = ""
    status: str = "confirmed"          # confirmed | propose
    body: str = ""                     # markdown body following frontmatter

def load_category(category: str) -> list[AboutEntry]:
    """Parse a category file into entries (frontmatter + body)."""

def save_category(category: str, entries: list[AboutEntry]) -> None:
    """Write entries back. Rebuilds INDEX afterward."""

def upsert_entry(category: str, entry: AboutEntry) -> None:
    """Insert or replace by key. Rebuilds INDEX."""

def list_entries(category: str | None = None) -> dict[str, list[AboutEntry]]:
    """Return entries grouped by category."""

def rebuild_index() -> None:
    """Regenerate INDEX.md from all category files."""

def load_index() -> str:
    """Return INDEX.md content (empty string when missing)."""

def migrate_from_global_memory() -> dict[str, int]:
    """One-shot migration: read GLOBAL_MEMORY.md, classify via
    claude haiku, split into category files. Returns counts per
    category. Leaves GLOBAL_MEMORY.md in place (sourcing-only)."""
```

## CLAUDE.md 주입

`compose_claude_md()` 에 ABOUT_ME 섹션 추가 (global memory 다음, bot memory 앞):

```
## About Me (Shared)
- 아래는 모든 봇이 공유하는 사용자(ash84) 정보. 참고만 하고 직접 수정하지 마라.
  더 자세한 정보가 필요하면 `~/.abyss/ABOUT_ME/<category>.md` 를 읽을 수 있다.

<INDEX.md content>
```

Phase 2a 에서는 propose 권한 없으므로 "수정하지 마라" 명시.

기존 `## Global Memory (Read-Only)` 섹션은 마이그레이션 완료 후 ABOUT_ME 가 우선이므로 그대로 유지하되, INDEX.md 가 있으면 ABOUT_ME 우선 표시.

## CLI (`abyss about-me`)

```
abyss about-me init                    # 디렉토리 + 빈 카테고리 파일 + INDEX 생성
abyss about-me show [category]         # 전체 또는 카테고리 출력 (Rich markdown)
abyss about-me list                    # 모든 항목 key 만 (테이블)
abyss about-me edit <category>         # $EDITOR 로 카테고리 파일 직접 편집 + INDEX 재생성
abyss about-me migrate                 # GLOBAL_MEMORY.md → ABOUT_ME/* 분할 (확인 prompt)
```

## 마이그레이션 정책

- `abyss about-me migrate` 는 **명시적 invoke** 만. `init` / `start` 가 자동으로 안 함.
- 기존 `GLOBAL_MEMORY.md` **보존**: 마이그레이션 후에도 삭제 안 함. 사용자가 직접 정리.
- 분류 엔진: `claude_runner.run_claude` haiku 모델 일회성 호출. 시스템 프롬프트 — "다음 자유 텍스트를 7개 카테고리로 분할, 각 항목 frontmatter 채워서 출력."
- 분류 실패시: 모든 항목을 `current_focus.md` 에 dump + 사용자에게 경고.
- dry-run: `--dry-run` 플래그로 미리보기.

## 변경 파일

| 파일 | 변경 |
|---|---|
| `src/abyss/about_me.py` (신규) | 모듈 |
| `src/abyss/cli.py` | `about_me_app` sub-app + 5개 커맨드 |
| `src/abyss/skill.py` | `compose_claude_md` 에 INDEX 주입 |
| `tests/test_about_me.py` (신규) | 모듈 단위 테스트 |
| `tests/test_cli_about_me.py` (신규) | CLI 테스트 |
| `tests/test_skill.py` 또는 `test_compose_claude_md.py` | INDEX 주입 회귀 테스트 |
| `docs/plan-about-me-2026-05-19.md` | 본 문서 |
| `docs/plan-coevolution-2026-05-19.md` | Phase 2a 체크박스 갱신 |

## 보안

- `_validate_category()` — `ABOUT_ME_CATEGORIES` whitelist 만 허용
- frontmatter parser — `yaml.safe_load` 사용, 알 수 없는 키는 무시 (forward-compat)
- 파일 쓰기는 `abyss_home() / "ABOUT_ME"` 내부로만 (path traversal 차단)
- `migrate` 는 LLM 호출 — 외부 API 호출 새 surface 아님 (이미 cron `parse_natural_language_schedule` 패턴 동일)
- 민감정보 (health, identity) 로컬만, 외부 전송 없음

## 사이드 이펙트

- 기존 `GLOBAL_MEMORY.md` 동작 안 깨짐 (보존됨)
- `compose_claude_md` 출력 길이 증가 — INDEX.md 평균 < 500 토큰 예상. global memory 와 중복되면 사용자가 `migrate` 후 GLOBAL_MEMORY 직접 비울 수 있음
- 봇 행동 변화: INDEX 가 비어있으면 영향 0, 채워지면 봇이 사용자 정보 더 잘 앎
- 봇별 `MEMORY.md` 영향 0 (그대로 유지)

## 단계

- [ ] Step 1: `src/abyss/about_me.py` + 단위 테스트
- [ ] Step 2: `compose_claude_md` INDEX 주입 + 회귀 테스트
- [ ] Step 3: CLI `init` / `show` / `list` / `edit` + 테스트
- [ ] Step 4: CLI `migrate` (haiku 호출) + dry-run + 테스트
- [ ] Step 5: `make lint && make test` + 수동 검증
- [ ] Step 6: PR 생성, plan-coevolution Phase 2a 체크박스 갱신

## 테스트 계획

### 단위
- [ ] `ensure_about_me_scaffold` 빈 디렉토리에 7개 파일 + INDEX 생성
- [ ] `load_category` frontmatter 파싱 — 정상 / 누락 키 / 잘못된 yaml
- [ ] `save_category` 라운드트립 — load 후 save → 동일 내용
- [ ] `upsert_entry` 신규 추가 / 기존 key 교체
- [ ] `rebuild_index` 모든 카테고리 한 줄 요약 생성
- [ ] `list_entries(category)` 단일 카테고리 / 전체

### 통합
- [ ] `compose_claude_md` ABOUT_ME 섹션 포함 — INDEX 존재 시
- [ ] `compose_claude_md` ABOUT_ME 디렉토리 없을 때 회귀 없음

### CLI
- [ ] `about-me init` idempotent
- [ ] `about-me show identity` Markdown 출력
- [ ] `about-me list` 테이블 출력
- [ ] `about-me migrate --dry-run` 분류 미리보기, 실제 파일 안 씀
- [ ] `about-me migrate` — GLOBAL_MEMORY.md 없을 때 친절한 에러

### 수동
- [ ] `abyss about-me init` → 디렉토리 확인
- [ ] `abyss about-me edit identity` → 항목 추가 → INDEX 자동 재생성 확인
- [ ] `abyss start` → 봇 대화에서 봇이 새 정보 인지 확인 ("내 이름 알아?")

## 완료 조건

- 6 단계 100%
- `make lint && make test` 통과
- 수동 검증 3개 통과
- plan-coevolution Phase 2a 체크박스 갱신, status `in-progress`

## 중단 기준

- `compose_claude_md` 변경이 기존 봇 동작 깨뜨림
- 마이그레이션 LLM 분류 정확도 < 70% (수동 확인 시)
- INDEX 주입이 평균 응답 토큰 비용 > 10% 증가
- → 중단, plan 수정, 사용자 리뷰
