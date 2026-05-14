# Roadmap

스냅샷이 아니라 방향. 우선순위는 위에서 아래.

## Now — v2026.05.14 직후

- **HTTPS 롤아웃**. `docs/HTTPS_REQUIRED.md` 에 정리된 secure-context 의존 기능 (Web Push 구독, mic / `getUserMedia`, PWA Service Worker, clipboard) 이 모두 잠겨있다. Tailscale `serve --bg --https=443 --set-path=/` 셋업이 완료되면 모바일에서 푸시 알림 + 음성 받아쓰기 + 진짜 PWA standalone 모드가 동작한다.
- **Routines 탭 답장 검증**. PR #61 으로 cron / heartbeat 세션에 사용자가 답장하는 경로가 열렸다 (`POST /chat/routines/<bot>/<kind>/<job>/chat`). 실 사용으로 SDK pool resume + `human` role 필터가 의도대로 도는지 누적 검증 필요.
- **Telegram 잔재 정리 (선택)**. `bot.yaml` 의 `telegram_token` / `telegram_username` / `allowed_users` 필드는 코드에서 안 읽지만 dead field 로 남아 있다. `telegram_botname` 만 display-name fallback shim. 깔끔한 yaml 을 원하면 한 번 훑는 cleanup PR.

## Next — 다음 release 사이클

- **PWA 위에서 다중-봇 협업 다시 설계**. 기존 group surface (orchestrator + member, `telegram_chat_id` binding, `compose_group_context`) 는 통째로 제거됐다. 후속 모델 후보:
  - Dashboard chat 의 다중 봇 방 — 채팅 한 세션에 여러 봇 참여, `@mention` 으로 라우팅
  - cron / heartbeat 같은 자동화 채널을 묶는 "팀" 단위 표시
  - v2026.05.14 릴리즈 노트의 "group은 추후 재설계" 결정 후속
- **모바일 음성 모드 완성**. ElevenLabs Scribe v2 STT + TTS 가 wire 되어 있지만 HTTPS 미적용으로 폰에서 검증 어려움. HTTPS 후 voice round-trip 실제 사용 확인 + UX 폴리시.
- **Routines 자동 새로고침**. 현재 routine detail 페이지는 수동 ⟳ 버튼만 있다. cron 이 새로 실행되면 SSE / poll 로 자동 갱신.

## Later — 후순위 / 아이디어

- **Slash command UX 강화**. 자동완성, 인자 힌트, 명령별 미리보기. 모바일에 ⌘ 아이콘 추가 후 다음 단계.
- **검색 통합**. FTS5 (`conversation_search`) + QMD 콜렉션이 별도로 동작 중. PWA 에서 통합 검색 surface — 채팅 / Routines / 메모리 한 번에.
- **이미지 / PDF 보다 풍부한 mobile preview**. 현재 모바일 chat 은 텍스트 위주. 첨부 PDF preview, image lightbox 등.
- **온보딩 자동화**. `abyss bot add` 가 display_name / personality / role / goal 만 묻는다. 도메인 별 템플릿 (예: "재무 어시스턴트") presets 추가 가능.

## Won't — 명시적으로 안 함

- **Telegram 재도입**. PWA + 대시보드가 모든 surface 를 커버하면서 Telegram 의 유지 비용이 효익을 초과한다는 결론. 필요 시 외부에서 webhook 으로 PWA push 를 trigger 하는 어댑터를 누가 만들면 모를까, abyss core 는 다시 들이지 않는다.
- **Multi-tenant 호스팅**. abyss 는 로컬 Mac 에서 한 사용자가 돌리는 도구. cloud / SaaS 방향으로 끌고 가지 않는다.

---

*이 문서는 "지금 어디 쯤" 의 신호. 실제 진행 상황은 GitHub Issues / PR + 릴리즈 노트를 참고.*
