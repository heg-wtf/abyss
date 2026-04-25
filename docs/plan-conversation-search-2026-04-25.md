# Plan: Cross-session conversation search via SQLite FTS5

- date: 2026-04-25
- status: done
- author: claude
- approved-by: ash84 (2026-04-25)
- completed: 2026-04-25

---

## 1. 목적 및 배경

### 문제 정의

abyss는 봇과 사용자 사이의 모든 대화를 `~/.abyss/bots/<name>/sessions/chat_<id>/conversation-YYMMDD.md` (그룹은 `~/.abyss/groups/<name>/conversation/YYMMDD.md`)에 마크다운으로 누적한다. 그러나 Claude는 이 파일을 자동으로 읽지 않는다.

현재 Claude가 과거 맥락을 참조할 수 있는 경로는 세 가지뿐이다.

1. 현재 컨텍스트 윈도우 — 토큰 한계에 도달하면 가장 오래된 메시지부터 롤아웃.
2. `--resume <session_id>` — 직전 Claude Code 세션을 복원하지만, 그 세션의 컨텍스트 한계 안에서만.
3. `MEMORY.md` — Claude가 **요약을 쓰기로 한 것만** 저장. 나머지 대화는 검색 불가능.

결과: 사용자가 "지난주에 추천해 달라고 했던 카페 이름 뭐였지?" 같은 고유명사·날짜 회상 질문을 하면 Claude가 모른다. 메모리에 올라가지 않은 모든 정보는 영구 소실된다.

### 동기

비교 분석 (`docs/comparisons/Comparison-Hermes-OpenClaw-Abyss`)에서 확인된 가장 큰 메모리 갭을 메우는 작업이다. Hermes는 FTS5 + LLM 요약 + Honcho dialectic 사용자 모델링을 묶은 학습 루프를 가지고 있고, 이 중 가장 가벼운 부분(전문 검색)을 abyss에 도입하면 다음을 얻는다.

- **고유명사·날짜·인물 회상** — 요약에 안 들어간 디테일을 Claude가 직접 검색.
- **`/reset` 후 맥락 복구** — 세션을 비워도 과거 대화에서 필요한 부분만 다시 끌어옴.
- **그룹 미션 회고** — 오케스트레이터가 "이 멤버한테 저번 주에 맡긴 일 결과는?" 물을 때 답변 가능.
- **하트비트 토큰 절약** — 전체 로그를 시스템 프롬프트에 붓지 않고, 관련 스니펫만 검색해서 주입.
- **봇간 참조 잠재력** — `GLOBAL_MEMORY.md`를 수동으로 편집하지 않아도 봇 A의 대화를 봇 B가 검색 도구로 조회.

### 비목표 (out of scope)

- LLM 기반 자동 요약 (Hermes의 `SOUL.md` 방식). 이건 후속 작업.
- 사용자 모델링 (Honcho dialectic). 후속 작업.
- 임베딩 기반 시맨틱 검색. 시작은 BM25 키워드 검색만.
- QMD 대체. QMD는 사용자의 개인 노트용. conversation-search는 봇 대화용. 두 검색은 공존한다.

---

## 2. 예상 임팩트

### 영향받는 모듈

| 모듈 | 변경 종류 | 영향 |
|---|---|---|
| `src/abyss/conversation_index.py` | 신규 | DB 추상화 (스키마, append, search, reindex) |
| `src/abyss/mcp_servers/conversation_search.py` | 신규 | MCP stdio 서버, `search_conversations` 도구 노출 |
| `src/abyss/builtin_skills/conversation_search/` | 신규 | SKILL.md + skill.yaml + mcp.json |
| `src/abyss/session.py` | 수정 | `log_conversation()` 후크에서 인덱스 append |
| `src/abyss/group.py` | 수정 | `log_to_shared_conversation()` 후크에서 인덱스 append |
| `src/abyss/skill.py` | 수정 | `compose_claude_md()`에서 conversation_search MCP 자동 주입 (QMD 패턴 차용) |
| `src/abyss/bot_manager.py` | 수정 | 봇 시작 시 `ensure_schema()` 호출 |
| `src/abyss/cli.py` | 수정 | `abyss reindex` 서브커맨드 추가 |
| `src/abyss/onboarding.py` | 수정 | `abyss init` env check에 FTS5 가용성 검증 |
| `tests/test_conversation_index.py` | 신규 | 단위 테스트 |
| `tests/test_conversation_search_mcp.py` | 신규 | MCP 서버 테스트 |
| `tests/test_session.py` | 수정 | `log_conversation` 인덱스 사이드이펙트 검증 |

