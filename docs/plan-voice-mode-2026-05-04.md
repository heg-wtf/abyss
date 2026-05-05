# Plan: Dashboard Chat Voice Mode (ElevenLabs)
- date: 2026-05-04
- status: in-progress
- author: claude
- approved-by: user (2026-05-04)

## 1. 목적 및 배경

abysscope 대시보드 채팅에 자비스 스타일 음성 대화 기능 추가.
채팅 헤더 우측 Voice 버튼 → 음성 입력(STT) + 음성 응답(TTS) 모드 전환.
STT/TTS 모두 ElevenLabs API 단일 키로 처리.

## 2. 예상 임팩트

- 영향 파일: `chat-view.tsx`, `prompt-input.tsx`, `chat_server.py`, `config.py`
- 신규 파일: `voice-orb.tsx`, `use-voice-mode.ts`
- 신규 API 라우트: `/chat/transcribe`, `/chat/speak`
- 기존 채팅 흐름(SSE) 변경 없음 — voice mode는 텍스트 submit 위에 레이어로 얹힘
- UX 변화: 헤더 Voice 버튼, 오브 애니메이션 오버레이, 자동 전송

## 3. 구현 방법 비교

### A. 브라우저 Web Speech API (무료)
- 장점: 설치 없음, 레이턴시 낮음
- 단점: 한국어 정확도 낮음, 브라우저별 지원 불일치, TTS는 로봇 느낌

### B. ElevenLabs STT(Scribe v2) + TTS (선택)
- 장점: 한국어 정확도 높음, 자연스러운 TTS, 단일 API 키, 150ms STT 레이턴시
- 단점: 유료 (STT: 캐릭터 기반, TTS: 캐릭터 기반)

