# Plan: 텔레그램 하드 컷 + PWA Web Push로 모바일 전환

- date: 2026-05-14
- status: done
- author: claude
- approved-by: ash84
- branch: feat/drop-telegram-pwa-push
- completed: 2026-05-14

## 1. 목적 및 배경

abyss는 텔레그램을 메인 모바일 UI로, abysscope 대시보드를 데스크탑 UI로 써왔다. 직전 plan (`plan-pwa-mobile-chat-2026-05-13.md`)에서 `/mobile` 라우트를 추가해 모바일 대시보드가 텔레그램과 비슷한 UX를 갖췄다.

**이제 텔레그램을 완전히 제거하고, 푸시 알림을 PWA Web Push로 대체한다.** 그룹 협업(orchestrator-member)은 후순위로 동결.

### 텔레그램 의존 폐기 이유

- ChatGPT/Claude 앱 모델 채택: 백엔드 1개 (abysscope `chat_server`) + 다중 클라이언트 (데스크탑 웹 + 모바일 PWA)
- 텔레그램 API 제약 (마크다운 테이블 불가, 메시지 길이 4096자, 스트리밍 워크어라운드)에서 해방
- 코드베이스 단순화: `handlers.py` (~1080 LOC), `python-telegram-bot` 의존성, BotFather 설정 부담 제거
- 멀티 디바이스 sync가 백엔드 단일 소스로 자연스럽게 됨

### 사용자 요구사항 (이 plan)

- 푸시: **PWA Web Push** (Flutter 네이티브 안 함)
- 마이그레이션: **하드 컷** (deprecation phase 없음)
- 그룹 협업: **동결** (코드는 남기되 텔레그램 의존 라우팅은 제거; 후속 plan에서 대시보드 UI 새로)
- 인증: **Tailscale only** (Supabase Auth 도입 안 함)

## 2. 예상 임팩트

### 제거되는 것

| 영역 | 변경 |
|---|---|
| `src/abyss/handlers.py` | 전체 삭제 (~1080 LOC) |
| `python-telegram-bot` | `pyproject.toml`에서 제거 |
| `cli.py` 텔레그램 서브커맨드 | `abyss bot add` 등 위저드의 토큰 프롬프트 제거 |
| `bot_manager.py` | 텔레그램 Application/polling 라이프사이클 제거. 크론 + 헬트빝 + chat_server 스케줄러만 유지 |
| `bot.yaml` 필드 | `telegram_token`, `telegram_username`, `allowed_users` (Telegram user_id) — 로딩 시 ignored |
| `onboarding.py` | 텔레그램 토큰 onboarding 프롬프트 제거 |
| `set_bot_commands` (BotCommand 등록) | 호출 지점 제거 |
| `/bind`, `/unbind` 슬래시 커맨드 | Telegram chat_id 종속이라 제거 (commands.py에서 삭제) |
| `tests/test_handlers.py` | 삭제 |
| `tests/test_handlers_group.py` | 삭제 또는 그룹 라우팅 단위 테스트만 남김 |

### 새로 추가되는 것

| 영역 | 내용 |
|---|---|
| `src/abyss/web_push.py` (신규) | VAPID 키 관리, 구독 저장, 발송 헬퍼 |
| `chat_server.py` 새 라우트 | `POST /chat/push/subscribe`, `GET /chat/push/vapid-key`, `POST /chat/push/visibility` |
| `abysscope/public/sw.js` | Service Worker (push 이벤트, notificationclick) |
| `abysscope/src/app/manifest.ts` | 동적 manifest 라우트 |
| `abysscope/src/hooks/use-web-push.ts` | 구독 관리 클라이언트 훅 |
| `abysscope/src/app/api/push/*` | 프록시 라우트들 |
| `cron.py` / `heartbeat.py` | `send_message_callback` 대신 `notify_user(bot, text)` 사용 — 내부적으로 Web Push 발송 |
| `chat_server.py` | 봇 응답 완료 시점에 푸시 트리거 (`process_chat_message` 후) |
| `abyss start` | 텔레그램 폴링 없음. 크론 + 헬트빝 + chat_server + dashboard만 |

### 영향받는 사용자 경험