### API/인터페이스 변경

- 새 MCP 도구: `search_conversations(query, since=None, until=None, limit=20, scope="bot")`. Claude가 시스템 프롬프트의 SKILL.md를 보고 호출.
- 새 CLI: `abyss reindex [--bot NAME | --group NAME | --all]`. 마크다운에서 인덱스 재구축.
- 사용자 대상 슬래시 명령은 추가하지 않음. 검색은 Claude가 자율적으로 호출하는 도구.

### 성능

- `log_conversation()` 한 번 호출당 SQLite INSERT ~1ms. 사용자 인지 불가능.
- 검색 1회 (10k 메시지 기준) BM25 ranking ~10ms. MCP stdio 왕복 포함 ~50ms.
- 인덱스 파일 크기: 메시지 1만 개당 약 10 MB (FTS5 + raw content).

### 사용자 경험 변화

- Claude가 갑자기 "그때 말씀하신 ~~"를 회상하기 시작 — 이게 본 작업의 의도된 변화.
- `~/.abyss/bots/<name>/conversation.db`, `~/.abyss/groups/<name>/conversation.db` 파일 신규 생성. backup.py가 이미 `~/.abyss/` 전체를 zip 하므로 백업/복구 변경 없음.
- 기존 마크다운 로그는 변경 없음. 인덱스는 항상 마크다운에서 재생성 가능 (마크다운이 source of truth).

### 가용성

- Python 표준 라이브러리 `sqlite3`만 사용. `pyproject.toml` 의존성 추가 없음.
- FTS5는 stdlib SQLite의 컴파일 옵션. macOS/Linux의 일반적 빌드는 포함. `abyss init`이 이걸 검증하므로 미지원 환경에서는 명확한 에러로 안내.

---

## 3. 구현 방법 비교

### 방법 A: SQLite FTS5 (선택)

- Python `sqlite3` stdlib + FTS5 가상 테이블.
- 인덱스 파일: 봇별 `~/.abyss/bots/<name>/conversation.db`, 그룹별 `~/.abyss/groups/<name>/conversation.db`.
- BM25 랭킹 내장.
- `unicode61` 토크나이저 + `remove_diacritics 2` (한국어 + 영어 + 일본어 가나 모두 처리).

**장점**
- 의존성 0개 (stdlib).
- 별도 프로세스/서버 없음 ("로컬 우선" 스탠스 유지).
- 백업 zip에 자동 포함.
- 봇 디렉터리 삭제 = 인덱스 자동 정리 (소유권 단순).
- 검색 100ms 이내.

**단점**
- Python 빌드에 FTS5 미포함 시 동작 불가 (대부분의 환경에선 문제 없음).
- 한국어 형태소 분석 없음 (어절 단위 매칭). "갈비탕" 검색 시 "갈비탕이"가 매칭됨 (prefix). "짬뽕"으로 "짬뽕집"은 매칭 안 됨 — 사용자가 충분한 키워드를 줘야 함. 실용 시나리오에서 큰 문제는 아니라고 판단.

### 방법 B: tantivy (Rust 기반 Python 바인딩)

- pip 패키지 1개 추가, 휠에 Rust 바이너리 포함.
- 풍부한 검색 옵션 (퍼지, 패싯).

**장점**
- 매우 빠름 (FTS5보다 한 자릿수 빠름).
- 한국어 토크나이저 옵션 일부 존재.

**단점**
- 의존성 추가 + 휠 크기 +20MB.
- macOS/Linux/Windows 모두 빌드된 휠이 필요 (Termux/iOS 사용 가능성 미확인).
- abyss 규모에선 FTS5 성능으로 충분.

### 방법 C: ripgrep + 점수 휴리스틱

