# Plan: Restore Orb Voice Mode on Mobile PWA Chat

- date: 2026-05-15
- status: in-progress
- author: claude
- approved-by: ash84

## Context

The mobile PWA chat (`/mobile/chat/<bot>/<sid>`) currently has a mic
button that runs a dictation-style flow: ElevenLabs Scribe v2 VAD
transcribes speech and appends the result to the textarea — the user
still has to tap Send. The previous desktop `/chat` route had a fuller
"voice mode": tap mic → full-screen Orb UI → talk → auto-submit with
`voice_mode: true` → assistant reply auto-TTS'd → recording
auto-restarts. That surface was removed in commit `c983c9b` along with
the desktop `/chat` route, with a comment in `mobile-chat-screen.tsx`
line 136 explicitly flagging "follow-up that wires the orb UI back in".

Now that the Tailscale Serve HTTPS proxy is live and the phone can
reach the dashboard over a secure origin (`getUserMedia` works), the
follow-up is unblocked. This plan restores the orb voice-mode loop on
mobile, sharing the same `useVoiceMode` hook + Scribe/TTS proxies the
desktop version used, packaged as a full-screen overlay instead of a
right sidebar.

## 1. 목적 및 배경

- 사용자가 폰에서 "마이크 → 받아쓰기 → 직접 Send" 흐름이 아닌
  "마이크 → 대화형 voice mode (Orb)" 흐름을 원함
- 백엔드(`voice_mode` flag, Korean spoken prompt injection,
  `/chat/speak`, `/chat/scribe-token`)는 이미 존재. UI만 복원
- 데스크톱 `/chat` 라우트가 제거되어 voice mode가 어디서도 동작하지
  않음. 모바일을 canonical surface로 못박은 결정과도 일치

## 2. 예상 임팩트

- 영향 모듈: `abysscope/src/components/mobile/mobile-chat-screen.tsx`
  (수정), `abysscope/src/components/chat/voice-screen.tsx` (신규 —
  c983c9b^ 의 파일을 그대로 복원)
- API/서버: 변경 없음. `voice_mode: true` flag는 이미
  `chat_server._handle_chat` (line 1075/1137) 에서 처리됨
- 사용자 경험: 모바일 마이크 버튼 동작 변경. 이전 "받아쓰기 후
  textarea 채워줌" → 신규 "Orb 풀스크린, 자동 송수신 루프"
- 성능: 추가 비용 없음. TTS는 user-initiated 일 때만 호출됨

## 3. 구현 방법 비교

### A. (선택) 풀스크린 오버레이 + 복원된 `VoiceScreen` 컴포넌트 그대로 재사용

`VoiceScreen` 은 `flex h-full flex-col` 레이아웃이라 `fixed inset-0
z-[60]` 컨테이너에 넣으면 모바일 풀스크린이 자연스럽게 맞음.
삭제 전 desktop chat-view 가 쓰던 wiring 패턴(`prevStreamingRef`,
auto-restart effect, voice handle 게이트)도 모바일 screen 의 기존
`previousStreamingRef` (line 344) 와 그대로 합쳐짐.

- 장점: 코드 재사용 최대. 삭제된 컴포넌트를 git 에서 그대로 복원해
  diff/리뷰가 명확. 모바일에서도 desktop 의 UX 가 그대로 재현됨.
- 단점: 모바일 화면 전체를 덮어 메시지 히스토리가 잠시 안 보임.
  (단, voice mode 종료 시 즉시 복귀하므로 실사용에서 문제 없음.)

### B. 하단 시트(slide-up) + Orb

채팅 메시지를 위쪽에 유지하면서 하단 50–70% 만 Orb 시트로 덮음.

- 장점: 메시지 히스토리 보면서 음성 가능
- 단점: 시트 컴포넌트 신규 작성 필요. desktop 의 voice mode 와
  시각적으로 다름. 사용자의 "동일하게" 요청과 불일치

### C. 기존 받아쓰기 유지 + 별도 "Voice Mode" 버튼 추가

마이크 = 받아쓰기, 새 버튼 = voice mode. 두 모드 공존.

- 장점: 기존 사용자 기존대로
- 단점: 사용자가 명시적으로 "받아쓰기 하지 말고" 라고 했음. 폐기

→ **A 선택**. 사용자 의도 정확히 매치 + 코드 재사용 최대 + git
히스토리에서 동일 로직 그대로 복원 가능.

## 4. 구현 단계

- [x] Step 0: feature branch `feat/mobile-voice-mode-orb` 생성 + 본
      plan doc 작성