| 시나리오 | 변경 후 |
|---|---|
| 메시지 전송 | 모바일/데스크탑 PWA에서 abysscope `/chat` 또는 `/mobile/chat/...` 사용. 텔레그램 앱 사용 안 함 |
| 봇 응답 알림 | PWA Web Push (홈 화면에 PWA 설치 + 알림 권한 필요) |
| 헬트빝 알림 | 동일하게 Web Push. 활성 시간 외에는 발송 안 함 (기존 로직 유지) |
| 크론 결과 | 동일하게 Web Push |
| 파일 업/다운 | abysscope 자체 CDN으로 모두 처리 (이미 동작 중) |
| 그룹 협업 | **사용 불가** (후속 plan에서 대시보드 UI 신규 작성) |
| `/cron run` | 대시보드에서 동작 (`send_message_callback` 새 구현으로 Web Push 또는 메시지로) |
| `/heartbeat run` | 동일 |
| `/bind` / `/unbind` | **제거** |

### 성능/가용성

- 텔레그램 폴링 (`getUpdates` 1초 간격)이 사라져 CPU/네트워크 부담 감소
- Web Push 발송은 봇 응답당 1회 HTTP 호출. 무시할 수준
- VAPID 키 첫 생성 시 ~100ms 비용 (자동, 캐시됨)

### 마이그레이션

- 기존 사용자 `~/.abyss/bots/<name>/bot.yaml` 파일은 그대로 유지. `telegram_token` 필드는 로딩 시 무시.
- 새 `abyss bot add`는 텔레그램 토큰 요구 안 함
- 첫 푸시 받으려면 사용자가 PWA 설치 + 알림 권한 허용 + 알림 토글 ON

## 3. 구현 방법 비교

### 방법 A: 한 PR에 모두 (하드 컷 + PWA 동시)

- 장점: 마이그레이션 한 번. 양쪽 코드 공존 기간 없음
- 단점: PR 거대 (~3000+ LOC 변경). 머지 후 만약 텔레그램 누락된 의존 발견 시 롤백 비용 큼

### 방법 B: 두 PR로 분리

**PR-B1**: PWA Web Push 추가. 텔레그램과 공존.
- `web_push.py`, 서브스크립션 라우트, Service Worker, manifest, 구독 UI
- 봇 응답 / heartbeat / cron 결과를 *둘 다*에 발송 (Web Push + Telegram)
- 안정화 확인

**PR-B2**: 텔레그램 제거.
- handlers.py 삭제, polling 라이프사이클 제거, 의존성 정리
- send_message_callback 경로 단일화 (Web Push만)

- 장점: 각 PR 독립 검증. PR-B1 동작 확인 후 PR-B2 진행
- 단점: 중간 상태 유지 코드 (양쪽 발송)

### 방법 C: 백엔드 먼저 → 프론트엔드 → 텔레그램 제거

세 PR. 더 잘게 쪼개기. 일정 길어짐.

### 선택: **방법 B (두 PR)**

이유:
1. 사용자가 *하드 컷*을 원했지만 PWA 푸시는 *iOS Safari 실기 검증*이 필요한 영역. PR-B1 머지 후 며칠 폰에서 써본 뒤 PR-B2 진행이 안전
2. PR 단위가 적정 (각 1500 LOC 내외)
3. 양쪽 발송 기간은 짧게 (1주 이내). 이중 알림 노이즈는 *환영 신호* — 푸시 실패 시 텔레그램 fallback

본 plan 문서는 **PR-B1 (PWA Web Push 추가)** 범위. PR-B2 (텔레그램 제거)는 별도 plan으로 분리.

## 4. 구현 단계 (PR-B1)

### Phase 1: 백엔드 — Web Push 인프라 (3일)

- [ ] `src/abyss/web_push.py` 신규
  - [ ] `VAPID_FILE = ~/.abyss/vapid-keys.json` — 자동 생성 + 캐시
  - [ ] `SUBSCRIPTIONS_FILE = ~/.abyss/push-subscriptions.json` — 파일 락 보호
  - [ ] `add_subscription(sub)`, `remove_subscription(endpoint)`, `list_subscriptions()`
  - [ ] `mark_device_visible(device_id)`, `mark_device_hidden(device_id)` — 활성 디바이스 추적 (60s TTL, in-memory)
  - [ ] `send_push(bot_name, title, body, *, claude_session_id=None, tab_id=None, workspace=None)` — 모든 구독에 발송, 가시 디바이스는 스킵
