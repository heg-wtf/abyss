# abyss Docs

abyss 문서 인덱스. 루트 [README.md](../README.md) 가 사용자용 빠른 시작이라면, 이 디렉토리는 내부 아키텍처 / 운영 / 정책 / 가이드 모음이다.

## 핵심

| 문서 | 요약 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 시스템 구조, 모듈 의존 그래프, 메시지/cron/heartbeat 흐름 다이어그램, `bot.yaml` 스키마, 주요 설계 결정의 근거 |
| [TECHNICAL-NOTES.md](TECHNICAL-NOTES.md) | 기능별 구현 디테일. Claude Code 실행 모드, Agent SDK 통합, 스트리밍 파싱, 스킬 MCP 머지, 세션 연속성, 메모리 입출력, IME 입력 처리 |
| [SECURITY.md](SECURITY.md) | 보안 감사 결과. 경로 traversal, 토큰 저장, 레이트 리밋, env 주입, workspace 한도 — 파일 처리·사용자 입력·서브프로세스 코드 작성 전 확인 |
| [ROADMAP.md](ROADMAP.md) | 현재/다음/이후 작업 방향. "지금 어디 쯤" 의 신호 |

## 운영 / 접근

| 문서 | 요약 |
|------|------|
| [MOBILE_ACCESS.md](MOBILE_ACCESS.md) | `/mobile` PWA 사용법, Tailscale 셋업, iOS/Android 홈 추가, Web Push 구독 |
| [HTTPS_REQUIRED.md](HTTPS_REQUIRED.md) | secure-context 가 필요한 기능 정리 (Web Push, mic, Service Worker, clipboard). HTTPS 미적용 시 잠기는 항목 |

## 스킬 / 통합

| 문서 | 요약 |
|------|------|
| [SKILL_AUTHORING.md](SKILL_AUTHORING.md) | 스킬 작성 가이드. GitHub 으로 공유 → `abyss skills add <github-url>` 흐름 |
| [skills/](skills/) | 통합 스킬 가이드 모음 — Gmail / Google Calendar / iMessage / Reminders / Jira / Supabase / Twitter / Image / Translate / QMD |

## 참고 자료

| 경로 | 용도 |
|------|------|
| [landing/](landing/) | `abyss.heg.wtf` 정적 사이트 소스 (GitHub Pages) |
| [comparisons/](comparisons/) | 외부 비교 / 분석 리포트 |

## 문서화 원칙

- 핵심 4개 (ARCHITECTURE / TECHNICAL-NOTES / SECURITY / ROADMAP) 는 항상 최신.
- 운영 문서는 기능이 추가될 때 함께 업데이트.
- 릴리즈 시 ROADMAP 의 "Now" 섹션은 직후 버전을 가리키도록 갱신.
- 신규 통합/백엔드 가이드는 대문자 파일명으로 추가 (`*_SETUP.md` 권장).
