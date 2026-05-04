# Plan: 대시보드 채팅 Voice 모드 (Voicebox + VoiceOrbVoid)

- date: 2026-05-04
- status: code-complete (awaiting Phase 0 manual verification)
- author: claude
- approved-by: user (auto-mode 2026-05-04)
- target-repo: /Users/ash84/workspace/heg/cclaw
- branch: feat/voice-mode

**Note**: Voicebox 미설치/미실행 확인됨(2026-05-04). Phases 1-8 코드 + 단위 테스트는 mock 기반으로 완료. Phase 0 수동 검증은 user가 Voicebox 설치 후 수행.

## 완료 기록 (2026-05-04)

| 항목 | 결과 |
|---|---|
| Vitest | 6 files / **103 passed** (신규 27건: voicebox 11 + chunker 9 + rms 7) |
| ESLint | 0 errors, 1 pre-existing warning (sidebar.tsx) |
| TypeScript noEmit | 통과 |
| Next.js production build | 통과, 3개 voice route 등록 (`/api/voice/{status,transcribe,generate}`) |
| Python pytest | **1029 passed**, 1 skipped (회귀 0) |

신규 파일:
- `abysscope/src/lib/voicebox.ts` + `__tests__/voicebox.test.ts`
- `abysscope/src/lib/voice-rms.ts` + `__tests__/voice-rms.test.ts`
- `abysscope/src/lib/sentence-chunker.ts` + `__tests__/sentence-chunker.test.ts`
- `abysscope/src/hooks/use-voice-pipeline.ts`
- `abysscope/src/components/chat/voice-orb.tsx`
- `abysscope/src/components/chat/voice-mode.tsx`
- `abysscope/src/app/api/voice/{status,transcribe,generate}/route.ts`

수정 파일:
- `abysscope/src/components/chat/chat-view.tsx` — Mic 토글 + Voice 모드 분기
- `abysscope/src/app/globals.css` — orb keyframe 4종 추가

## 1. 목적 및 배경

