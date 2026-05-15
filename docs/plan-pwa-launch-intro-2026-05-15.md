# Plan: PWA First-Run Launch Intro Animation

- date: 2026-05-15
- status: in-progress
- author: claude
- approved-by: ash84

## Context

PWA 첫 실행 시 시스템 splash (`background_color: #131313`) 만 보이고 인앱
런치 애니메이션이 없음. 사용자가 예시 이미지(중심에서 폭발하는 큐브 입자
+ 강한 chromatic aberration + 스캔라인) 같은 임팩트 있는 인트로를 요청.

PWA 처음 실행 1회만, 1.5초 지속, 탭하면 즉시 스킵, PWA standalone +
일반 브라우저 모두 동일 적용.

## 1. 목적

- 첫 실행 임팩트 (브랜드 톤 환기)
- 처음 한 번만 → localStorage flag
- 가속 GPU 셰이더로 동적 효과 (영상 자산 불필요)

## 2. 임팩트

- 영향 파일:
  - 신규: `abysscope/src/components/mobile/launch-intro.tsx`
  - 수정: `abysscope/src/components/mobile/mobile-shell.tsx` (인트로
    오버레이 마운트)
  - 수정 (테스트): `abysscope/src/components/mobile/__tests__/mobile-route.test.ts`
- 정상 동작 영향 없음 (인트로는 1회 + 1.5s + tap skip)
- 번들 크기: ~3KB (셰이더 문자열 + 부트스트랩)

## 3. 구현 방법 (B 선택)

WebGL 1.0 fragment shader 풀스크린 quad. 보일러플레이트:
- vertex: 풀스크린 quad
- fragment: 시간 기반 큐브 보로노이 + 중심 가우시안 burst + 방사형
  RGB shift (chromatic aberration) + 수평 스캔라인

진입 시점 분기 (`MobileShell`):
1. mount 시 `localStorage.getItem("abyss_pwa_intro_seen")` 확인
2. 미설정 → `<LaunchIntro>` 풀스크린 오버레이 (z-[100])
3. 1.5s 자동 완료 또는 사용자 탭 → setItem + state flip → 언마운트
4. `prefers-reduced-motion: reduce` 면 즉시 완료 (animation skip)

SSR-safe: initial state = "intro hidden", `useEffect` 안에서 localStorage
조회 후 flag. Hydration mismatch 없음.

대안:
- A (MP4): 영상 자산 별도 제작 필요 → 미선택
- C (CSS only): 이미지 톤 재현 어려움 → 미선택

## 4. 구현 단계

- [x] Step 0: 브랜치 + plan doc
- [ ] Step 1: `launch-intro.tsx` — WebGL setup, shader, RAF loop,
      auto-complete, tap-to-skip, reduced-motion fallback
- [ ] Step 2: `mobile-shell.tsx` 와이어링 — localStorage flag, intro
      상태, onComplete 핸들러
- [ ] Step 3: source-regex 가드 `mobile-route.test.ts`
- [ ] Step 4: `pnpm lint && pnpm test && pnpm build`
- [ ] Step 5: commit + PR

## 5. 테스트 계획

### 단위 (source-regex)
- [ ] LaunchIntro 가 WebGL context 획득 + RAF 루프 + onComplete
- [ ] MobileShell 가 localStorage 키 + LaunchIntro import + 조건부 렌더
- [ ] prefers-reduced-motion 처리 존재

### 수동
- [ ] PWA 첫 실행 → 인트로 1.5s 후 자동 종료 → 채팅 화면
- [ ] 새로고침/재진입 → 인트로 안 뜸 (1회만)
- [ ] 탭으로 즉시 스킵
- [ ] localStorage 삭제 후 재실행 → 인트로 다시 뜸 (수동 리셋)
- [ ] iOS Safari + Android Chrome 모두 동작

## 6. 사이드 이펙트

- localStorage 키 추가: `abyss_pwa_intro_seen`
- 첫 진입 1.5s 동안 mobile UI 가려짐 (스킵 가능)
- 정상 UX 흐름에 영향 없음
- 사용자 디버깅용 리셋: devtools 에서 localStorage 항목 삭제

## 7. 보안 검토

- 추가 입력 / 외부 요청 없음
- WebGL context — 일반 사용 (셰이더 텍스처 업로드 없음)
- 비해당: A01–A10

## Critical Files

- 신규: `abysscope/src/components/mobile/launch-intro.tsx`
- 수정: `abysscope/src/components/mobile/mobile-shell.tsx`
- 수정: `abysscope/src/components/mobile/__tests__/mobile-route.test.ts`

## Verification

1. `cd abysscope && pnpm lint && pnpm test && pnpm build` 통과
2. `abyss restart`
3. localStorage 비운 PWA 첫 진입 → 인트로 확인
4. 두 번째 진입 → 인트로 없음
