# Plan: abysscope `/mobile` PWA 채팅 화면 + 슬래시 커맨드 통합

- date: 2026-05-13
- status: in-progress
- author: claude
- approved-by: ash84
- branch: feat/mobile-pwa-chat

## 1. 목적 및 배경

abyss는 텔레그램이 모바일 인터페이스이고, abysscope 대시보드가 데스크탑 인터페이스. 두 페인 포인트:

1. **모바일 ↔ 대시보드 끊김**: 텔레그램 chat 단위로 세션이 묶여 있어 같은 봇을 모바일/대시보드에서 동시에 *이어가는* 경험 불가
2. **한 봇에 한 작업만**: 텔레그램 chat_id = 단일 세션. 같은 봇으로 여러 주제 동시 진행 어려움

해결책: **abysscope 자체를 모바일 PWA로 제공**. 텔레그램 의존도를 점진적으로 줄이고, 같은 백엔드(`chat_server.py`)를 모바일에서도 사용. ChatGPT/Claude 앱과 동일 모델 — 백엔드 + 다중 클라이언트.

본 plan은 **1단계: `/mobile` 라우트 + UI 골격 + 슬래시 커맨드 백엔드 통합**까지 다룬다. PWA manifest/SW + Web Push는 후속 plan으로 분리.

### 사용자가 제시한 요구사항

- PWA + Tailscale 접속 가정. `/mobile` 라우트로 접근
- 3단 구조
  - 메인 = 채팅 화면
  - 좌상단 햄버거 → 채팅 리스트 화면
  - 채팅 리스트: 봇 이미지, 봇 이름, 마지막 대화 미리보기 (또는 사용자가 지정한 채팅 이름)
- 채팅 화면 입력바: `[슬래시예약어]` `[첨부]` `[입력]` `[보이스]` 텔레그램 스타일
- 채팅 화면 우상단: workspace 파일 보기 버튼 (대시보드 워크스페이스 트리와 동일)
- 모든 내부 슬래시 커맨드 동작 (`/cron`, `/reset`, `/memory`, …)
- 푸시는 후속 plan

## 2. 예상 임팩트

### 영향받는 서비스/모듈

| 모듈 | 변경 정도 | 비고 |
|---|---|---|
| `src/abyss/handlers.py` | 중 | 슬래시 커맨드 로직 추출, 텔레그램 어댑터로 격하 |
| `src/abyss/commands.py` (신규) | - | 슬래시 커맨드의 플랫폼 무관 구현체 |
| `src/abyss/chat_server.py` | 중 | `/chat` SSE에 슬래시 prefix 라우팅 추가 |
| `abysscope/src/app/mobile/` (신규) | - | 모바일 전용 라우트 트리 |
| `abysscope/src/components/mobile/` (신규) | - | 모바일 전용 컴포넌트 |
| `abysscope/src/lib/abyss-api.ts` | 소 | 채팅 이름 변경 API 추가 |
| `abysscope/src/app/api/chat/` | 소 | 슬래시 커맨드 라우팅 통과 |

### 성능/가용성

- 모바일 라우트 = 데스크탑 라우트와 동일 백엔드. 추가 서비스 없음
- 슬래시 커맨드 추상화 = 텔레그램 핸들러 한 단계 추가. 무시할 수준 (~ms)
- 채팅 이름 매핑 = JSON 파일 1개 추가 (`abysscope_data/.session_names.json`)

### 사용자 경험 변화

- 텔레그램 사용자: 변화 없음 (호환성 유지)
- 대시보드 사용자: `/mobile` 새 진입점. 데스크탑 라우트(`/chat`)는 그대로
- 모바일에서 abysscope 접속 시 자동으로 `/mobile` 리다이렉트 (선택 사항. 기본은 명시적 접근)

## 3. 구현 방법 비교

### 방법 A: 라우트 분리 + 별도 컴포넌트 트리 (purplemux 방식)

```
src/app/chat/        # 데스크탑
src/app/mobile/      # 모바일 (신규)
src/components/chat/         # 공유 가능한 로직
src/components/mobile/       # 모바일 전용 컴포넌트 (신규)
```