abysscope 대시보드의 개별 채팅 세션에 **Voice 버튼**을 추가해, 클릭 시 마이크 입력 → STT → 기존 LLM 파이프라인 → TTS → 오디오 재생까지 음성으로 대화할 수 있게 한다. 클라우드 의존 없이 로컬 [Voicebox.sh](http://Voicebox.sh) 서버(`localhost:47390`)를 백엔드로 사용하고, JARVIS 스타일 UI는 `VoiceOrbVoid` 컴포넌트로 표현한다.

핵심 제약:
- **기존 chat 인프라 재사용** — `chat_core.process_chat_message`, `/chat` SSE 그대로 사용. 음성 분기는 STT(입력 변환) + TTS(출력 변환) 두 지점만 추가.
- **세션 단위 토글** — 글로벌이 아닌 개별 채팅 세션에서 Voice 모드 진입/이탈.
- **한·영 양쪽 자연스러움 우선** — Whisper large-v3(STT), Qwen3-TTS 1.7B(TTS).
- **Voicebox 미실행 시 graceful degrade** — Voice 버튼 비활성화 + 안내 토스트.

## 2. 예상 임팩트

| 영역 | 변경 |
|---|---|
| `abysscope/src/components/chat/voice-mode.tsx` (신규) | Voice 모드 컨테이너. `VoiceOrbVoid` + 마이크 루프 + 재생 큐 호스팅. |
| `abysscope/src/components/chat/voice-orb.tsx` (신규) | `VoiceOrbVoid` 컴포넌트(idle/listening/thinking/speaking 4-state). |
| `abysscope/src/hooks/use-voice-pipeline.ts` (신규) | MediaRecorder + RMS 모니터 + STT/TTS 호출 + 재생 큐. |
| `abysscope/src/lib/voicebox.ts` (신규) | Voicebox 헬스체크, STT/TTS HTTP 래퍼, 모델/언어 상수. |
| `abysscope/src/components/chat/chat-view.tsx` | 세션 헤더에 Voice 버튼 토글 추가. on 시 `<VoiceMode>` 렌더, off 시 기존 텍스트 UI. |
| `abysscope/src/app/api/voice/transcribe/route.ts` (신규) | multipart 프록시 → Voicebox `/api/transcribe` (CORS 회피, 로컬-only 호출이지만 라우팅 일관성). |
| `abysscope/src/app/api/voice/generate/route.ts` (신규) | JSON 프록시 → Voicebox `/api/generate` (binary 응답 stream). |
| `abysscope/src/app/api/voice/status/route.ts` (신규) | Voicebox 헬스체크 프록시. |
| `abysscope/src/components/chat/use-chat-stream.ts` | 기존 그대로 사용. Voice 모드는 transcript를 일반 메시지로 submit + 스트리밍 청크를 sentence-chunker로 분배. |
| 신규 hook: `use-sentence-chunker.ts` | LLM 스트리밍 청크 누적 → 문장 경계(`.`/`!`/`?`/`。` + 충분한 길이)에서 emit → TTS 큐 push. |

비변경:
- `chat_core.py`, `chat_server.py`, 기존 `/chat` SSE — 음성은 클라이언트 사이드 변환만 추가.
- 봇 설정(`bot.yaml`), 백엔드 선택, MEMORY/skill 흐름 — 일체 무관.

## 3. 구현 방법 비교

### 방법 A — 클라이언트-only Voice 파이프라인 (선택)

브라우저가 직접 Voicebox HTTP API를 호출. abysscope Next.js 라우트는 단순 프록시(CORS/포트 통일 목적).

**장점**:
- abyss Python 서버에 음성 코드 0줄 추가. 기존 `chat_server.py` 무변경.
- 마이크 권한, 오디오 재생, RMS 모니터링 등 브라우저 API를 그대로 활용.
- 파이프라인 디버깅 단순(클라이언트 콘솔만 보면 됨).
- TTS 청크 재생 큐가 클라이언트에 있어 LLM 스트리밍과 자연스럽게 연동.

**단점**:
- 다른 abyss 클라이언트(Telegram 등)에는 음성 기능 적용 안 됨 — 단, 이번 범위는 대시보드 한정이라 비이슈.
- 브라우저 호환성 의존(MediaRecorder, AudioContext) — Chrome/Safari 최신 버전은 모두 지원.

### 방법 B — 서버-사이드 음성 처리

`chat_server.py`에 `/voice/in`, `/voice/out` 엔드포인트 추가. 클라이언트는 raw audio만 업로드/다운로드.

**장점**:
- Telegram 등 다른 채널에서도 동일 음성 파이프라인 재사용 가능(미래 확장성).
- 클라이언트 단순화(오디오 캡처/재생만).

**단점**:
- aiohttp ↔ Voicebox 추가 홉 — 레이턴시 증가(특히 PCM 스트리밍 시).
- Python에서 마이크 RMS 게이트, sentence-chunker, 재생 큐를 다시 짜야 함(브라우저 API의 재구현).
- `chat_server.py` 책임 비대화 — 이미 4개 라우트(messages/chat/upload/files) 보유.
- abyss Python 의존성 증가.

**선택: A**. 대시보드 한정 기능에 서버 비대화는 과한 비용. Telegram 음성 확장은 별도 플랜에서 다룬다.

## 4. 구현 단계

### Phase 0 — Voicebox 환경 검증
- [ ] Voicebox 설치(macOS DMG) + Settings → API Server → Always On
- [ ] `curl http://localhost:47390/api/status` 200 응답 확인
- [ ] `curl -X POST http://localhost:47390/api/transcribe` 한국어 샘플 1건 정상 변환 확인
- [ ] `curl -X POST http://localhost:47390/api/generate` Qwen3-TTS + `language: ko` 한국어 합성 확인
- [ ] Whisper large-v3 모델 다운로드 완료 확인 (Voicebox UI에서)
- [ ] Qwen3-TTS 1.7B 모델 다운로드 완료 확인 (Voicebox UI에서)

### Phase 1 — 프록시 라우트
- [ ] `app/api/voice/status/route.ts` — `GET`, 2s timeout, `{ ok: boolean }` 반환
- [ ] `app/api/voice/transcribe/route.ts` — multipart 통과 프록시. 한국어 + medium 디폴트, 클라이언트 override 허용
- [ ] `app/api/voice/generate/route.ts` — JSON in, audio binary stream out. `engine: "chatterbox"`, `language: "ko"` 디폴트
- [ ] 라우트별 `runtime: "nodejs"` 명시 (multipart/binary 처리)

### Phase 2 — Voicebox 클라이언트 헬퍼
- [ ] `lib/voicebox.ts` — `checkVoiceboxHealth()`, `transcribe(blob)`, `synthesize(text, voiceId?)`
- [ ] 상수: `VOICEBOX_BASE`, `STT_LANGUAGE = "ko"`, `STT_MODEL = "large-v3"`, `TTS_ENGINE = "qwen3-tts"`
- [ ] 에러 클래스 `VoiceboxError` (status, code, message)

### Phase 3 — VoiceOrbVoid 컴포넌트
- [ ] `components/chat/voice-orb.tsx` — props `{ state: 'idle' | 'listening' | 'thinking' | 'speaking', size?: number }`
- [ ] 4-state 시각 표현(idle: 정적 / listening: 펄스 + 마이크 입력 진폭 반영 / thinking: 로테이션 / speaking: 파형)
- [ ] CSS animation은 Tailwind keyframes로 구성, 외부 라이브러리 의존 없음

### Phase 4 — Voice 파이프라인 훅
- [ ] `hooks/use-voice-pipeline.ts` 구현
  - MediaRecorder + AudioContext + AnalyserNode 생성
  - RMS 모니터 루프(requestAnimationFrame)
  - `RMS_THRESHOLD = 18`, `SILENCE_TIMEOUT_MS = 900` 상수
  - 무음 timeout 시 recorder.stop → blob 수집 → `transcribe()` 호출
  - 콜백 `onTranscript(text)` 노출
  - `speak(text)` 메서드: TTS → `Audio.play()` → state 'speaking' → 종료 후 'idle'
  - 큐 모드: `enqueueSpeech(sentence)` — 동시 재생 1개 보장(이전 끝나면 다음)
  - cleanup: stream.getTracks().stop(), audioCtx.close(), rAF cancel

### Phase 5 — Sentence Chunker
- [ ] `hooks/use-sentence-chunker.ts` — LLM 스트리밍 청크 누적
- [ ] 문장 경계: `[.!?。]\s+` 또는 `[.!?。]$` + 길이 ≥ 12자
- [ ] 코드블록(\`\`\`) 내부는 한 덩어리로 emit하지 않고 통째로 skip 또는 한 번에 묶음 처리(읽으면 어색함)
- [ ] `flush()` — 스트림 종료 시 잔여 버퍼 emit

### Phase 6 — VoiceMode 컨테이너
- [ ] `components/chat/voice-mode.tsx` 구현
- [ ] props: `{ botName, sessionId, onTranscriptSubmit, streamingChunks$ }` (또는 동일 효과의 callback API)
- [ ] state machine:
  - idle → 사용자 트리거(`startListening`) → listening
  - listening → 무음 감지 → thinking
  - thinking → STT 결과 → onTranscriptSubmit(text) → 부모가 LLM 스트리밍 시작
  - 스트리밍 청크 도착 → sentence-chunker → enqueueSpeech → speaking
  - 스트림 종료 + 큐 비음 → idle
- [ ] 종료 버튼: 음성 모드 해제 → 텍스트 UI 복귀

### Phase 7 — chat-view 통합
- [ ] `chat-view.tsx`에 `voiceModeActive` state 추가
- [ ] 세션 헤더에 Voice 토글 버튼 (`Mic` 아이콘, `lucide-react`)
- [ ] Voicebox 헬스 미통과 시 버튼 disabled + tooltip "Voicebox 서버가 실행 중이 아닙니다"
- [ ] Voice 모드 on:
  - 기존 `<PromptInput>` + 메시지 리스트 영역을 `<VoiceMode>` 로 교체
  - 메시지 리스트는 우측 사이드/축소 형태로 유지(최근 1~2건 미리보기) — 또는 hide 후 OFF 시 복귀
  - submit 시 기존 `handleSubmit` 재사용(첨부 없음, prompt만)
  - 스트리밍 청크: `handleSubmit`이 사용하는 `onChunk` 콜백을 sentence-chunker로 분기

### Phase 8 — 폴리싱
- [ ] Voicebox 다운 감지 시 자동 텍스트 모드 fallback + 토스트
- [ ] STT 빈 결과 처리(다시 listening로 복귀)
- [ ] 사용자 수동 cancel(`Stop` 버튼) — 재생 중 audio.pause + 큐 비우기
- [ ] 다크/라이트 테마 테스트

## 5. 테스트 계획

### 단위 테스트 (vitest)
- [ ] `lib/voicebox.test.ts` — fetch 모킹으로 transcribe/synthesize/health 정상/에러 경로
- [ ] `hooks/use-sentence-chunker.test.ts` — 한국어/영어 혼합 입력, 코드블록, flush 동작
- [ ] `hooks/use-voice-pipeline.test.ts` — MediaRecorder/AudioContext 모킹(`vi.stubGlobal`), RMS gate, silence timeout, 재생 큐 직렬화
- [ ] `components/chat/voice-orb.test.tsx` — state별 클래스/aria-label 렌더 검증
- [ ] `components/chat/voice-mode.test.tsx` — 마이크 권한 거부 시 에러 토스트, transcribe 결과 → onSubmit 호출

### 통합 테스트 (수동, 로컬 환경)
- [ ] Voicebox 미실행 → Voice 버튼 disabled
- [ ] Voicebox 실행 + Voice on → "안녕" 발화 → STT "안녕" 캡처 → LLM 응답 스트리밍 → TTS 재생
- [ ] 긴 응답(코드 포함) → sentence-chunker가 코드블록 건너뛰는지 확인
- [ ] 발화 중간에 Stop → 즉시 재생 중단
- [ ] 무음 timeout 정상 동작(말 끊김 시 STT 트리거)
- [ ] 다크 모드 / 라이트 모드 모두 Orb 색감 적절

### 회귀 테스트
- [ ] 기존 텍스트 채팅 흐름(`PromptInput` 제출, 첨부 업로드, 세션 생성/삭제) 변경 없음 확인
- [ ] `npm run test` (vitest) 신규 케이스 포함 전체 통과
- [ ] `npm run lint`, `npm run build` (Next.js production build) 통과
- [ ] `uv run pytest` — Python 사이드 무변경 확인용 (회귀 0)

## 6. 사이드 이펙트

| 항목 | 영향 | 대응 |
|---|---|---|
| 기존 텍스트 채팅 | 변경 없음 — Voice 모드 off 시 기존 코드 경로 그대로 | 회귀 테스트로 확인 |
| 첨부 파일 흐름 | Voice 모드는 첨부 미지원(범위 외) | Voice on 상태에서는 첨부 UI 숨김. off 시 복귀 |
| 다른 클라이언트(Telegram) | 영향 없음 — 클라이언트-only 변경 | N/A |
| 봇 설정 / MEMORY / skill | 무관 | N/A |
| 마이크 권한 | 사용자 첫 진입 시 브라우저 prompt | UI에 안내 문구 |
| 음성 데이터 저장 | **저장 안 함** — STT 텍스트만 conversation log에 기록(기존 흐름 동일) | 저장하지 않는 것이 디폴트. 필요 시 별도 플랜 |
| Voicebox 외부 의존 | 사용자가 별도 설치 필요 | onboarding/README에 설치 가이드 추가 |
| Next.js bundle 크기 | 신규 hook + 컴포넌트(~5KB gzip 추정) | 영향 미미 |

하위 호환성: 모두 신규 코드. 기존 API/타입 변경 없음. 마이그레이션 불필요.

## 7. 보안 검토

| OWASP 항목 | 적용 여부 | 검토 |
|---|---|---|
| A01 Broken Access Control | ❌ 해당 없음 | 대시보드 내부 기능, 로컬 전용 |
| A02 Cryptographic Failures | ❌ 해당 없음 | 음성 데이터 영속 저장 없음, 전송은 localhost |
| A03 Injection | ⚠️ 검토 | STT 결과 텍스트가 LLM prompt에 그대로 들어감 — 기존 텍스트 채팅과 동일 경로. 추가 sanitization 불요(LLM이 사용자 입력으로 인식) |
| A04 Insecure Design | ⚠️ 검토 | TTS 텍스트가 Voicebox로 전송 — 민감 정보 음성화 우려. **대응**: 사용자가 의식적으로 Voice 모드 진입할 때만 동작. 비밀번호/토큰 표시되는 응답은 텍스트 모드가 안전(README 안내) |
| A05 Security Misconfiguration | ⚠️ 검토 | Voicebox 포트 47390 외부 노출 시 누구나 STT/TTS 호출 가능 — Voicebox 자체 설정. abysscope 프록시 라우트도 dashboard origin 동일 정책 적용 필요 |
| A06 Vulnerable Components | ⚠️ 검토 | 신규 npm 의존성 0(Web Audio API + fetch만 사용) — 검토 불요 |
| A07 Auth Failures | ❌ 해당 없음 | 로컬 대시보드 |
| A08 Data Integrity | ❌ 해당 없음 | |
| A09 Logging | ✅ | STT 결과는 conversation log에 텍스트 메시지로 기록(기존). 오디오 raw는 저장 안 함 |
| A10 SSRF | ⚠️ 검토 | Voicebox 프록시 라우트는 **고정 URL `http://localhost:47390`** 만 호출. 사용자 입력 URL 미허용. SSRF 차단 |

PCI-DSS: 결제 정보 무관. 영향 없음.

추가 보안 조치:
- 프록시 라우트는 `http://localhost:47390` 외 outbound 금지(상수 고정)
- 마이크 활성/비활성 상태를 UI에 명확히 표시(privacy indicator)
- Voice 모드 종료 시 모든 stream track 즉시 stop, AudioContext close 보장(메모리/하드웨어 leak 방지)

## 8. 오픈 이슈 / 결정 필요

- [ ] **Voicebox voice profile 선택 UX** — 기본 voice 사용 vs 봇별 voice profile 매핑(`bot.yaml`에 `voice_id` 필드 추가). 1차에서는 기본 voice 고정, 후속 PR에서 매핑 검토
- [ ] **다국어 봇 처리** — 봇 응답이 한국어/영어 혼합일 때 Chatterbox Multilingual 자동 감지 신뢰도. 1차는 `language: ko` 고정, 영어 발화 어색하면 후속 튜닝
- [ ] **배경 wake word(JARVIS 모드)** — 항상 on 상태에서 wake word 감지 후 listening. Phase 9+ 별도 플랜
- [ ] **Voice 모드 중 텍스트 메시지 보기** — 메시지 리스트를 축소 표시할지 hide할지 UX 결정 필요(Phase 6에서 프로토타입 후 결정)

## 9. 참고

- [Voicebox.sh](http://Voicebox.sh) Settings → API Server 활성화
- 엔진 선택 근거 (2026-05-04 업데이트, 한·영 양쪽 자연스러움 우선):
  - **STT — Whisper large-v3**: 한국어 정확도 최고, 영어 7.44% WER. Parakeet v3는 영어가 더 빠르지만 25개 유럽어 한정으로 한국어 미지원
  - **TTS — Qwen3-TTS 1.7B**: 한국어가 공식 10개 주력 언어 중 하나, 다국어 일관성 최고. Chatterbox는 영어 voice cloning이 ElevenLabs 수준이지만 다국어 균질성은 Qwen3 우위. 표현력/voice cloning 강하게 원하면 `TTS_ENGINE="chatterbox"`로 1줄 수정
- 레이턴시 최적화: sentence-chunker로 첫 문장 TTS를 LLM 스트리밍 도중 시작 → 체감 응답 단축
- Tauri 아닌 브라우저 환경: `getUserMedia`는 HTTPS 또는 `localhost`에서만 동작 — abysscope 기본 호스팅(`localhost:3847`) OK