- [ ] 의존성 추가: `pywebpush` (Python web push)
- [ ] 단위 테스트: `tests/test_web_push.py`
  - [ ] VAPID 키 자동 생성
  - [ ] 구독 add/remove
  - [ ] 가시 디바이스 스킵
  - [ ] 발송 실패 (Gone / Not Registered 410/404) 시 자동 제거

### Phase 2: 백엔드 — 라우트 + 트리거 통합 (2일)

- [ ] `chat_server.py` 새 라우트 등록
  - [ ] `GET /chat/push/vapid-key` → `{"publicKey": str}`
  - [ ] `POST /chat/push/subscribe` body `{endpoint, keys, expirationTime?}`
  - [ ] `DELETE /chat/push/subscribe` body `{endpoint}`
  - [ ] `POST /chat/push/visibility` body `{deviceId, visible: bool}`
- [ ] `process_chat_message` 응답 완료 시점에 `send_push(bot_name, title="<bot> replied", body=preview)` 호출
  - [ ] 가시 디바이스 (대시보드 열려 있음) 스킵 — 중복 방지
- [ ] `cron.py` `execute_cron_job` 결과를 send_message_callback이 아닌 `notify_user` (Web Push)로 전송
- [ ] `heartbeat.py` `execute_heartbeat` 동일
- [ ] 양쪽 발송 모드 유지 (텔레그램 콜백 + Web Push). PR-B2 전까지 공존
- [ ] 통합 테스트: `tests/test_chat_server.py`에 push 시나리오 추가

### Phase 3: 프론트엔드 — Service Worker + manifest (2일)

- [ ] `abysscope/public/sw.js` 신규 (~50 LOC, purplemux 패턴)
  - [ ] `install` / `activate` 핸들러
  - [ ] `push` 이벤트 → `self.registration.showNotification(...)`
  - [ ] `notificationclick` → URL 열기 (해당 채팅으로 이동)
  - [ ] `clear-notifications` 메시지 핸들러
- [ ] `abysscope/src/app/manifest.ts` 신규
  - [ ] 동적 라우트, 호스트 기반 `start_url`
  - [ ] 아이콘 (기존 favicon 활용 + 추가 사이즈)
  - [ ] `display: standalone`, `theme_color: #131313`, `background_color: #131313`
- [ ] `abysscope/src/app/layout.tsx` 메타 추가
  - [ ] `<link rel="manifest" href="/manifest" />`
  - [ ] Apple touch icon
  - [ ] iOS splash 이미지 (선택, 첫 버전엔 생략 가능)
  - [ ] `apple-mobile-web-app-capable: yes`

### Phase 4: 프론트엔드 — 구독 훅 + 설정 UI (2일)

- [ ] `abysscope/src/hooks/use-web-push.ts` 신규
  - [ ] VAPID 키 가져오기
  - [ ] `Notification.requestPermission`
  - [ ] `serviceWorker.register('/sw.js')`
  - [ ] `pushManager.subscribe`
  - [ ] 구독 정보를 백엔드로 전송
  - [ ] `notificationclick` 메시지 수신 → 라우터 푸시
  - [ ] 가시성 추적 (focus/blur, 30s 핑)
- [ ] `abysscope/src/app/api/push/*` 프록시 라우트들
  - [ ] `vapid-key/route.ts` (GET)
  - [ ] `subscribe/route.ts` (POST/DELETE)
  - [ ] `visibility/route.ts` (POST)
- [ ] `abysscope/src/app/settings/page.tsx` 또는 `/mobile/sessions` 헤더에 *알림 토글*
  - [ ] OFF/ON 상태 표시
  - [ ] ON 시 권한 요청 + 구독
  - [ ] OFF 시 구독 해제
- [ ] iOS 안내 카드 (Safari 16.4+ 필요, 홈 화면 추가 필수)