**B 선택 이유**: 자비스 느낌은 TTS 음질이 결정적. ElevenLabs이 현재 최선.
이전 Whisper 환각 문제(PR #39)는 VAD 기반 무음 필터링으로 해결.

## 4. 구현 단계

### 4-1. Backend (chat_server.py)
- [ ] `ELEVENLABS_API_KEY` env var 읽기 (`config.py` 또는 `os.environ`)
- [ ] `POST /chat/transcribe` 라우트 추가
  - multipart audio 수신 → ElevenLabs `POST /v1/speech-to-text` 호출 (scribe_v2, language_code=ko)
  - 응답: `{ "text": "..." }`
  - 무음/짧은 오디오 필터: `language_probability < 0.5` 이면 빈 text 반환
- [ ] `POST /chat/speak` 라우트 추가
  - JSON `{ "text": "...", "voice_id": "..." }` 수신
  - ElevenLabs `POST /v1/text-to-speech/{voice_id}` 호출 (eleven_multilingual_v2, mp3_44100_128)
  - 바이너리 mp3 스트리밍 응답 (Content-Type: audio/mpeg)

### 4-2. Frontend Hook (use-voice-mode.ts)
- [ ] `useVoiceMode()` 훅 작성
  - 상태: `idle | recording | processing | speaking`
  - `startRecording()`: MediaRecorder + VAD (silence 1.5s → auto stop)
  - `stopRecording()`: 녹음 종료 → blob 생성
  - `transcribe(blob)`: `POST /api/chat/transcribe` → text 반환
  - `speak(text)`: `POST /api/chat/speak` → AudioContext 재생
  - `cancel()`: 녹음 중단 또는 오디오 재생 중단

### 4-3. VAD (Voice Activity Detection)
- [ ] `@ricky0123/vad-web` 패키지 추가 (브라우저 VAD)
  - 또는: RMS 에너지 기반 간단 VAD 직접 구현 (의존성 최소화)
  - 1.5초 침묵 감지 → 자동 전송
  - 최소 오디오 길이 300ms 미만이면 무시

### 4-4. Frontend UI
- [ ] `voice-screen.tsx` 컴포넌트 작성 (채팅 화면 전체 대체)
  - 레이아웃: 봇 이름 + ✕ 닫기 버튼 (상단), 애니메이션 오브 (중앙), 상태 텍스트 (하단)
  - 상태별 오브 CSS 애니메이션:
    - `idle`: 조용한 pulse (대기)
    - `recording`: 빨간/강한 pulse (듣는 중)
    - `processing`: 회전 스피너 (처리 중)
    - `speaking`: 파란 wave (말하는 중)
  - ✕ 클릭 → voice mode 종료, 채팅 화면 복귀

- [ ] `chat-view.tsx` 수정
  - 헤더 우측에 Voice 버튼 추가 (`activeSession` 있을 때만 활성화)
  - `voiceMode` boolean 상태
  - Voice 버튼 클릭 → 채팅 화면 전체가 `VoiceScreen`으로 교체
  - `useVoiceMode()`에서 transcript 나오면 → `handleSubmit()` 자동 호출
  - LLM 응답 완료(streaming=false) 감지 → `speak(assistantMessage)` 자동 호출
  - voice mode 종료 → 채팅 화면 복귀 (메시지 히스토리 유지)

### 4-5. API 라우트 (Next.js)
- [ ] `src/app/api/chat/transcribe/route.ts` — multipart 프록시 → chat_server `/chat/transcribe`
- [ ] `src/app/api/chat/speak/route.ts` — JSON 프록시 → chat_server `/chat/speak`, binary stream 전달

### 4-6. 설정
- [ ] `ELEVENLABS_API_KEY` 환경 변수 문서화 (README 또는 CLAUDE.md)
- [ ] 기본 voice_id 하드코딩: `pNInz6obpgDQGcFmaJgB` (Adam, 자비스 느낌)
  - 추후 설정 페이지에서 변경 가능하도록 bot.yaml에 `voice_id` 필드 추가 고려 (이번 scope 외)

## 5. 테스트 계획

**단위 테스트 (Python):**
- [ ] `test_chat_server.py`: `/chat/transcribe` — 정상 오디오, language_probability < 0.5 필터, 잘못된 형식
- [ ] `test_chat_server.py`: `/chat/speak` — 정상 텍스트, 빈 텍스트, 긴 텍스트
- [ ] ElevenLabs API 호출은 mock 처리

**통합 테스트 (수동):**
- [ ] Voice 버튼 클릭 → 오브 recording 상태 확인
- [ ] 말하고 1.5초 침묵 → 자동 transcribe → 텍스트 채팅 전송
- [ ] LLM 응답 완료 → TTS 자동 재생
- [ ] Voice 모드 중 오브 클릭 → 녹음/재생 취소
- [ ] TTS 재생 중 새 녹음 시작 → 재생 중단 후 녹음 시작
- [ ] `ELEVENLABS_API_KEY` 없을 때 → Voice 버튼 비활성화 + 툴팁

## 6. 사이드 이펙트

- 기존 텍스트 채팅 흐름 영향 없음 (Voice는 추가 레이어)
- `handleSubmit` 재사용 — voice transcript가 텍스트로 들어오는 구조
- 브라우저 마이크 권한 요청 발생 (첫 Voice 버튼 클릭 시)
- `chat_server.py`에 httpx 의존성 추가 필요 (ElevenLabs API 호출)
  - 이미 `httpx`가 `pyproject.toml`에 있는지 확인 필요

## 7. 보안 검토

- `ELEVENLABS_API_KEY` 서버(Python)에서만 사용, 프론트엔드에 노출 안 됨
- `/chat/transcribe`: 오디오 파일 크기 제한 필요 (최대 10MB)
- `/chat/speak`: 텍스트 길이 제한 (최대 5000자 — ElevenLabs 제한 고려)
- Origin allowlist: 기존 `_origin_allowed()` 그대로 적용
- PCI-DSS: 해당 없음
- 오디오 파일은 메모리 처리 후 디스크 저장 없음

## 8. 완료 조건

- 구현 단계 체크리스트 100% 완료
- 테스트 체크리스트 100% 완료
- `make lint && uv run pytest` 통과
- 사이드 이펙트: 기존 텍스트 채팅 회귀 없음 확인
- `status: done` 기재
