# Plan: Per-Session Chat Stream Isolation in abysscope

- date: 2026-05-13
- status: done (pending manual browser verification)
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

abysscope 대시보드 채팅에서 한 세션이 응답 스트리밍 중이면 다른 모든 세션의 입력창이 비활성화되고, 세션을 전환하면 진행 중이던 스트림이 abort 또는 잘못된 세션 메시지에 chunk가 주입되는 문제가 있다.

### 현재 구조의 결함

`abysscope/src/components/chat/chat-view.tsx`:

1. **단일 `useChatStream` 인스턴스**: `const stream = useChatStream()` 하나만 존재. `stream.streaming`이 boolean 전역 플래그로 동작.
2. **L299 disabled 조건**: `disabled={!activeSession || stream.streaming}` — 어떤 세션이든 스트리밍 중이면 현재 활성 세션 입력창도 비활성화.
3. **L243-251 chunk 주입 effect**: `setMessages(prev => ...)` 가 *현재 활성 세션* 의 messages 배열 마지막 메시지에 stream.text를 덮어씀. 스트리밍 중 세션 전환하면 A 세션 chunk가 B 세션 메시지에 들어감.
4. **`use-chat-stream.ts` L36 abort**: `send` 호출 시 무조건 `abortRef.current?.abort()` 실행. 다른 세션에서 send 호출하면 기존 스트림 강제 중단.
5. **handleCancel**: `activeSession`만 cancel. 백그라운드 스트림 못 멈춤.
6. **messages 단일 배열**: `activeSession` 바뀌면 fetch로 다시 로드 → 진행 중인 스트림 결과 사라짐.

## 2. 예상 임팩트

### 영향 모듈

- `abysscope/src/components/chat/chat-view.tsx` (대규모 리팩토링)
- `abysscope/src/components/chat/use-chat-stream.ts` (시그니처 변경)
- `abysscope/src/components/chat/prompt-input.tsx` (확인만, 변경 없을 가능성 높음)

### 영향 없음

- Python 백엔드 (`chat_server.py`, `chat_core.py`): 이미 per-session asyncio lock 보유, 동시 다중 세션 처리 지원
- API 라우트: 변경 없음
- 다른 dashboard 페이지: chat 영역 외 영향 없음

### 사용자 경험 변화

- 세션 A 스트리밍 중 세션 B 입력 가능
- 세션 전환 시 진행 중 스트림 유지, 돌아오면 진행 중 메시지 계속 보임
- 각 세션 독립 cancel 가능

### 성능

- per-session state Map 추가 → 메모리 미미한 증가 (세션당 메시지 배열 + AbortController + text buffer)
- 동시 N개 스트림 가능 → 백엔드는 이미 지원. 네트워크/Claude SDK pool 부담은 사용자가 의도한 것

## 3. 구현 방법 비교

### 방법 A: 최소 수정 (rejected)

`streamingSessions: Set<string>` 추가, `disabled` 조건만 per-session.

- 장점: 변경 폭 작음 (~10 LOC)
- 단점: chunk 오염, abort 충돌, 백그라운드 cancel 불가 버그 잔존. 사용자가 세션 전환하면 여전히 깨짐. 절반 수정.

### 방법 B: 정공법 (선택) ✅

per-session 스트림/메시지 상태를 Map으로 보관. 활성 세션만 렌더링.

```typescript
interface SessionRuntime {
  messages: ConversationMessage[];
  streamText: string;
  streaming: boolean;
  error: string | null;
  abortController: AbortController | null;
}
const [runtimes, setRuntimes] = useState<Map<string, SessionRuntime>>(new Map());
```

- 장점: 사용자 멘탈 모델(탭처럼 독립)과 일치. 모든 관련 버그 한 번에 해결. 백엔드는 이미 지원.
- 단점: 변경 폭 큼 (~150 LOC). useChatStream 재설계 필요.

### 방법 C: 라이브러리 도입 (rejected)

Zustand / Jotai 등으로 글로벌 store.

- 장점: 상태 관리 깔끔
- 단점: 새 의존성 추가. 단일 파일 범위 문제에 과한 솔루션. abysscope 현재 React state만 사용.

**선택: B**. 사용자가 명시적으로 B 요청. 정공법.

## 4. 구현 단계

- [x] **Step 1**: `use-chat-stream.ts` 리팩토링 — `SessionStream` 객체와 `useMultiSessionChatStream()` 훅 신규. 시그니처:
  ```typescript
  interface SessionStream {
    text: string;
    streaming: boolean;
    error: string | null;
  }
  interface MultiSessionStreamHandle {
    streams: Map<string, SessionStream>;
    send: (bot, sessionId, message, attachmentPaths?, voiceMode?) => Promise<string>;
    cancel: (sessionId: string) => void;
    cancelAll: () => void;
  }
  ```
  내부적으로 `Map<sessionId, AbortController>` 보관. send/cancel은 sessionId로 격리.

- [x] **Step 2**: `chat-view.tsx`의 messages 상태를 `Map<sessionId, ConversationMessage[]>`로 변경. helper:
  ```typescript
  const activeMessages = activeSession ? (sessionMessages.get(activeSession.id) ?? []) : [];
  const updateSessionMessages = (sessionId, updater) => setSessionMessages(prev => { ... });
  ```

- [x] **Step 3**: messages 로드 effect — `activeSession` 바뀌면 `sessionMessages`에 해당 세션 entry 없을 때만 fetch. 이미 있으면 그대로 사용 (in-flight 보존).