- 장점: 코드 격리. 데스크탑 영향 없음. 디버깅 쉬움. purplemux로 검증된 패턴
- 단점: 일부 컴포넌트 중복 가능. 공통 추출은 별도 리팩터

### 방법 B: 반응형 단일 페이지 (`useMediaQuery`로 분기)

```
src/app/chat/page.tsx
  └─ if isMobile: <MobileChatView /> else <DesktopChatView />
```

- 장점: 라우트 하나. URL 통일
- 단점: 컴포넌트 트리 거대해짐. 하이드레이션 시 데스크탑/모바일 깜빡임. iOS PWA에서 viewport 판정 까다로움

### 방법 C: App Router Parallel Routes (`@desktop` + `@mobile`)

```
src/app/chat/
  ├─ @desktop/page.tsx
  ├─ @mobile/page.tsx
  └─ layout.tsx  # 분기 결정
```

- 장점: Next 15+ 네이티브 기능. SSR 분기
- 단점: parallel routes는 API 호환성 까다로움. 학습 곡선 큼. abyss 팀 익숙도 낮음

### 선택: **방법 A**

이유:
1. 사용자가 명시적으로 `/mobile` 라우트 요청. URL 분리가 의도된 디자인
2. purplemux가 대규모 모바일 UI를 이 방식으로 성공 운영 — 검증됨
3. 데스크탑 영향 최소화. 1주 안에 동작 가능한 첫 버전
4. 후속에서 공통 컴포넌트 추출하기 자연스러움

## 4. 구현 단계

### Phase 1: 백엔드 슬래시 커맨드 추출 (3일)

- [ ] `src/abyss/commands.py` 신규 작성
  - [ ] 각 커맨드를 `async def cmd_<name>(bot_name, session_id, args, context) -> CommandResult` 형태로 추출
  - [ ] `CommandResult` 데이터클래스 정의 (text, attachments, parse_mode, requires_reset 등)
  - [ ] 모든 telegram-specific 의존성 제거 (Update, Context 객체 안 받음)
- [ ] `src/abyss/handlers.py` 리팩터
  - [ ] 각 `*_handler`는 `commands.cmd_*`를 호출하는 어댑터로 단순화
  - [ ] `Update`/`Context` → `bot_name`/`session_id`/`args` 변환만 담당
  - [ ] 결과 `CommandResult` → `update.reply_text()` 호출
- [ ] `src/abyss/chat_server.py`
  - [ ] `_handle_chat`에서 메시지 prefix `/` 감지
  - [ ] 슬래시 메시지면 파싱 후 `commands.cmd_*` 직접 호출
  - [ ] 결과를 SSE 한 번에 push (스트리밍 안 함, 단발 응답)
  - [ ] 명령어 목록 엔드포인트 `/chat/commands` 추가 (자동완성용)
- [ ] 추출 대상 커맨드 (handlers.py 등록 순):
  `start`, `help`, `reset`, `resetall`, `files`, `send`, `status`, `model`, `version`, `cancel`, `streaming`, `memory`, `skills`, `cron`, `heartbeat`, `compact`, `bind`, `unbind`
- [ ] 단위 테스트: 각 커맨드가 어댑터 없이도 동작

### Phase 2: `/mobile` 라우트 골격 (1일)

- [ ] `abysscope/src/app/mobile/layout.tsx` — 모바일 전용 레이아웃 (viewport meta, safe-area-inset 처리)
- [ ] `abysscope/src/app/mobile/page.tsx` — 메인 채팅 화면 진입점
- [ ] `abysscope/src/app/mobile/sessions/page.tsx` — 채팅 리스트 화면
- [ ] 데스크탑 라우트(`/chat`)와 격리 확인
- [ ] User-Agent 감지로 `/`(루트) 진입 시 모바일 자동 리다이렉트 옵션 — 기본 OFF, 환경변수로 토글

### Phase 3: 채팅 리스트 화면 (2일)

- [ ] `abysscope/src/components/mobile/mobile-session-list.tsx`
  - [ ] 봇 아바타 (BotAvatar 컴포넌트 재사용)
  - [ ] 봇 이름 + (사용자 지정 이름이 있으면 우선) 표시
  - [ ] 마지막 메시지 미리보기 (1줄, ellipsis)
  - [ ] 시간 표시 (오늘이면 HH:mm, 이전이면 MM.DD)
  - [ ] 미읽음/활성 인디케이터 (선택)
