# Plan: `abyss dashboard` 서브커맨드 폐기 + `start/restart/stop` 단일 진입점

- date: 2026-05-15
- status: done
- author: claude
- approved-by: ash84 (2026-05-15)
- decisions:
  - `--daemon` 플래그: **즉시 제거**, alias 없음
  - `abyss dashboard` 서브커맨드: **즉시 제거**, deprecation alias 없음
  - 두 서버 통합 (단일 서버화): **이번 PR 범위 밖**. 별도 plan 으로 분리

## 1. 목적 및 배경

현재 abyss 의 lifecycle 은 **두 개의 명령어 트리** 로 쪼개져 있다:

- `abyss start [--daemon]` → bot 매니저 (cron / heartbeat / chat_server) 부팅
- `abyss dashboard start [--daemon] [--port]` → Next.js 프론트 빌드 + 서빙

두 개를 따로 켜고 따로 끄는 운영 모델은 **로컬 1인 사용자 도구** 에는 과잉이다. PWA / 대시보드는 사실상 default UI 인데, "시작" 명령이 두 개로 갈라져 있어:

- 신규 사용자가 `abyss start` 후 대시보드가 안 떠 헤맴
- `abyss dashboard start --daemon` 와 `abyss start --daemon` 의 PID 충돌 / 순서 의존
- foreground 모드의 UX 가 일관되지 않음 (bot 매니저는 console output stream, 대시보드는 raw `next start` output)

목표: **`abyss start` 하나로 API 서버 + 대시보드까지 다 부팅**, **default daemon**, 진행 상황은 `BuildProgress` 체크리스트로 일관되게 표시.

## 2. 예상 임팩트

**영향받는 모듈:**
- `src/abyss/cli.py`: `dashboard_app` 서브 typer 트리 전체 제거 (4개 명령). 최상위 `start/restart/stop` 시그니처 변경
- `src/abyss/bot_manager.py`: `_run_bots` 가 chat_server 외에 abysscope 빌드/서빙도 lifecycle 안에 포함. 또는 `start_bots` 가 abysscope 부팅을 먼저 트리거하고 bot 매니저 부팅
- `src/abyss/dashboard_ui.py`: 그대로 재사용 (이미 BuildProgress 가 있다). 다만 `BuildStep` 항목을 "Locate dashboard / Install deps / Build / Start server" → "Locate dashboard / Install deps / Build / Start API + dashboard" 로 통합
- `_pid_file()` / `_dashboard_pid_file()` 둘 다 유지 (각 프로세스의 PID 추적). 단 stop 은 한 번에 둘 다 정리
- `tests/test_cli.py` / `tests/test_bot_manager.py`: 명령 트리 변경에 따른 호출 시그니처 수정

**문서:**
- `README.md`, `CLAUDE.md`, `docs/MOBILE_ACCESS.md`, `docs/landing/index.html` — `abyss dashboard start` 언급 제거 + `abyss start` 로 통일

**호환성:**
- 외부 사용자가 `abyss dashboard start` 로 자동화한 launchd / cron 이 있다면 깨진다. 릴리즈 노트 + deprecation 안내 필요
- `--daemon` 플래그 제거 → 기본 daemon. **foreground 모드** 가 필요하면 `--foreground` 옵션을 둔다 (디버깅용)
- `--port` 옵션 → top-level `abyss start --port` 로 이전 (대시보드 포트만 의미)

**프로세스 모델:**
- 현재: bot manager (foreground asyncio loop) + abysscope (별도 Next.js subprocess)
- 변경: bot manager 가 abysscope 를 **자식 프로세스로 spawn**. bot manager 가 죽으면 abysscope 도 정리. 단일 supervisor.

## 3. 구현 방법 비교

### 방법 A: bot_manager 가 abysscope 를 자식 subprocess 로 관리 (선택)

- `bot_manager.py` 에 `_start_abysscope()` / `_stop_abysscope()` 추가
- `_run_bots()` 의 chat_server 부팅 직후 abysscope 빌드 + 서빙 시작
- shutdown 시 chat_server + abysscope 둘 다 정리
- PID 파일은 abysscope.pid 그대로 유지 (외부 도구가 추적 가능)
- `cli.py` 의 dashboard_app 전체 삭제

**장점:**
- 진입점 1개 (`abyss start`). 멘탈 모델 깔끔
- shutdown 순서 보장 (chat_server 가 살아있는 동안만 dashboard 가 의미 있음 → chat_server 가 죽으면 dashboard 도 죽어야)
- BuildProgress 가 전체 부팅을 한 화면에서 표현
- 기존 dashboard_ui 재사용