- `rg --json` 호출, 결과를 점수 매김.

**장점**
- 의존성 매우 가벼움 (rg 바이너리만).
- 인덱스 파일 없음.

**단점**
- 마크다운 1만 개 grep 시 수 초 — 검색 응답성이 나쁨.
- BM25 같은 랭킹 직접 구현 필요.
- 메시지 단위 메타데이터 (date, role) 추출은 별도 파서.

### 방법 D: Whoosh (순수 Python)

- 의존성 1개 (pure Python, 휠 작음).

**장점**
- 의존성 가벼움.

**단점**
- FTS5보다 느림 (1만 메시지에 ~수백 ms).
- 단일 프로세스 동시 쓰기 불가 (FTS5도 비슷하지만 SQLite는 더 견고).
- 유지보수 인구 소수.

### 결론

**방법 A (SQLite FTS5) 선택.** abyss 철학("로컬 우선, 추가 서버 프로세스 없음, 의존성 최소")과 가장 잘 맞고, 스택 크기 0 증가, 성능 충분.

---

## 4. 구현 단계

### Phase 1 — 인덱스 코어

- [ ] Step 1.1 — `src/abyss/conversation_index.py` 생성. 함수 시그니처:
  - `db_path_for_bot(bot_name: str) -> Path`
  - `db_path_for_group(group_name: str) -> Path`
  - `ensure_schema(db_path: Path) -> None` — FTS5 테이블 + indexer_state 테이블 생성 (idempotent)
  - `append(db_path: Path, *, chat_id: str, ts: datetime, role: str, content: str) -> None`
  - `search(db_path: Path, *, query: str, since: datetime | None, until: datetime | None, chat_id: str | None, limit: int) -> list[SearchHit]`
  - `reindex_from_markdown(db_path: Path, conversation_dir: Path) -> int` — 마크다운 파일 전체 다시 읽어 INSERT
  - `is_fts5_available() -> bool` — env check용
  - 데이터클래스 `SearchHit(chat_id, ts, role, snippet, score, raw_content)`
- [ ] Step 1.2 — FTS5 스키마 결정 + `ensure_schema()` 구현.
  ```sql
  CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
      content,
      chat_id UNINDEXED,
      role UNINDEXED,
      ts UNINDEXED,
      date_key UNINDEXED,         -- 'YYYY-MM-DD' for cheap date filter
      tokenize='unicode61 remove_diacritics 2'
  );
  CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
  INSERT OR IGNORE INTO schema_version (version) VALUES (1);
  ```
- [ ] Step 1.3 — `append()` 구현. 파라미터화 쿼리 사용. 동시쓰기는 SQLite WAL 모드로 설정.
- [ ] Step 1.4 — `search()` 구현. BM25 랭킹 (`bm25(messages)`), 스니펫 (`snippet(messages, 0, '<<', '>>', '...', 32)`). `since`/`until`/`chat_id`는 WHERE 절 필터.
- [ ] Step 1.5 — `reindex_from_markdown()` 구현. 마크다운 파서: 헤더 `## YYYY-MM-DD HH:MM:SS user/assistant` 감지, 본문 누적. 기존 `conversation-YYMMDD.md` 포맷 분석은 `session.py:log_conversation` (line 225-241) 확인.
- [ ] Step 1.6 — 한국어 + 영어 + 이모지 혼용 텍스트 인덱싱/검색 동작 검증 스크립트 (개발자용 sanity check).

### Phase 2 — 로깅 후크

- [ ] Step 2.1 — `src/abyss/session.py:log_conversation()` (line 225) 수정. 마크다운 append 직후 `conversation_index.append()` 호출. 인덱스 실패는 warning 로그만 남기고 메시지 처리 계속 (마크다운은 source of truth).
- [ ] Step 2.2 — `src/abyss/group.py:log_to_shared_conversation()` 수정. 동일 패턴.
- [ ] Step 2.3 — `src/abyss/bot_manager.py:_run_bots()` (line 38) 봇 시작 시 `conversation_index.ensure_schema(db_path_for_bot(bot_name))` 호출 추가.
- [ ] Step 2.4 — 그룹 인덱스 ensure는 `bind_handler` (`handlers.py:1599`) + `_run_bots` 시작 시 모든 그룹에 대해 수행.