- [ ] 채팅 항목 long-press → 액션 시트 (이름 변경, 삭제)
- [ ] 채팅 이름 변경 기능
  - [ ] `abysscope_data/.session_names.json` 매핑 파일
  - [ ] API: `POST /api/chat/sessions/{id}/rename`, body `{name: string}`
  - [ ] `chat_server.py` `/chat/sessions` 응답에 `display_name`/`custom_name` 필드 추가
- [ ] "새 채팅" 버튼 → 봇 선택 시트 (기존 base-ui Menu 재사용)

### Phase 4: 채팅 화면 (3일)

- [ ] `abysscope/src/components/mobile/mobile-chat-view.tsx` — 메인 컨테이너
- [ ] 상단 네비게이션 바 (`mobile-chat-header.tsx`)
  - [ ] 좌: 햄버거 아이콘 → 채팅 리스트로 이동
  - [ ] 중: 봇 이름 + 표시 이름
  - [ ] 우: 워크스페이스 파일 버튼 (Folder 아이콘) + 보이스 모드 진입 버튼
- [ ] 메시지 영역 (`mobile-message-list.tsx`)
  - [ ] 기존 `ChatMessage` 컴포넌트 재사용 가능 여부 확인. 안 되면 모바일 전용 변형
  - [ ] 자동 스크롤 (`use-stick-to-bottom` 패턴)
  - [ ] 시간 표시 (텔레그램 스타일 — 오른쪽 하단)
- [ ] 하단 입력바 (`mobile-prompt-input.tsx`)
  - [ ] 레이아웃: `[슬래시] [첨부] [입력 textarea] [보이스/전송]`
  - [ ] 슬래시 버튼: 탭하면 슬래시 메뉴 시트 표출 (`/cron`, `/reset` 등). 검색 가능
  - [ ] 첨부 버튼: 사진/카메라/파일 (iOS는 input[type=file] capture, accept 분기)
  - [ ] 입력 textarea: auto-resize. 줄바꿈 = Shift+Enter (모바일은 데스크탑보다 어려움 — 줄바꿈 별도 버튼 제공)
  - [ ] 입력 비어 있으면 보이스 아이콘, 채워지면 전송 아이콘 (텔레그램 패턴)
- [ ] safe-area 처리: 입력바 하단 = `env(safe-area-inset-bottom)` 패딩

### Phase 5: 워크스페이스 파일 패널 (1일)

- [ ] `abysscope/src/components/mobile/mobile-workspace-sheet.tsx`
  - [ ] 우측에서 슬라이드인 (Vaul drawer or shadcn Sheet)
  - [ ] 기존 `WorkspaceTree` 컴포넌트 재사용
  - [ ] 파일 탭 → 다운로드/공유 시트
- [ ] 채팅 헤더 우측 버튼에서 토글

### Phase 6: 슬래시 커맨드 UI (2일)

- [ ] 입력바 좌측 슬래시 아이콘 → 시트 표출
- [ ] `GET /api/chat/commands` 호출하여 사용 가능 커맨드 목록
- [ ] 검색 가능 (cmdk 패턴 또는 단순 filter)
- [ ] 항목 클릭 → 입력창에 `/<command> ` 자동 입력 + 포커스
- [ ] 인자 도움말 표시 (예: `/cron add <description>`)
- [ ] 실행 결과는 일반 메시지처럼 채팅에 표시 (sender = "system" or 봇 아바타)

### Phase 7: Tailscale 접근 가이드 (0.5일)

- [ ] `docs/MOBILE_ACCESS.md` 신규
  - [ ] Tailscale 설치 (맥 + 폰)
  - [ ] abysscope 외부 노출 (`abyss dashboard start --host 0.0.0.0`)
  - [ ] Tailscale 호스트네임으로 폰 접속
  - [ ] iOS PWA: Safari → 공유 → 홈 화면 추가
  - [ ] Android PWA: Chrome → 설치
  - [ ] HTTPS 요구사항 + `tailscale serve` 옵션 안내