**단점:**
- bot_manager.py 가 굵어진다 (Next.js 빌드 / 노드 환경 / 포트 처리까지 다 떠안음)
- abysscope 만 재시작이 필요한 시나리오 (프론트 수정 후 hot reload) 에는 `abyss restart` 가 무거움 — 단, 현재 사용자 시나리오에서 이건 거의 안 쓰임

### 방법 B: 두 개의 launchd 프로세스 유지, 단일 CLI 만 노출

- `abyss start` 가 내부적으로 두 개의 launchd job 을 등록 (bot 매니저 + abysscope)
- `abyss stop` 도 두 개 정리
- subprocess spawn 대신 launchd 가 supervise

**장점:**
- macOS 표준 lifecycle (launchd 가 죽은 프로세스 재시작)
- bot_manager.py 가 빌드 책임을 안 떠안음

**단점:**
- 빌드 (npm install / next build) 가 launchd 안에서 도는 게 어색함 — 빌드는 시작 시점 1회, 재시작에서는 캐시 활용이 필요한데 launchd 는 단순 supervisor
- 두 개의 plist 관리 + 디버깅 surface 증가
- BuildProgress 가 두 번 도는 (또는 어느 한쪽이 안 보임) 문제

### 선택: **방법 A**

bot_manager 가 단일 supervisor 로 모든 in-process / out-of-process 컴포넌트를 관리. abysscope 도 launchd 위에서 따로 도는 것보다 bot_manager 자식으로 두는 게 lifecycle 보장 + UX 일관성에서 유리.

### Foreground 옵션

- `abyss start` (기본) → daemon (launchd plist 등록 + 백그라운드)
- `abyss start --foreground` → asyncio loop 가 현재 터미널을 점유, Ctrl+C 로 stop. 디버깅용으로 명시적 플래그
- `--port` → 대시보드 포트만 의미. default `3847`

## 4. 구현 단계

- [ ] **Step 1**: `bot_manager._start_abysscope_subprocess(port)` / `_stop_abysscope_subprocess()` 추가 — abysscope 디렉토리 탐색 + `npm install` (캐시 체크) + `next build` + `next start` 자식 프로세스로
- [ ] **Step 2**: `_run_bots` 안에 abysscope 빌드/서빙을 chat_server 부팅 옆에 통합. BuildProgress 체크리스트로 표시
- [ ] **Step 3**: shutdown 흐름에 abysscope subprocess 정리 추가 (SIGTERM → wait → SIGKILL)
- [ ] **Step 4**: `cli.py` 의 `start`, `restart` 시그니처 변경 — `daemon=True` default, `--foreground` 옵션 추가, `--port` 옵션 추가
- [ ] **Step 5**: `cli.py` 의 `dashboard_app` typer 트리 + `_dashboard_pid_file` 외 보조 함수들 모두 삭제 (bot_manager 로 이전된 로직 외)
- [ ] **Step 6**: `bot_manager.stop_bots()` 에 abysscope.pid 정리 추가 (이미 `_show_dashboard_status` 가 있으니 stop 도 미러)
- [ ] **Step 7**: `bot_manager.show_status()` 가 통합된 상태를 출력 — abyss + dashboard 한 화면
- [ ] **Step 8**: `_start_daemon` (launchd plist) 갱신 — daemon 진입 시 abysscope 도 같이 떠야
- [ ] **Step 9**: `tests/test_cli.py` / `tests/test_bot_manager.py` — `dashboard_*` 테스트 제거, 새 시그니처에 맞춰 업데이트
- [ ] **Step 10**: 문서 — `README.md`, `CLAUDE.md`, `docs/MOBILE_ACCESS.md`, `docs/landing/index.html` 의 `abyss dashboard *` 언급 제거
- [ ] **Step 11**: `make lint && make test` 통과
- [ ] **Step 12**: 실제 `abyss start` / `abyss restart` / `abyss stop` 수동 검증 (`~/.abyss/` 환경에서)

## 5. 테스트 계획

**단위 테스트:**
- [ ] 케이스 1: `bot_manager._start_abysscope_subprocess` 가 abysscope 디렉토리 없으면 명확한 에러
- [ ] 케이스 2: `node_modules` 가 이미 있으면 `npm install` 스킵
- [ ] 케이스 3: stop 시 abysscope.pid 가 정리됨
- [ ] 케이스 4: `abyss start --foreground` 가 foreground 모드로 진입 (launchd plist 안 만듦)
- [ ] 케이스 5: `abyss dashboard start` 가 typer 에서 더 이상 인식 안 됨 (404 / "no such command")