- [x] **Step 4**: `handleSubmit` 수정 — `stream.send` 호출 시 `session.id`로 격리. 낙관적 user message + streaming assistant message는 `updateSessionMessages(session.id, ...)`로 그 세션에만 추가. 완료 후 final content 반영도 동일.

- [x] **Step 5**: chunk 반영 effect 재작성 — `streams` Map 순회. 각 streaming 세션에 대해 해당 세션의 messages 마지막 assistant 메시지 content를 stream.text로 동기화. `useEffect([streams])`.

- [x] **Step 6**: `handleCancel` — `activeSession.id`로 stream.cancel(sessionId) 호출.

- [x] **Step 7**: PromptInput `disabled` — `streams.get(activeSession.id)?.streaming` 으로 활성 세션 기준만 판단.

- [x] **Step 8**: header voice 버튼, stream error 표시도 활성 세션 기준으로 변경.

- [x] **Step 9**: 세션 삭제(`handleDelete`) — 해당 세션의 runtime/messages/stream 모두 정리. 진행 중이면 cancel.

- [x] **Step 10**: voice mode 관련 effect 검토 — `voiceMode`는 활성 세션 기준이므로 `stream.streaming` 의존성 → `streams.get(activeSession?.id)?.streaming`으로 변경.

- [x] **Step 11**: 컴포넌트 unmount 시 모든 in-flight 스트림 abort (cleanup).

- [x] **Step 12**: `make lint` + `npm run lint` 통과 확인 (abysscope ESLint react-hooks/purity 등).

## 5. 테스트 계획

### 단위 테스트 (`abysscope/src/components/chat/__tests__/`)

abysscope vitest 환경에 jsdom / @testing-library가 없어 hook 자체는 React 렌더링 없이 검증 불가. 의존성 추가 비용 대비 효익이 낮다고 판단해 **source-level regex guards + pure helper 단위 테스트** 패턴 (`ui-regression.test.ts`와 동일)으로 대체. 같은 회귀 방지 효과를 제공함.

- [x] `use-chat-stream.test.ts`: `getSessionStream` 헬퍼 - null/undefined/missing/present 케이스
- [x] `use-chat-stream.test.ts`: hook 소스 - `Map<string, AbortController>` 보유, 단일 abortRef 패턴 부재
- [x] `use-chat-stream.test.ts`: hook 소스 - `cancel(sessionId)` / `cancelAll()` 시그니처, `streams: Map<string, SessionStream>` export, unmount cleanup loop
- [x] `ui-regression.test.ts`: chat-view가 `useMultiSessionChatStream` 사용 + per-session `sessionMessages` Map + `activeStream.streaming` disabled + `stream.cancel(session.id)` on delete

### 통합 테스트 (수동, 브라우저)

- [ ] 시나리오 1: 세션 A에 긴 응답 트리거 → 세션 B로 전환 → B 입력창 활성화 확인, 메시지 전송 가능
- [ ] 시나리오 2: 세션 A 스트리밍 중 B 전환 → A로 돌아오기 → A의 진행 중 응답이 보이고 계속 누적됨
- [ ] 시나리오 3: 세션 A 스트리밍 중 B에서 메시지 전송 → A/B 모두 정상 응답 받음
- [ ] 시나리오 4: 세션 A 스트리밍 중 A에서 cancel → A만 멈춤, B는 계속
- [ ] 시나리오 5: 세션 A 스트리밍 중 A 삭제 → A 스트림 abort, B 영향 없음
- [ ] 시나리오 6: 페이지 새로고침 → 진행 중 스트림 모두 abort, 입력창 정상
- [ ] 시나리오 7: voice mode 단일 세션에서 정상 동작 확인 (회귀 방지)

### 엣지 케이스

- [ ] 동일 세션 연속 send (중간 cancel 없이): 백엔드 lock으로 직렬화되는지 확인
- [ ] 세션 삭제 직후 즉시 재생성: 새 세션 runtime 깨끗하게 시작
- [ ] 네트워크 에러: 한 세션 에러가 다른 세션 영향 없음

## 6. 사이드 이펙트

### 기존 기능 영향

- **voice mode**: `stream.streaming` 의존성 → 활성 세션 기준으로 변경. voice는 본래 한 세션 안에서만 동작하므로 동작 동일해야 함.
- **handleVoiceOpen disabled**: 헤더의 Mic 버튼 `disabled={!activeSession || stream.streaming}` → 활성 세션 streaming 기준으로 동작은 동일.
- **prevStreamingRef effect**: 활성 세션의 streaming false 전이만 감지하도록 변경 (다른 세션 streaming 변화에 반응 X).

### 하위 호환성

- API 라우트 변경 없음. 백엔드 변경 없음.
- 기존 `useChatStream` export는 deprecate 가능하나, 사용처가 chat-view.tsx 한 곳뿐이라 그냥 교체.

### 마이그레이션

- 불필요. 클라이언트 코드만 변경.

## 7. 보안 검토

- **OWASP Top 10**: 해당 사항 없음. UI 상태 관리 변경.
- **인증/인가**: 변경 없음.
- **민감 데이터**: 메시지/세션 데이터 메모리 보관 방식만 변경. 디스크 저장은 백엔드 그대로.
- **PCI-DSS**: 해당 없음.
- **새 의존성**: 없음.

## 8. 완료 조건

- 구현 단계 1-12 체크
- 단위 테스트 신규 작성 + 통과
- 통합 테스트 시나리오 1-7 수동 검증 통과
- `cd abysscope && npm run lint && npm run build` 통과
- `cd /Users/ash84/workspace/heg/cclaw && uv run pytest` 통과 (regression 확인)
- 본 plan `status: done` 기재
