# Plan: Drop Telegram + Group surface entirely

- date: 2026-05-14
- status: done
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

`/mobile` PWA + abysscope 대시보드가 이미 채팅·세션·슬래시 커맨드·음성·푸시
알림을 모두 책임진다. Telegram 채널은 같은 출력을 두 번째로 만들 뿐이고,
유지 비용 (handlers ~1,159 LoC, 테스트 ~5,300 LoC, `python-telegram-bot`
의존, BotFather 안내 흐름)이 커서 단일 surface로 통합한다.

그룹 (orchestrator + member 협업) 기능도 Telegram chat ID에 박혀있고,
PWA 측 다중-봇 방 개념이 없으므로 **현재 그룹 코드는 통째로 제거**하고
나중에 PWA 위에서 새로 설계한다.

## 2. 예상 임팩트

### 영향받는 서비스 / 모듈

| 모듈 | 변화 |
|---|---|
| `handlers.py` | **전체 삭제** (~1,159 LoC) — Telegram adapter 전용 |
| `bot_manager.py` | **중수술** (~581 → ~200 LoC) — `Application.builder()`, polling 제거 |
| `onboarding.py` | **경수술** (~80 LoC 제거) — 토큰 검증 / BotFather 안내 |
| `utils.py` | **부분 제거** (~80 LoC) — `split_message`, `markdown_to_telegram_html`, `TELEGRAM_MESSAGE_LIMIT` |
| `cron.py` | **경수술** — `send_message_callback` 파라미터 제거 |
| `heartbeat.py` | **경수술** — 동일 |
| `cli.py` | **경수술** (~40 LoC) — `telegram_status` 컬럼, group subcommands |
| `commands.py` | **경수술** — `/bind`, `/unbind` 명령 제거 (그룹용) |
| `group.py` | **전체 삭제** — 추후 재설계 |
| `skill.py` | **경수술** — `compose_group_claude_md`, group context 주입 제거 |
| `session.py` | **경수술** — `group_session_directory`, `log_to_shared_conversation` 제거, `telegram_username` lookup 제거 |
| `chat_server.py` | **거의 무변경** — `telegram_botname` fallback만 `bot_name`으로 |
| `web_push.py`, `chat_core.py`, `sdk_client.py`, `llm/` | **무변경** |

### 사용자 경험

- Telegram 봇 더 이상 응답 안 함. `abyss bot add` 시 토큰 안 물어봄.
- `abyss start` 후엔 dashboard + chat_server만 뜸. `abyss status`도 Telegram 컬럼 사라짐.
- 그룹 채팅 (`/bind` 등) UI 흔적 제거. 기존 `group.yaml` 파일은 무시되거나 정리 안내.
- 모바일 PWA / 대시보드는 변화 없음.

### 성능 / 가용성

- `~/.abyss/bots/` 폴링 루프 (`Application.run_polling`) 사라짐 → 메모리 / CPU 약간 감소.
- 외부 의존 (`api.telegram.org`) 끊김 → 네트워크 단절 시 startup 실패 사라짐.

## 3. 구현 방법 비교

### 방법 A: 큰 PR 하나 (선택)

- 모든 변경을 단일 PR로 묶음.
- 장점: Telegram이 어디서 어떻게 엮여있었는지 한눈에 보임. revert 단순.
- 단점: 리뷰 부담. 테스트 한 번에 다 갈아엎어야 함.

### 방법 B: 단계별 PR 4-5개

1. handlers.py + 테스트 제거
2. bot_manager polling 제거 + 데몬 reshape
3. onboarding / cli 토큰 흐름 제거
4. utils 정리
5. group.py + commands 제거
6. python-telegram-bot 의존 제거

- 장점: 각 PR이 독립적 + 작음. 회귀 발견 시 좁은 범위.
- 단점: 중간 PR 머지된 시점에 `bot.yaml`의 `telegram_token`이 dead field로 남아있는 어색한 상태.

**선택: 방법 A** — 시멘틱적으로 "Telegram이 빠졌다"는 단일 사건. 부분 머지 상태에서 머지 트레인이 막히면 디버깅이 더 어려움. 단, 커밋은 논리 단위로 잘게 쪼개서 리뷰 용이성 확보.

## 4. 구현 단계