### Phase 3 — MCP 서버

- [ ] Step 3.1 — `src/abyss/mcp_servers/__init__.py` (빈 패키지).
- [ ] Step 3.2 — `src/abyss/mcp_servers/conversation_search.py`. MCP stdio 프로토콜 직접 구현 (의존성 없음, JSON-RPC over stdin/stdout). 기준 SDK가 있다면 사용 검토 — 다만 `claude-agent-sdk`는 클라이언트용. 서버 구현은 100줄 이내로 충분.
  - 도구: `search_conversations(query, since=None, until=None, chat_id=None, limit=20)`
  - DB 경로는 환경변수 `ABYSS_CONVERSATION_DB`에서 읽음
  - 응답 포맷: 결과 배열, 각 hit에 `date`, `role`, `snippet`, `score`
- [ ] Step 3.3 — Python에서 `python -m abyss.mcp_servers.conversation_search` 실행 가능하도록 `__main__` 가드 추가.

### Phase 4 — 빌트인 스킬 + 자동 주입

- [ ] Step 4.1 — `src/abyss/builtin_skills/conversation_search/SKILL.md` 작성.
  - 한글 (config.yaml language=ko 기본)
  - 도구 사용 시점: 사용자가 과거 정보를 묻거나, 회상이 필요하거나, 토큰 절약을 위해 관련 스니펫만 끌어와야 할 때
  - 검색 쿼리 작성 팁: 키워드 위주, 너무 짧으면 결과 폭발
  - since/until 활용 예시
- [ ] Step 4.2 — `src/abyss/builtin_skills/conversation_search/skill.yaml`. type=mcp, allowed_tools=[]. 빌트인 마크.
- [ ] Step 4.3 — `src/abyss/builtin_skills/conversation_search/mcp.json`:
  ```json
  {
    "mcpServers": {
      "conversation_search": {
        "command": "python",
        "args": ["-m", "abyss.mcp_servers.conversation_search"],
        "env": {
          "ABYSS_CONVERSATION_DB": "${ABYSS_CONVERSATION_DB}"
        }
      }
    }
  }
  ```
- [ ] Step 4.4 — `src/abyss/skill.py:compose_claude_md()` (line 377) 수정. QMD 자동 주입 패턴 (`_load_qmd_builtin_markdown` line 281)을 모방하여 conversation_search SKILL.md 자동 합치기. 환경 변수 `ABYSS_CONVERSATION_DB`는 봇 컨텍스트에서 `db_path_for_bot(bot_name)`으로 치환.
- [ ] Step 4.5 — `src/abyss/skill.py:merge_mcp_configs()` (line 544) 수정. 자동 주입된 conversation_search MCP를 다른 스킬 MCP 설정과 머지. `${ABYSS_CONVERSATION_DB}` 변수 치환 처리.
- [ ] Step 4.6 — 그룹 컨텍스트에서는 그룹용 DB 경로로 치환 (오케스트레이터/멤버 모두). `compose_group_context()` (line 296) 협력.

### Phase 5 — CLI

- [ ] Step 5.1 — `src/abyss/cli.py`에 `reindex` 서브커맨드 추가.
  - `abyss reindex --bot <name>` — 해당 봇 모든 채팅 마크다운 → DB 재구축
  - `abyss reindex --group <name>` — 그룹 마크다운 → DB 재구축
  - `abyss reindex --all` — 모든 봇 + 그룹
  - 진행 상황은 Rich progress bar
- [ ] Step 5.2 — `abyss status` (`bot_manager.py:show_status` line 482)에 인덱스 메시지 수 표시 (옵션 — `--verbose`).
- [ ] Step 5.3 — `abyss init` (`onboarding.py`) env check에 `conversation_index.is_fts5_available()` 추가. 미지원 시 명확한 안내 + abort.

### Phase 6 — 문서화

