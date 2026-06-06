# Plan: SDK 스트리밍 idle 타임아웃 전환 + 풀 자가치유 (HEG-41)
- date: 2026-06-06
- status: done
- author: claude
- approved-by: (Linear HEG-41 스펙 + "41 진행해" 지시로 갈음)

## 완료 요약
- 비스트리밍 경로(`run_claude_with_sdk`)에도 동일한 `TimeoutError` evict 패치를
  적용(같은 OSError-서브클래스 재-wedge 버그). UI keepalive(#4)는 선택 항목이라
  이번 범위 제외.
- 전체 테스트 1283 passed / 1 skipped, ruff clean.

## 1. 목적 및 배경

단일 턴에서 오래 걸리는 작업(예: iOS 위젯 구현 → repo 탐색 + 의존성 추가 +
테스트 다수 작성)을 시키면 SDK 풀 스트리밍 쿼리가 600초 wall-clock 타임아웃을
초과하고, 해당 세션의 persistent `ClaudeSDKClient`가 wedge 상태가 된다. 이후
모든 메시지가 죽은 풀 클라이언트를 재사용하며 행(hang) → 세션 "먹통". 수동
`/chat/cancel` 또는 데몬 재시작 전까지 복구 불가.

관측(heg-staff / chat_web_011314d78c4f, 2026-06-06 KST):
```
08:24:19 sdk_client ERROR: Pool streaming timed out after 600s
08:24:19 claude_runner WARNING: SDK pool unavailable (streaming), falling back to subprocess
08:25:57 chat_server ERROR: chat failed: Cannot write to closing transport
08:35:57 sdk_client ERROR: Pool streaming timed out after 600s (재발)
```

### 근본 원인 (2가지)
1. `sdk_client.py`의 스트리밍 함수가 **스트림 루프 전체**를
   `asyncio.wait_for(loop, timeout)`로 감쌈 → `timeout`은 턴 전체 wall-clock
   상한이지 idle(무진행) 상한이 아님. 이벤트를 계속 내보내며 작업 중인 agent도
   600초에 죽음.
2. 타임아웃 시 wedge된 클라이언트가 풀에서 **evict되지 않음**. 게다가 코드가
   `raise TimeoutError(...)`(builtin) 하는데 builtin `TimeoutError`는 `OSError`
   서브클래스라, `claude_runner`의 `except (ConnectionError, OSError)` 브랜치가
   먼저 잡아채고 `close_session()`을 호출하지 않음 → 다음 메시지가 죽은 클라
   재사용 → 재-wedge.

## 2. 예상 임팩트
- 영향 모듈: `sdk_client.py`, `claude_runner.py`, `config.py`. (chat_core는
  타임아웃 값 전달만, 시그니처 변경 없음)
- 영향 API: PWA/대시보드 채팅 SSE 스트리밍 경로 (`run_claude_streaming_with_sdk`)
- 성능: 정상 동작 변화 없음. 장시간 작업이 더 이상 조기 종료되지 않음.
- 사용자 경험: 긴 단일 턴 작업 성공률 상승, 먹통 제거.

## 3. 구현 방법 비교

**방법 A — idle(이벤트 간) 타임아웃 + max_total 백스톱** (채택)
- 매 스트림 이벤트마다 리셋되는 `idle_timeout`으로 무진행만 감지. 절대 상한
  `max_total`은 안전 백스톱.
- 장점: 진행 중 작업은 절대 안 죽음, 진짜 hang만 죽음. 스펙과 일치.
- 단점: 수동 `__anext__()` 루프로 변경 필요(코드 약간 복잡).

**방법 B — wall-clock 상한만 600 → 3600으로 상향**
- 장점: 1줄 변경.
- 단점: 1시간 넘는 작업은 여전히 죽음. hang 빠른 감지 불가(최대 3600초 대기).
  근본 해결 아님. → 기각.

**채택 이유**: A만 "진행 중 작업 불사 + hang 신속 감지 + 재-wedge 방지"를 모두
만족.

## 4. 구현 단계
- [x] Step 1: `config.py` — `get_sdk_idle_timeout()`(기본 180),
      `get_sdk_max_total()`(기본 3600) 추가. `config.yaml`의
      `sdk_streaming.{idle_timeout,max_total}` 읽기, 검증/폴백.
- [x] Step 2: `sdk_client.py` — `_consume_stream` 공유 헬퍼 도입.
      `sdk_query_streaming` + `SDKClientPool.query_streaming`을
      `idle_timeout`/`max_total` 파라미터로 교체. 수동 `__anext__()` 루프 +
      이벤트마다 `wait_for(.., idle_timeout)`, 누적시간 `max_total` 검사.
      타임아웃 메시지에 idle/max_total 구분.
- [x] Step 3: `claude_runner.py` — `run_claude_streaming_with_sdk`가 config에서
      idle/max_total 읽어 `pool.query_streaming`에 전달. 전용
      `except TimeoutError`(OSError보다 먼저) → `close_session` 후 subprocess
      fallback. 비스트리밍 경로도 동일 패치.
- [x] Step 4: 테스트 작성 + 기존 회귀 수정.
- [x] Step 5: `ruff check` 통과, `pytest` 전체 통과, plan status=done.

## 5. 테스트 계획
**단위 테스트:**
- [x] (a) async-gen이 idle cap보다 긴 누적시간으로 천천히 yield하지만 idle은 안 함
      → 타임아웃 X (`test_streaming_long_but_progressing_not_killed`)
- [x] (b) async-gen이 침묵 → `idle_timeout`에 `TimeoutError`
      (`test_streaming_idle_timeout_on_silence`, `test_query_streaming_idle_timeout`)
- [x] (c) 계속 yield하지만 `max_total` 초과 → `TimeoutError` 백스톱
      (`test_streaming_max_total_backstop`)
- [x] (d) 풀 스트리밍 `TimeoutError` 시 `close_session(session_key)` 호출 + subprocess
      fallback (`test_run_streaming_with_sdk_timeout_evicts_and_falls_back`)
- [x] (e) `config.get_sdk_idle_timeout/max_total` 기본값 + override + 잘못된 값 폴백
      (test_config 4종)

**통합 테스트:**
- [x] 타임아웃 후 같은 세션에 후속 메시지 → close_session으로 죽은 클라 evict 후
      subprocess fallback 성공(mock 호출 검증).

## 6. 사이드 이펙트
- `sdk_query_streaming`/`query_streaming` 시그니처에서 `timeout` 제거 →
  `idle_timeout`/`max_total`로 교체. 호출부: 프로덕션은 claude_runner 1곳,
  나머지는 테스트. 모두 갱신.
- 하위호환: 내부 함수라 외부 API 영향 없음. config 신규 키는 미설정 시 기본값.
- 마이그레이션: 불필요(기본값으로 동작).

## 7. 보안 검토
- OWASP: 해당 없음(입력 검증/인증/인가 변경 없음).
- 자가치유는 DoS 완화 방향(자기-DoS 세션 먹통 제거).
- 민감 데이터 처리 변경 없음. PCI-DSS 무관.