- [ ] **Step 1**: `handlers.py` 통째로 삭제. 관련 import 제거.
- [ ] **Step 2**: `bot_manager.py` 재작성. `Application.*` 호출 제거. 폴링 루프 제거. `chat_server` + cron + heartbeat scheduler만 띄움. send_message_callback 주입 제거.
- [ ] **Step 3**: `cron.py` / `heartbeat.py`에서 `send_message_callback` 파라미터 제거. `markdown_to_telegram_html` / `split_message` / `parse_mode="HTML"` 분기 제거. `allowed_users` 송신 루프 제거 (web_push로 단일화).
- [ ] **Step 4**: `onboarding.py`에서 `validate_telegram_token`, `prompt_telegram_token` 제거. `abyss bot add` 흐름은 display_name + personality + role + goal만 묻도록 단순화.
- [ ] **Step 5**: `utils.py`에서 `markdown_to_telegram_html`, `split_message`, `TELEGRAM_MESSAGE_LIMIT` 제거. 사용처 없음 확인.
- [ ] **Step 6**: `group.py` 통째로 삭제. `compose_group_claude_md`, `log_to_shared_conversation`, `find_group_by_chat_id`, `group_session_directory` 등 모든 export 제거. `commands.py`에서 `cmd_bind`/`cmd_unbind` 삭제, `COMMAND_CATALOG`에서도 제거.
- [ ] **Step 7**: `skill.py` / `session.py`에서 group 관련 함수 호출 제거. `telegram_username` 참조 모두 제거.
- [ ] **Step 8**: `cli.py`에서 group subcommands 트리 제거 (`abyss group`). `abyss status` 테이블에서 Telegram 컬럼 제거. 태그라인을 "Personal AI assistant via PWA + Claude Code"로 변경.
- [ ] **Step 9**: `chat_server.py`에서 `telegram_botname` fallback을 `bot_name`으로 (`display_name or bot_name`).
- [ ] **Step 10**: `pyproject.toml`에서 `python-telegram-bot>=22.6` 제거. `uv lock` 갱신.
- [ ] **Step 11**: 9개 Telegram-coupled 테스트 파일 검토 — 대부분 삭제, group 테스트는 통째로 삭제, onboarding / utils / heartbeat 테스트는 Telegram mock 제거 후 잔존 케이스만 유지.
- [ ] **Step 12**: 문서 갱신 — `README.md`, `docs/ARCHITECTURE.md`, `docs/TECHNICAL-NOTES.md`, `CLAUDE.md` 4종에서 Telegram 멘션 정리.

## 5. 테스트 계획

### 단위 테스트
- [ ] `test_bot_manager.py` 신규 — chat_server + scheduler 기동 / 종료 검증
- [ ] `test_cron.py` 갱신 — send_message_callback 없는 시그니처 검증, web_push만 호출되는지
- [ ] `test_heartbeat.py` 갱신 — 동일
- [ ] `test_onboarding.py` 갱신 — `prompt_telegram_token` 호출 없는지 + display_name only flow
- [ ] `test_commands.py` 유지 — `/bind` 케이스 삭제
- [ ] `test_chat_server.py` 유지 — 변경 거의 없음

### 통합 테스트
- [ ] `abyss start` → polling 시도 없이 정상 기동, `abyss status` 출력에 Telegram 컬럼 없음
- [ ] `abyss bot add` → 토큰 안 묻고 끝
- [ ] 기존 `bot.yaml`에 `telegram_token` 남아있어도 정상 동작 (silently ignored)
- [ ] PWA에서 채팅 / 슬래시 / 음성 / 라우틴 전부 정상

### 엣지 케이스
- [ ] `python-telegram-bot` import 누락 시 친절한 에러 — pyproject 제거 후 stale env에서도 진단 가능
- [ ] 기존 `~/.abyss/groups/` 디렉토리 존재 시 `abyss start`가 무시하고 진행

## 6. 사이드 이펙트

- **기존 사용자**: Telegram 봇 응답 끊김. 대시보드 / PWA로 옮기지 않은 사용자가 있다면 명시 안내 필요 (release notes에 강조).
- **그룹 사용 중인 봇**: 협업 중단. `groups/*` 디렉토리 그대로 두지만 코드가 무시. 추후 재설계 시 데이터는 살릴 수 있음.
- **하위 호환**: `bot.yaml`의 `telegram_*` 필드는 dead field로 남음. 향후 cleanup PR에서 제거.
- **버전 bump**: 계산기 버전 `2026.05.14` 새 릴리즈. 큰 변화 → release notes에 명시.

## 7. 보안 검토

- **OWASP Top 10**: 해당 없음. 외부 API 의존 줄어들 뿐.
- **인증/인가**: `allowed_users` (Telegram chat ID 기반 권한) 제거. PWA / 대시보드의 인증은 origin 제어 + Tailscale 네트워크 격리에 의존 → 동일.
- **민감 데이터**: `telegram_token`이 `bot.yaml`에 저장됐었음. 코드에선 더 이상 사용 안 하지만, 사용자가 직접 파일에서 제거하도록 release notes 안내. (스크립트로 자동 제거 안 함 — 사용자 데이터 임의 수정 X)
- **PCI-DSS**: 무관.

## 8. Plan 이탈 방지

본 plan에 명시되지 않은 파일 수정 금지. 발견 시 plan 먼저 업데이트하고 승인 요청.

## 9. 완료 조건

- 구현 단계 체크리스트 100% 완료
- `uv run pytest` 통과 (Telegram mock 테스트는 모두 제거됨)
- `make lint` / `next lint` / `vitest run` 통과
- `abyss start` → `abyss status` → `abyss stop` 사이클 정상
- PWA 동작 회귀 없음
- 사이드 이펙트 항목 각각 "해당 없음" 또는 "대응 완료" 명시
- `status: done` 기재

## 10. 중단 기준

- Telegram 제거 후 PWA 단독으로 cron 결과 도달 못 하는 경우 (web_push HTTPS 의존)
  → 대안 마련 (e.g. dashboard chat 내 라우틴 알림 카운터) 후 재개
- `bot_manager` 재구성 후 chat_server / cron / heartbeat 중 하나라도 lifecycle 깨지면 즉시 중단
- 그룹 데이터 보존 요청이 새로 나오면 plan 수정 (현재는 `groups/*` 폴더 무시 정책)