**통합 테스트:**
- [ ] 시나리오 1: 깨끗한 환경에서 `abyss start` → BuildProgress 체크리스트 → abyss.pid + abysscope.pid 둘 다 생성 → 3847 포트 응답 → http://localhost:3847 접근 가능
- [ ] 시나리오 2: `abyss restart` → 두 PID 모두 갱신 → 새 포트에서 응답
- [ ] 시나리오 3: `abyss stop` → 두 PID 정리 + 두 프로세스 종료 + 포트 free
- [ ] 시나리오 4: `abyss start --foreground` → Ctrl+C 로 깨끗하게 종료, abysscope 도 같이 종료
- [ ] 시나리오 5: `abyss status` → bot + dashboard 통합 상태 표시
- [ ] 시나리오 6: launchd daemon 모드에서 abysscope 가 죽으면 bot_manager 가 재시작 또는 명확한 로그

## 6. 사이드 이펙트

- **하위 호환성 깨짐**: `abyss dashboard start/stop/restart/status` 사용자 자동화 깨짐. 릴리즈 노트에 명시
- **`--daemon` 플래그 제거**: 기존 `abyss start --daemon` 호출은 typer 가 unknown flag 로 거부. `--foreground` 가 명시적 대체. 릴리즈 노트 안내 + `--daemon` 을 deprecation alias 로 1릴리즈 유지 고려 (간단하면 그렇게)
- **빌드 시간**: `abyss start` 가 처음에는 `npm install + next build` 로 인해 느려짐. 첫 실행 후 캐시. BuildProgress 가 진행 상황을 보여줘서 hang 처럼 보이지 않게
- **chat_server 의 위치**: chat_server 는 abysscope 의 백엔드. abysscope 가 chat_server 를 호출하므로 chat_server 가 먼저 떠야 한다. 부팅 순서: chat_server → abysscope build → abysscope start

## 7. 보안 검토

- **OWASP A05 (Security Misconfiguration)**: abysscope 가 자동으로 떠서 외부 트래픽 노출 가능. 단 default bind `127.0.0.1` + Tailscale 셋업이 가이드된 외부 접근. `ABYSS_DASHBOARD_HOST=0.0.0.0` 설정은 명시적이라 사용자 책임 보존
- **포트 충돌**: 같은 포트로 두 번 시작 시 두 번째가 명확히 실패해야. 이미 `_is_port_in_use` 가 있으므로 재사용
- **subprocess 권한**: bot_manager 가 npm + next 를 spawn → PATH / 노드 모듈 위치는 cli.py 의 기존 `_run_to_log` 패턴 재사용
- **PCI-DSS / 민감 데이터**: 해당 없음

## 8. 작업 순서

1. **이 plan 승인** → `approved-by` 기재
2. 브랜치 `chore/merge-dashboard-cli` 생성
3. Step 1-3 (bot_manager) → Step 4-8 (cli + lifecycle) → Step 9 (테스트) → Step 10 (문서)
4. 수동 검증 (Step 12) — 깨끗한 환경에서 부팅 / 재시작 / 정지
5. PR → CI → 머지
6. 릴리즈 (버전 bump + 노트 + 트윗 초안 + landing page 업데이트)

## 9. 완료 조건

- [ ] Step 1-12 체크리스트 100%
- [ ] `abyss dashboard` 명령이 typer 에서 사라짐 (`abyss --help` 출력에서 확인)
- [ ] `abyss start` 한 번으로 bot + 대시보드 모두 부팅 + BuildProgress 보임
- [ ] `make lint && make test` 통과
- [ ] 본 plan `status: done`

## 10. 중단 기준

- abysscope subprocess 의 lifecycle 이 bot_manager asyncio loop 와 충돌 (signal handling, 좀비 프로세스 등) → 즉시 중단, 방법 B (launchd 두 개) 로 재검토
- BuildProgress UI 가 백그라운드 daemon 모드에서 의미 없음 — daemon 모드에서는 첫 빌드만 진행하고 그 후 detach 하는 식의 분리가 필요 → plan 갱신 후 재승인
- `--port` 옵션 의미가 bot 매니저 / 대시보드 / chat_server 셋 다에 충돌하면 → 별도 옵션 분리, plan 갱신