- [ ] `README.md`에 모바일 접속 섹션 링크

### Phase 8: 테스트 + 폴리시 (1.5일)

- [ ] iOS Safari 16.4+ 실기 테스트
- [ ] Android Chrome 실기 테스트
- [ ] 가로 모드 처리 검증
- [ ] 키보드 표시 시 입력바 가려짐 검증
- [ ] 메모리 누수 검증 (긴 대화 스크롤)
- [ ] 다국어 (한국어) 글자 잘림 검증

총 작업량: **약 13.5일** (~2.5주, 단일 개발자 기준)

## 5. 테스트 계획

### 단위 테스트

- [ ] `tests/test_commands.py`: 각 슬래시 커맨드 함수가 어댑터 없이도 동작
  - [ ] `/cron list` — 등록된 cron 반환
  - [ ] `/cron add <natural>` — Claude 호출 모킹, 새 cron 등록 검증
  - [ ] `/reset` — 세션 디렉토리 정리 검증
  - [ ] `/memory` — MEMORY.md 읽기 검증
  - [ ] `/skills` — 봇에 attach 된 스킬 목록 반환
  - [ ] `/files` — 워크스페이스 파일 목록 반환
- [ ] `tests/test_chat_server.py`: 슬래시 prefix 라우팅
  - [ ] `POST /chat` body `/help` → CommandResult SSE
  - [ ] `POST /chat` body `일반 메시지` → 기존 LLM 경로
  - [ ] `GET /chat/commands` → 커맨드 메타데이터
- [ ] `tests/test_session_names.py`: 채팅 이름 변경
  - [ ] 매핑 파일 신규 생성
  - [ ] 기존 항목 수정
  - [ ] 빈 이름 → 매핑 제거
  - [ ] 동시 쓰기 락 처리
- [ ] abysscope `__tests__/mobile/*.test.tsx`
  - [ ] `MobileSessionList`: 세션 데이터 렌더링
  - [ ] `MobilePromptInput`: 슬래시/첨부/보이스 버튼 토글 동작
  - [ ] `MobileChatHeader`: 햄버거 클릭 → 라우터 이동

### 통합 테스트

- [ ] 시나리오 1: 모바일에서 슬래시 커맨드 실행
  - 폰 PWA로 abysscope 접속 → 채팅 선택 → `/cron list` 입력 → 결과 메시지로 표시
- [ ] 시나리오 2: 첨부 + 슬래시 혼합
  - 사진 첨부 + 일반 메시지 → 봇 응답 → `/files`로 워크스페이스에 파일 저장 확인
- [ ] 시나리오 3: 텔레그램 ↔ 모바일 대시보드 컨텍스트 공유 (별도 plan에서 다룰 예정이지만 회귀 확인)
  - 텔레그램에서 메시지 → 데스크탑 대시보드에서 같은 봇 대화 확인 → 모바일에서도 동일하게 보이는지
- [ ] 시나리오 4: Tailscale 가이드 따라 폰 PWA 설치
  - 문서대로 진행 → "홈 화면 추가" 가능 → 풀스크린 진입 확인
- [ ] 시나리오 5: 데스크탑 라우트 회귀
  - `/chat` (데스크탑 라우트)이 변경 없이 동작
  - 텔레그램 봇 모든 슬래시 커맨드가 변경 없이 동작
- [ ] 시나리오 6: 채팅 이름 변경
  - 채팅 리스트에서 항목 long-press → "이름 변경" → "경제질문" 입력 → 리스트에 반영
  - 새로고침 후 유지

## 6. 사이드 이펙트

- **handlers.py 시그니처 변경**: 슬래시 커맨드 로직이 `commands.py`로 이동. 기존 텔레그램 핸들러 외부에서 직접 호출하던 코드 없음 → 영향 0
- **chat_server.py SSE 응답 포맷**: 슬래시 결과를 어떻게 표현할지 결정 필요. 일반 메시지와 구분되는 `event: command_result` SSE 이벤트 권장. 기존 클라이언트는 모르는 이벤트 무시 → 호환성 유지
- **모바일 라우트 추가**: 데스크탑 라우트 영향 없음. 단, `next.config` 또는 `middleware`에서 User-Agent 자동 리다이렉트 도입 시 회귀 위험. **기본 OFF**로 출시
- **채팅 이름 매핑 파일**: 신규 파일 (`abysscope_data/.session_names.json`). 기존 데이터와 분리. 마이그레이션 불필요
- **하위 호환성**: 깨지지 않음. 모든 변경은 *추가형* 또는 *내부 리팩터*