### Phase 5: Tailscale HTTPS 가이드 + 문서 (1일)

- [ ] `docs/MOBILE_ACCESS.md` 업데이트
  - [ ] `tailscale serve https / http://localhost:3847` 가이드
  - [ ] PWA 설치 단계 (iOS Safari + Android Chrome)
  - [ ] 알림 토글 사용법
- [ ] README의 모바일 섹션 보완

### Phase 6: 테스트 + 실기 검증 (1.5일)

- [ ] Python 회귀: `make lint && make test`
- [ ] abysscope vitest 회귀
- [ ] iOS Safari 16.4+ 실기:
  - [ ] PWA 설치 가능
  - [ ] 알림 권한 허용 → 구독 등록
  - [ ] 봇 응답 → 푸시 도착 (대시보드 닫혀 있을 때)
  - [ ] 대시보드 열려 있으면 푸시 안 옴
  - [ ] notificationclick → 해당 채팅으로 이동
- [ ] Android Chrome 실기 (동일 시나리오)
- [ ] 크론 실행 → 푸시 도착
- [ ] heartbeat 실행 → 푸시 도착

총 작업량: **약 11.5일** (~2.5주, 단일 개발자 기준)

## 5. 테스트 계획

### 단위 테스트

- [ ] `tests/test_web_push.py`
  - [ ] VAPID 키 첫 생성, 캐시 hit
  - [ ] 구독 add (멱등), remove, list
  - [ ] 가시 디바이스 스킵
  - [ ] 410 / 404 응답 시 자동 구독 제거
  - [ ] 동시 쓰기 락
- [ ] `tests/test_chat_server.py`
  - [ ] `/chat/push/vapid-key` 200 + publicKey 형식
  - [ ] `/chat/push/subscribe` POST/DELETE
  - [ ] `/chat/push/visibility` POST
  - [ ] 봇 응답 완료 후 send_push 호출 (mock)
  - [ ] 가시 디바이스에는 발송 안 됨

### 통합 테스트

- [ ] 시나리오 1: PWA 설치 + 구독 + 첫 푸시
  - 모바일에서 abysscope 접속 → 홈 화면 추가 → PWA 열기 → 설정에서 알림 ON → 권한 허용 → 새 채팅 메시지 → 푸시 도착
- [ ] 시나리오 2: 크론 푸시
  - `/cron add 1분 후 ping 보내줘` → 1분 대기 → 푸시 도착
- [ ] 시나리오 3: 가시 디바이스 중복 방지
  - 폰 PWA 열어둔 상태에서 다른 디바이스로 메시지 → 폰엔 푸시 안 옴
- [ ] 시나리오 4: 텔레그램 동시 동작 (B1 단계)
  - 텔레그램에 메시지 → 텔레그램 응답 + 폰 PWA 푸시 둘 다 도착
- [ ] 시나리오 5: 알림 클릭 → 채팅 이동
  - 푸시 알림 탭 → PWA 열림 → 해당 세션으로 자동 이동
- [ ] 시나리오 6: 구독 만료 자동 정리
  - PWA 삭제 후 다시 메시지 → 410 응답 → 백엔드 구독 자동 제거 (다음 발송에 영향 없음)

## 6. 사이드 이펙트

- **텔레그램 fallback 유지 (B1)**: 푸시 실패해도 텔레그램으로 보이므로 회귀 위험 낮음
- **HTTPS 요구사항**: iOS Safari PWA = HTTPS 강제. Tailscale `serve` 또는 reverse proxy 필요. 문서화 필수
- **알림 권한 거절 시**: 사용자가 "차단" 클릭하면 OS 설정에서 재허용해야 함. iOS 푸시 도달률 ~80%
- **VAPID 키 백업**: `~/.abyss/vapid-keys.json` 분실 시 모든 기존 구독 무효화. 백업 가이드 필요
- **여러 디바이스 구독**: 동일 사용자가 폰 + 태블릿 + 데스크탑 모두 구독 가능. 모두에 발송 (가시 스킵 후). 의도된 동작
- **하위 호환성**: 기존 텔레그램 봇 동작 변하지 않음. push 발송은 추가 기능

## 7. 보안 검토

