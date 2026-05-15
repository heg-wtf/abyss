# Plan: Sanitize + Auto-Retry Anthropic Upstream 5xx Errors

- date: 2026-05-15
- status: in-progress
- author: claude
- approved-by: ash84

## Context

Anthropic API 가 5xx (특히 `529 overloaded_error`) 를 반환하면
Claude Code CLI 는 raw JSON 을 일반 assistant 텍스트로 출력한다.
프로세스는 exit code 0 으로 종료되므로 abyss 는 정상 응답으로
간주, raw JSON 을 markdown 과 채팅 UI 에 그대로 노출한다.

```
API Error: 529 {"error":{"message":"{\"type\":\"error\",\"error\":
{\"type\":\"overloaded_error\",\"message\":\"Overloaded\"},
\"request_id\":\"req_011Cb3RtVZBrZgTH4FQB7tct\"} ..."}}
```

본 PR 은 두 가지를 동시에 처리한다:

1. **Auto-retry**: 알려진 retryable 패턴 (5xx / 429) 매칭 시 지수
   백오프로 자동 재시도.
2. **Sanitize**: 재시도 소진 또는 non-retryable 시 사용자에게는
   한국어 안내를, markdown 에는 운영자용 HTML 코멘트로
   `request_id` + status 를 남긴다.

## 1. 목적

- end-user 가 보는 raw JSON 제거
- 일시 5xx 는 자동 복구
- 운영자 추적용 `request_id` 보존

## 2. 예상 임팩트

- 영향 모듈:
  - 신규: `src/abyss/upstream_errors.py`, `tests/test_upstream_errors.py`
  - 수정: `src/abyss/chat_core.py`, `src/abyss/chat_server.py`,
    `tests/test_chat_core.py`,
    `abysscope/src/components/chat/use-chat-stream.ts`,
    `abysscope/src/components/mobile/__tests__/mobile-route.test.ts`
- 사용자 경험: 5xx 발생 시 spinner 유지 후 깨끗한 응답. 실패도
  raw JSON 대신 한국어 안내
- 성능: 정상 응답엔 추가 비용 0. 에러 시만 retry 지연 (최악 ~9s)
- 토큰: retry 비용 미미 (5xx 는 입력 토큰만 소비)

## 3. 구현 방법 (A 선택)

`chat_core.process_chat_message` 외부 wrap. 단일 지점, backend-
agnostic, 기존 resume-fallback 와 독립. SSE `reset_partial`
이벤트로 프론트 partial bubble 정리.

대안 B (claude_runner 안) / C (클라이언트 측) 는 backend 다중화
대응 / 토큰 가시성 측면에서 부적합.

## 4. 구현 단계

- [x] Step 0: feature branch + plan doc
- [ ] Step 1: `src/abyss/upstream_errors.py` 작성
- [ ] Step 2: `chat_core.process_chat_message` retry wrap
- [ ] Step 3: `chat_server._handle_chat` on_reset SSE
- [ ] Step 4: `use-chat-stream.ts` reset_partial 처리
- [ ] Step 5: 테스트 추가 (upstream_errors, chat_core, 프론트)
- [ ] Step 6: `make lint && make test` / pnpm lint+test+build
- [ ] Step 7: commit + PR

## 5. 테스트 계획

### 단위 — `tests/test_upstream_errors.py`

- [ ] 529 overloaded → retryable=True, request_id 추출
- [ ] 503 → retryable=True
- [ ] 429 → retryable=True
- [ ] 400 → retryable=False
- [ ] 정상 응답 → None
- [ ] JSON 없는 `API Error: 529` → retryable=True, request_id=None
- [ ] sanitize 529 → 한국어 + HTML 코멘트
- [ ] sanitize 429 → 다른 한국어 (rate limit 톤)

### 단위 — `tests/test_chat_core.py` (확장)

- [ ] 정상 응답: retry 없음
- [ ] 1차 529 → 2차 성공: on_reset 1회, sleep 1회, 깨끗한 응답 저장
- [ ] 3차 모두 529: sanitize 저장
- [ ] 1차 400: 즉시 sanitize, retry 없음
- [ ] `max_attempts: 0`: retry 없이 sanitize

### 통합 (수동)

- [ ] 정상 채팅 회귀 없음
- [ ] 자연 발생 5xx 대기 후 markdown / UI 확인

## 6. 사이드 이펙트

- markdown assistant 메시지가 sanitized 텍스트로 바뀜 (raw JSON 폐기)
- 첫 시도 에러 chunk 짧게 leak → `reset_partial` 로 즉시 비워짐
- cron / heartbeat 경로는 on_reset=None, retry+sanitize 만 적용
- 기존 Exception → `Error: {error}` fallback 그대로 유지
- 하위 호환: bot.yaml 변경 없이 동작 (기본값 사용)

## 7. 보안 검토

- A03 Injection: HTML 코멘트 필드 모두 영숫자/하이픈/언더스코어로 정제
- A09 Logging: raw JSON 을 한 번 logger.warning 으로 기록 (500자 제한,
  request_id 추적용)
- 민감 데이터: 기존 markdown 정책과 동일

## Critical Files

- 신규: `src/abyss/upstream_errors.py`, `tests/test_upstream_errors.py`
- 수정: `src/abyss/chat_core.py`, `src/abyss/chat_server.py`,
  `tests/test_chat_core.py`,
  `abysscope/src/components/chat/use-chat-stream.ts`,
  `abysscope/src/components/mobile/__tests__/mobile-route.test.ts`

## Verification

1. `make lint && make test` 통과
2. `cd abysscope && pnpm lint && pnpm test && pnpm build` 통과
3. 단위 테스트로 retry / sanitize 경로 검증
4. `abyss restart` → 일반 채팅 회귀 없음
5. 자연 발생 5xx 시 markdown + UI 확인