- [ ] Step 6.1 — `docs/TECHNICAL-NOTES.md`에 "Conversation Search" 섹션 추가. 스키마, 인덱싱 트리거, 자동 주입 흐름, 재구축 절차.
- [ ] Step 6.2 — `docs/ARCHITECTURE.md` 모듈 의존 그래프에 `conversation_index.py`, `mcp_servers/conversation_search.py` 추가.
- [ ] Step 6.3 — `CLAUDE.md` Core Modules 표에 두 신규 모듈 행 추가.
- [ ] Step 6.4 — `README.md`에 "search past conversations" 항목 한 줄 추가.
- [ ] Step 6.5 — `docs/SECURITY.md`에 SQL injection 검토 결과 + 인덱스 파일 비밀 노출 위험 항목 추가.

### Phase 7 — 검증

- [ ] Step 7.1 — `make lint` 통과.
- [ ] Step 7.2 — `make test` 통과.
- [ ] Step 7.3 — 실제 봇으로 다음 사용자 흐름 수동 검증:
  1. 어제 봇과 임의 주제 대화 (예: "나는 토요일에 강남 카페 X에서 미팅"). 오늘 `/reset` 후 봇한테 "지난주 주말에 어디 미팅 갔다고 했지?" 물음 → Claude가 검색 도구로 회상.
  2. 그룹 미션 후 다음날 오케스트레이터한테 "어제 멤버 X한테 시킨 일 결과는?" → 회상.
  3. 봇 디렉터리 삭제 → 인덱스도 같이 삭제됨 확인.
  4. 마크다운만 백업/복구 → `abyss reindex` 실행 → 검색 정상 동작.

---

## 5. 테스트 계획

### 단위 테스트 (`tests/test_conversation_index.py`)

- [ ] 케이스 1: `ensure_schema()` 두 번 호출해도 에러 없음 (idempotent).
- [ ] 케이스 2: `append()` + `search()` 라운드트립 — 한국어 키워드.
- [ ] 케이스 3: `append()` + `search()` 라운드트립 — 영어 키워드.
- [ ] 케이스 4: `append()` + `search()` 라운드트립 — 이모지 포함 콘텐츠.
- [ ] 케이스 5: `search()` BM25 랭킹 — 더 자주 등장하는 메시지가 상위.
- [ ] 케이스 6: `search()` `since`/`until` 필터링.
- [ ] 케이스 7: `search()` `chat_id` 필터링 — 다른 채팅 메시지 미포함.
- [ ] 케이스 8: `search()` `limit` 적용.
- [ ] 케이스 9: `search()` 빈 결과 정상 반환 (예외 X).
- [ ] 케이스 10: `search()` 쿼리 문자열에 SQL 메타문자 (`'`, `;`, `--`) 포함 — SQL injection 방어 (parameterized query).
- [ ] 케이스 11: `reindex_from_markdown()` — 마크다운 N개 → 모든 메시지가 인덱스에 들어옴.
- [ ] 케이스 12: `reindex_from_markdown()` — 잘못된 헤더 형식 라인은 무시하고 진행 (graceful).
- [ ] 케이스 13: `is_fts5_available()` — 정상 환경에서 True.
- [ ] 케이스 14: `append()` 동시 호출 (asyncio.gather) — 데이터 손실 없음 (WAL 모드).
- [ ] 케이스 15: 매우 긴 콘텐츠 (10MB 단일 메시지) 핸들링 — 인덱싱 + 검색 동작.

### 단위 테스트 (`tests/test_conversation_search_mcp.py`)

- [ ] 케이스 1: MCP 서버가 stdio로 `tools/list` 응답 — `search_conversations` 도구 노출.
- [ ] 케이스 2: `search_conversations` 호출 → DB에서 결과 가져와 JSON으로 반환.
- [ ] 케이스 3: 환경변수 `ABYSS_CONVERSATION_DB` 미설정 시 명확한 에러.
- [ ] 케이스 4: DB 파일 없을 때 빈 결과 (예외 X).
- [ ] 케이스 5: 잘못된 파라미터 (`limit=-1`) 거부.
- [ ] 케이스 6: 결과 직렬화 — 한국어/이모지 escape 정상.

### 통합 테스트

