# Plan: Dashboard 부팅 시 Google Fonts fetch 실패로 미기동되는 문제 수정
- date: 2026-06-01
- status: approved
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

맥 부팅 후 launchd가 `com.abyss.daemon`(KeepAlive=true)을 자동 실행할 때, 네트워크가 완전히 준비되지 않은 시점에 `abysscope` Next.js 빌드가 `Geist_Mono` Google Fonts fetch에 실패하여 dashboard subprocess가 기동되지 않는 문제. Daemon(API/cron/heartbeat)은 정상 동작하지만 사용자는 dashboard에 접근할 수 없다.

증거:
- `~/.abyss/logs/dashboard-build-20260530-232003.log`, `dashboard-build-20260530-082018.log`: 동일한 `next/font: error: Failed to fetch Geist Mono from Google Fonts` 에러.
- `bot_manager.py:217` — 빌드 실패는 단순 로그만 남기고 dashboard_handle=None. 재시도 로직 없음.

## 2. 예상 임팩트

- **영향 모듈**: `abysscope/src/app/layout.tsx`, `src/abyss/dashboard.py`, `src/abyss/bot_manager.py`
- **빌드 산출물**: Geist Mono woff2 파일 1개를 `abysscope/src/app/fonts/`에 추가 (~30-50KB)
- **성능/가용성**: 빌드 시 외부 네트워크 의존 제거 → 빌드 성공률 향상, 빌드 시간 단축 (수십~수백 ms)
- **사용자 경험**: 부팅 시 dashboard 누락 사라짐. 폰트 시각적 변화 없음

## 3. 구현 방법 비교

### 방법 A: Geist Mono self-host (근본 해결)
- 장점: 빌드 시 외부 네트워크 의존 완전 제거. Pretendard와 동일 패턴(`next/font/local`)
- 단점: woff2 파일 저장소에 포함 (~30-50KB), 폰트 업데이트 시 수동 갱신 필요

### 방법 B: Dashboard 빌드 재시도 (방어막)
- 장점: 추후 다른 외부 의존성 발생 시 자동 복구. 부팅 시 일시적 네트워크 문제 흡수
- 단점: 근본 원인 해결 아님. 재시도 동안 dashboard 시작 지연

### 방법 C: Geist Mono 제거 후 Pretendard 단일화
- 장점: 의존성 가장 적음
- 단점: 코드 블록 모노스페이스 시각 일관성 손실. UI 회귀

**선택: A + B 동시 적용.** A로 근본 원인을 제거하고, B로 향후 유사 이슈(다른 CDN 의존성 등)에 대한 방어막 확보.

## 4. 구현 단계

- [ ] Step 1: Geist Mono woff2 파일 다운로드 → `abysscope/src/app/fonts/GeistMono.woff2`로 저장 (Variable weight)
- [ ] Step 2: `abysscope/src/app/layout.tsx` 수정 — `next/font/google` import 제거, `localFont`로 Geist Mono 정의. `--font-geist-mono` CSS 변수 유지
- [ ] Step 3: 로컬 빌드 검증 — 네트워크 차단 상태로 `npx next build` 성공 확인
- [ ] Step 4: `src/abyss/dashboard.py`에 retryable build helper 추가 — `build_and_start_with_retry(max_attempts, backoff_seconds)` 또는 `build_and_start` 내부 재시도
- [ ] Step 5: `src/abyss/bot_manager.py` — 빌드 실패 시 backoff 재시도 호출
- [ ] Step 6: 단위 테스트 — retry 로직 (빌드 실패 N회 후 성공/최종 실패 시나리오)
- [ ] Step 7: 통합 테스트 — Geist Mono local 폰트로 빌드 성공 (CI 빌드 통과)
- [ ] Step 8: `make lint && make test` (또는 `uv run ruff check && uv run pytest`) 통과
- [ ] Step 9: 커밋 + PR 작성
- [ ] Step 10: 머지 후 launchd 재시작 검증 (`launchctl unload/load` + 빌드 로그 확인)

## 5. 테스트 계획

**단위 테스트:**
- [ ] 케이스 1: `build_and_start` 1회 실패 후 2회차 성공 (mock subprocess returncode 1 → 0)
- [ ] 케이스 2: `build_and_start` max_attempts만큼 모두 실패 시 RuntimeError raise
- [ ] 케이스 3: backoff 대기 시간이 의도대로 적용되는지 (mock sleep)

**통합 테스트:**
- [ ] 시나리오 1: 로컬에서 `cd abysscope && npm run build` 네트워크 차단 상태 성공
- [ ] 시나리오 2: 전체 `uv run pytest` 통과 (회귀 없음)
- [ ] 시나리오 3: 빌드된 dashboard에서 `Geist_Mono` 클래스가 정상 적용 (DOM에 `--font-geist-mono` 변수 확인)

## 6. 사이드 이펙트

- **하위 호환성**: 폰트 시각적 변화 없음 (동일 폰트 파일). 변수명 동일 → CSS 회귀 없음
- **번들 크기**: woff2 1개 (~30-50KB) 정적 자산 추가. 기존 Next.js 자동 폰트 fetch 캐시는 사라지지만 영구 캐시로 대체
- **마이그레이션**: 불필요. 빌드 시 자동 적용
- **빌드 시간**: 약간 단축 (외부 fetch 제거)

## 7. 보안 검토

- **OWASP Top 10**: A06 (Vulnerable Components) — 폰트 파일은 정적 자산. 신뢰할 수 있는 출처(Vercel 공식 GitHub `vercel/geist-font`)에서 다운로드
- **인증/인가**: 변경 없음
- **민감 데이터**: 변경 없음
- **PCI-DSS**: 해당 없음
- **공급망 리스크**: woff2 파일은 일회성 다운로드 후 저장소 포함. SHA256으로 검증 가능

## 8. 완료 조건

- [ ] 모든 구현 단계 체크 완료
- [ ] 모든 테스트 통과
- [ ] `uv run ruff check . && uv run pytest` 통과
- [ ] abysscope `npm run lint && npx tsc --noEmit` 통과
- [ ] 네트워크 차단 상태 `npx next build` 성공 확인
- [ ] PR 생성