- [ ] Step 1: `abysscope/src/components/chat/voice-screen.tsx` 복원
- [ ] Step 2: `mobile-chat-screen.tsx` 수정 (voiceMode 상태, 콜백
      분기, executeStreamSend voiceMode 인자, auto-speak/restart
      effect, VoiceScreen 풀스크린 오버레이 렌더)
- [ ] Step 3: `mobile-route.test.ts` source-regex guard 추가
- [ ] Step 4: `cd abysscope && pnpm lint && pnpm test`
- [ ] Step 5: 폰(HTTPS Tailscale) 으로 실제 동작 검증
- [ ] Step 6: commit (gitmoji `✨ feat:`) + PR 생성

## 5. 테스트 계획

### 단위 테스트 (`mobile-route.test.ts`, source-regex 스타일)

- [ ] mobile-chat-screen.tsx 가 `VoiceScreen` 을 import 한다
- [ ] mobile-chat-screen.tsx 가 `voiceMode` 상태를 선언한다
- [ ] mobile-chat-screen.tsx 가 stream.send 호출 시 voiceMode 인자
      를 전달한다 (또는 `voice_mode: true` 가 등장한다)
- [ ] mobile-chat-screen.tsx 에 voice mode auto-restart 패턴이
      존재한다
- [ ] voice-screen.tsx 가 `Orb`, `useTheme`, `onClose` 를 사용한다

### 통합 테스트 (수동, 폰 HTTPS Tailscale URL)

- [ ] 시나리오 1: idle 상태에서 마이크 탭 → Orb 풀스크린, "듣는 중"
      라벨, partial transcript 표시
- [ ] 시나리오 2: 0.5s 무음 → Scribe VAD commit → 메시지 자동 전송
      ("처리 중")
- [ ] 시나리오 3: assistant 응답 스트리밍 완료 → `/chat/speak` 호출,
      Web Audio 로 한국어 구어체 TTS 재생 ("응답 중")
- [ ] 시나리오 4: TTS 종료 → 자동 recording 재시작 (`speaking → idle`)
- [ ] 시나리오 5: X 버튼 → voice.cancel(), 오버레이 닫힘
- [ ] 시나리오 6: voice mode 중 workspace drawer 토글 시도 →
      handleVoiceClose 가 먼저 실행되어 voice mode 종료 후 drawer
      열림

## 6. 사이드 이펙트

- 기존 "마이크 = 받아쓰기" 동작 폐기. 사용자가 명시 요청
- `stream.send` 시그니처 변경 없음(5번째 optional 인자 기존 존재).
  호출자만 인자 전달 추가
- 모바일 화면 전체를 가리는 오버레이가 추가됨. SlideDrawer, slash
  Dialog 와 동시 활성화 방지를 위해 voice mode 진입 시 workspace
  drawer 강제 close (desktop 패턴 그대로)
- 하위 호환성: 깨지지 않음. 백엔드 변경 없음
- PWA cache: SW 가 새 voice-screen.tsx 번들을 받아야 함. 자동
  refresh (수동 reload 1회 정도 필요할 수 있음)

## 7. 보안 검토

- OWASP A03 Injection: 추가 사용자 입력 진입점 없음. 음성 transcript
  는 기존 chat 메시지 경로 동일 처리
- A01 Broken Access Control: `/chat/speak`, `/chat/scribe-token` 은
  Next.js 측 origin allowlist + `chat_server.py` 의
  `ALLOWED_ORIGINS` (env override 가능) 그대로 사용
- A02 Cryptographic Failures: ElevenLabs Scribe WebSocket 은 단명
  JWT(scribe-token) 발급 구조. 토큰 라이프사이클 변경 없음
- 민감 데이터: 음성 → ElevenLabs (기존). 새 외부 의존성 없음
- HTTPS 전제: Tailscale Serve 이미 켜짐. `getUserMedia` 동작 보장
- PCI-DSS: 비해당

## Critical Files

- 신규: `abysscope/src/components/chat/voice-screen.tsx`
- 수정: `abysscope/src/components/mobile/mobile-chat-screen.tsx`
- 수정: `abysscope/src/components/mobile/__tests__/mobile-route.test.ts`

## Verification (end-to-end)

1. 브랜치 체크아웃 후 `cd abysscope && pnpm lint && pnpm test`
2. `abyss restart` (대시보드 재빌드)
3. 폰에서 `https://ash84-macbookpro-home.tail76fd8.ts.net` 접속,
   PWA 재설치 (origin 변경 반영)
4. `/mobile/chat/<bot>/<sid>` 진입 → 푸터 마이크 탭 → 통합 테스트
   시나리오 1–6 통과 확인