- [ ] 시나리오 1 (`tests/test_session.py` 추가): `log_conversation()` 호출 후 `conversation_index.search()`로 즉시 조회 가능.
- [ ] 시나리오 2: 봇 시작 → 메시지 핸들러 통한 응답 → 인덱스에 user + assistant 둘 다 저장됨 (`test_handlers.py` 확장).
- [ ] 시나리오 3 (`tests/test_skill.py` 확장): `compose_claude_md()` 출력에 conversation_search SKILL.md 내용 포함 + `merge_mcp_configs()` 결과에 `${ABYSS_CONVERSATION_DB}`가 실제 경로로 치환됨.
- [ ] 시나리오 4: 그룹 메시지 라우팅 → `groups/<name>/conversation.db`에 인덱스됨.
- [ ] 시나리오 5: `abyss reindex --bot X` CLI → DB 비운 뒤 마크다운 모두 다시 인덱싱.
- [ ] 시나리오 6: `abyss reindex --all` — 봇 N개 + 그룹 M개 모두 처리.
- [ ] 시나리오 7: 백업/복구 흐름 — DB 파일 삭제 후 `reindex --all` → 검색 결과 동등.

### 평가 테스트 (`tests/evaluation/test_conversation_search_eval.py`, CI 제외)

- [ ] 시나리오 E1: 실제 Claude API 호출 — 사용자가 "지난주에 X 얘기한 거 기억해?" 같은 회상 질문 → Claude가 conversation_search 도구를 자율적으로 호출하는지 확인.
- [ ] 시나리오 E2: Claude가 결과를 사용자 응답에 자연스럽게 통합하는지.

---

## 6. 사이드 이펙트

### 기존 기능에 미치는 영향

| 항목 | 영향 | 대응 |
|---|---|---|
| `log_conversation()` 호출자 (handlers, cron, heartbeat) | INSERT 1ms 추가 | 측정 후 무시 가능 — 실제 동기 디스크 I/O는 마크다운 쓰기 비용에 비해 미미 |
| `compose_claude_md()` 호출자 | 시스템 프롬프트에 SKILL.md 한 섹션 추가 (~500 토큰) | 토큰 비용 미미. QMD 자동 주입과 동일 패턴 |
| `merge_mcp_configs()` 호출자 | conversation_search MCP 항목 추가 | 다른 MCP 스킬과 충돌 없음 (이름 겹침 방지) |
| 봇 시작 시간 | `ensure_schema()` ~10ms 추가 | 무시 가능 |
| 디스크 사용량 | 봇/그룹당 conversation.db 생성 | 메시지 1만 개당 ~10 MB. backup.py가 자동 포함 |
| 기존 마크다운 로그 | 변경 없음 | source of truth 유지 |
| QMD 자동 주입 | 영향 없음 | 별개 기능, 공존 |

### 하위 호환성

- 깨짐 없음. 신규 기능 추가만.
- `conversation.db` 파일 미존재 시 `ensure_schema()`가 생성. 기존 사용자가 업그레이드 후 첫 봇 시작에서 빈 인덱스 생성됨.
- 기존 사용자가 과거 대화도 검색하고 싶다면 `abyss reindex --all` 1회 실행으로 마이그레이션.

### 마이그레이션 필요 여부

- 강제 마이그레이션 없음. `abyss reindex --all`은 옵션.
- 자동 마이그레이션 트리거는 추가하지 않는다 (대용량 마크다운 파싱은 첫 봇 시작을 느리게 만들 수 있음). 사용자가 명시적으로 실행.

### 운영/배포

- `pyproject.toml` 의존성 변경 없음 → 빌드 변화 없음.
- 휠 크기 변화 없음 (Python stdlib만 사용).
- `abyss init`이 FTS5 미지원 환경 감지 시 abort → 일부 환경에서 신규 설치 실패할 수 있음. 한국 macOS / Ubuntu / WSL2의 표준 Python에서는 모두 OK.

---

## 7. 보안 검토

### OWASP Top 10 관련