## 7. 보안 검토

### OWASP Top 10 항목

| 항목 | 해당 여부 | 대응 |
|---|---|---|
| A01 Broken Access Control | 해당 — 모바일 라우트도 인증 없음 | Tailscale 가정으로 1차는 인증 없음. 향후 `chat_server.py` origin allowlist 확장. plan에 별도 명시 |
| A03 Injection | 해당 — 슬래시 커맨드 args | 각 `cmd_*`에서 args 검증. 기존 텔레그램 핸들러 검증 로직 그대로 이식 |
| A04 Insecure Design | 해당 — 채팅 이름 변경 | 사용자 입력 길이/문자 제한 (예: 1-64자, 컨트롤 문자 금지) |
| A05 Security Misconfiguration | 해당 — User-Agent 자동 리다이렉트 | 기본 OFF. 운영자 명시적 활성화 필요 |
| A07 Identity/Auth Failure | 해당 — Tailscale = 네트워크 레벨 인증 | Tailscale 외부 노출 시 위험. 가이드 문서에 *Tailscale 전용* 명시. 공용 인터넷 노출 금지 경고 |
| A08 Software/Data Integrity | 해당 안 함 | - |
| A09 Logging | 해당 — 슬래시 커맨드 로그 | 기존 텔레그램 로그 패턴 유지. 민감 args (예: `/memory clear`) 마스킹 검토 |

### 인증/인가 변경

- 모바일 라우트 = 데스크탑과 동일 정책 (현재 인증 없음, Tailscale 의존)
- 채팅 이름 변경 API = 누구나 변경 가능. 같은 정책

### 민감 데이터

- 채팅 이름 = 사용자 지정 텍스트. 파일에 평문 저장. 다른 사용자에게 노출 없음 (단일 사용자 환경 가정)
- 슬래시 커맨드 args = 텔레그램과 동일 처리

### PCI-DSS

- 해당 없음

## 8. Plan 이탈 방지

- plan에 명시되지 않은 파일 수정 금지
- 구현 중 다른 접근 필요해지면 즉시 중단, plan 수정, 사용자 재승인

## 9. 완료 조건

- [ ] Phase 1-8 모든 체크리스트 완료
- [ ] `make lint && make test` 통과 (Python + abysscope)
- [ ] iOS PWA + Android PWA 양쪽 실기 동작 확인
- [ ] 텔레그램 봇 회귀 테스트 통과
- [ ] 데스크탑 `/chat` 라우트 회귀 테스트 통과
- [ ] 문서 업데이트: README.md 모바일 섹션, `docs/MOBILE_ACCESS.md`
- [ ] CLAUDE.md 업데이트 (모바일 라우트, commands.py 추가 사항)
- [ ] status: done 기재

## 10. 중단 기준

- Tailscale 가이드 따라도 폰 PWA 설치 안 됨 (HTTPS 인증서 또는 `tailscale serve` 이슈로) → plan에 reverse proxy 옵션 추가
- 슬래시 커맨드 추출 중 `Update`/`Context` 객체에 강하게 묶인 의존성 발견 (예: 파일 다운로드/업로드 처리) → 추출 범위 재정의
- iOS Safari에서 모바일 레이아웃 viewport 처리가 환경별로 깨짐 → 디바이스 매트릭스 축소

## 후속 plan 예고

- `plan-pwa-manifest-push-2026-XX-XX.md`: manifest.json + Service Worker + VAPID + Web Push (이 plan 완료 후)
- `plan-session-uuid-refactor-2026-XX-XX.md`: 텔레그램 chat_id → 세션 UUID 모델 (텔레그램과 모바일 컨텍스트 공유 활성화)
- `plan-multi-session-grid-2026-XX-XX.md`: 한 봇에 N 세션 가시화 (a 페인 해결)