| OWASP 항목 | 해당 여부 | 대응 |
|---|---|---|
| A01 Broken Access Control | 해당 — push 구독 API에 인증 없음 | Tailscale 가정. 단, `endpoint`는 사용자별 push 서비스 URL이라 추측 어려움. 다른 사용자가 무작위로 구독 추가/삭제할 위험 낮음 |
| A02 Cryptographic Failures | 해당 — VAPID 개인키 보관 | `~/.abyss/vapid-keys.json` 권한 0600. README에 백업 + 권한 명시 |
| A03 Injection | 해당 — push body가 사용자 입력 포함 | 푸시 body는 메시지 미리보기 (preview). HTML escape 후 plaintext. XSS 표면 없음 (Service Worker가 plain text로 표시) |
| A05 Security Misconfiguration | 해당 — Service Worker scope | `/sw.js` 루트 scope. 다른 origin 자원 캐시 안 함 |
| A07 Identity Failure | 해당 — Tailscale 의존 | 공용 인터넷 노출 금지 가이드 강조 |
| A08 Data Integrity | 해당 — 푸시 payload 변조 | VAPID 서명으로 보장 (Web Push 표준) |
| A09 Logging | 해당 — push 실패 로그 | 실패 endpoint 정리 시 로깅. 사용자 메시지 내용은 로그에 남기지 않음 |

### 인증

- 구독 API에 별도 인증 없음 (Tailscale only). 단일 사용자 전제.
- 향후 다중 사용자 지원 시 Supabase Auth 도입 (별도 plan)

### 민감 데이터

- `~/.abyss/vapid-keys.json` — 0600, README 백업 가이드
- `~/.abyss/push-subscriptions.json` — endpoint + p256dh + auth 키. 0600. 노출 시 다른 디바이스 발송 가능하지만 도청 불가 (push 서비스가 중간)
- 푸시 body는 메시지 *미리보기*만 (~80자). 전체 내용은 PWA 열어야 보임 → 잠금화면 정보 누출 최소화

### PCI-DSS

- 해당 없음

## 8. Plan 이탈 방지

- plan에 명시되지 않은 파일 수정 금지
- 텔레그램 제거는 별도 plan (`plan-remove-telegram-2026-XX-XX.md`)으로 분리. 본 plan에서 텔레그램 코드 건드리지 않음
- 만약 푸시 트리거 통합 중 `cron.py` / `heartbeat.py` 시그니처 변경이 필요하면 즉시 중단 + 사용자 승인

## 9. 완료 조건

- [ ] Phase 1-6 모든 체크리스트 완료
- [ ] `make lint && make test` 통과
- [ ] `npm run lint && npm run build && npm test` (abysscope) 통과
- [ ] iOS PWA + Android PWA 실기 검증 완료
- [ ] 텔레그램 메시지 + Web Push 양쪽 정상 도달 (B1 공존 단계)
- [ ] `docs/MOBILE_ACCESS.md` 업데이트
- [ ] README 모바일 섹션 보완
- [ ] CLAUDE.md에 `web_push.py` 모듈 추가 설명
- [ ] status: done 기재
- [ ] PR-B2 (텔레그램 제거) 후속 plan 초안 작성

## 10. 중단 기준

- iOS Safari 16.4+ 환경에서 푸시 도달률이 50% 미만으로 측정될 경우 (Apple Web Push 인프라 이슈)
- `pywebpush` 또는 VAPID 라이브러리에 호환성 문제 발견 시
- HTTPS 요구사항을 Tailscale로 만족시키지 못하는 환경이 다수일 경우 → reverse proxy 가이드 추가 후 재진행

## 후속 plan 예고

- `plan-remove-telegram-2026-XX-XX.md`: handlers.py 삭제, python-telegram-bot 의존성 제거, bot.yaml 마이그레이션, CLI 위저드 정리
- `plan-dashboard-group-collab-2026-XX-XX.md`: 그룹 협업(orchestrator-member) 대시보드 UI 신규
- `plan-session-uuid-2026-XX-XX.md`: 텔레그램 chat_id 종속 끊고 세션 = UUID 통일 (텔레그램 제거 후 자연스러움)