| 항목 | 적용 여부 | 검토 |
|---|---|---|
| A01 Broken Access Control | N/A | 인덱스 파일은 봇 디렉터리 안. 사용자 접근 제어 변동 없음 |
| A02 Cryptographic Failures | 검토 필요 | 인덱스 파일이 평문 대화 보관 → 기존 마크다운과 동일 노출도. backup.py가 AES-256 zip으로 암호화. 추가 조치 불필요 |
| A03 Injection | **중요** | FTS5 MATCH 쿼리는 반드시 parameterized. `db.execute("... MATCH ?", (query,))` 패턴 강제. 단위 테스트 케이스 10이 회귀 방지 |
| A04 Insecure Design | N/A | 신규 trust boundary 없음 |
| A05 Security Misconfiguration | 검토 필요 | DB 파일 권한 = 봇 디렉터리 권한 상속 (`umask 077` 권장) |
| A06 Vulnerable Components | 낮음 | stdlib SQLite만 사용. 외부 의존성 0개 |
| A07 Authn Failures | N/A | 신규 인증 없음 |
| A08 Software/Data Integrity | 낮음 | DB 손상 시 마크다운에서 `reindex`로 완전 복구 가능 |
| A09 Logging Failures | N/A | 검색 로그는 일반 abyss logger 사용 |
| A10 SSRF | N/A | 외부 호출 없음 |

### 인증/인가 변경

- 변경 없음. MCP 서버는 abyss가 직접 띄운 자식 프로세스 (stdio) — 외부 접근 불가능.
- `ABYSS_CONVERSATION_DB` 환경변수는 abyss 프로세스 내에서만 노출 → 봇 자기 자신의 인덱스만 검색 (다른 봇 인덱스 접근 불가).

### 민감 데이터 처리

- 인덱스 파일에 평문 대화 저장 → **기존 마크다운 로그와 동일한 민감도**. 추가 노출 없음.
- backup.py의 AES-256 zip이 인덱스 파일도 보호.
- `~/.abyss/` 외부로 인덱스 파일 유출 경로 없음.

### PCI-DSS 영향

- 해당 없음. abyss는 카드 데이터를 다루지 않음.

### 추가 위협 모델링

- **위협**: 악성 사용자가 매우 긴 단일 메시지를 보내 인덱스 파일 디스크 고갈 시도.
  - **완화**: handlers.py에 이미 메시지 크기 제한 존재. 인덱싱 단계에서 별도 제한 추가 불필요.
- **위협**: 봇 토큰이 대화 내용에 우연히 포함 → 인덱스에 저장 → 백업 파일 유출 시 토큰 노출.
  - **완화**: 기존 마크다운 로그에 이미 동일 노출도. 신규 위험 아님.
- **위협**: SQL injection — `search_conversations` 도구가 받는 query 문자열.
  - **완화**: parameterized query 100% 강제. FTS5 MATCH 쿼리에서 사용자 query는 항상 `?` 바인딩.
- **위협**: 환경변수 인젝션 — `ABYSS_CONVERSATION_DB`를 외부에서 조작.
  - **완화**: 환경변수는 abyss가 MCP 서버 spawn 시 직접 설정. 외부 입력 경로 없음.

---

## 8. 완료 조건 체크리스트

- [ ] Phase 1~7 구현 단계 100% 완료
- [ ] 단위 테스트 케이스 1~15 + MCP 1~6 통과
- [ ] 통합 테스트 시나리오 1~7 통과
- [ ] `make lint` 통과
- [ ] `make test` 통과
- [ ] 평가 테스트 E1, E2 수동 확인 (CI 제외)
- [ ] 사이드이펙트 표 항목 모두 "해당 없음" 또는 "대응 완료"
- [ ] 보안 검토 항목 모두 "검토 완료" 또는 "대응 완료"
- [ ] `docs/TECHNICAL-NOTES.md`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `README.md`, `docs/SECURITY.md` 갱신
- [ ] 본 문서 status를 `done`으로 변경

## 9. 중단 기준

- FTS5가 abyss 표준 환경(macOS/Ubuntu에서 `uv` 설치 Python)에서 사용 불가능한 경우.
- 인덱싱 부하가 메시지 처리 응답 시간을 ≥ 100ms 추가하는 것이 측정되는 경우.
- 자동 주입된 SKILL.md가 다른 스킬과 충돌해 모델 혼동을 유발하는 경우 (평가 단계에서 발견 시).
- → 즉시 중단 후 plan을 업데이트하고 사용자 리뷰 요청.
