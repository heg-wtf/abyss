# Plan: Dashboard Frequency Heatmap

- date: 2026-04-29
- status: draft
- author: claude
- approved-by:

---

## 1. 목적 및 배경

Dashboard 첫 화면에 봇별 대화 빈도를 GitHub Contribution Graph 스타일 히트맵으로 시각화한다.
사용자가 각 봇과 얼마나 자주 대화했는지 한눈에 파악할 수 있게 한다.

섹션명: **Frequency**

---

## 2. 예상 임팩트

- 영향 범위: `abysscope/src/app/page.tsx`, `abysscope/src/lib/abyss.ts`, 신규 컴포넌트 1개
- 성능: 서버 컴포넌트에서 파일 읽기 — 봇 7개 × 파일 최대 365개, 빠름
- 사용자 경험: Dashboard에 Frequency 섹션 추가 (Disk Breakdown 위)

---

## 3. 구현 방법 비교

### A. 외부 라이브러리 (`react-calendar-heatmap`)
- 장점: 빠른 구현, 툴팁 포함
- 단점: 클라이언트 컴포넌트 필요, 추가 의존성, 스타일 커스터마이징 복잡

### B. 순수 Tailwind CSS 커스텀 컴포넌트 ✅ 선택
- 장점: 의존성 없음, 서버 컴포넌트 유지, Tailwind 색상 완전 제어
- 단점: 구현 코드 약간 더 많음

**선택 이유**: 의존성 최소화, 서버 컴포넌트 유지 가능, 기존 스타일 일관성

---

## 4. 데이터 구조

### 소스
`~/.abyss/bots/<name>/sessions/chat_<id>/conversation-YYMMDD.md`

### 날짜 파싱
파일명 `conversation-260224.md` → `YYMMDD` → `2026-02-24`

### 카운트 기준
파일 내 `## user` 헤더 수 = 해당 날 유저 메시지 수

### 집계 단위
**전체 봇 합산** (날짜 → 총 메시지 수) + **봇별 날짜 → 메시지 수**
→ 봇별로 각각 히트맵 1줄씩 표시 (GitHub contribution graph 스타일)

---

## 5. 구현 단계

- [ ] Step 1: `lib/abyss.ts`에 `getConversationFrequency()` 추가
  - 반환 타입: `{ botName: string; displayName: string; data: Record<string, number> }[]`
  - 각 봇의 날짜별 `## user` 카운트 집계
  - 최근 365일 범위만 포함

- [ ] Step 2: `components/conversation-heatmap.tsx` 서버 컴포넌트 작성
  - Props: `data: Record<string, number>`, `label: string`
  - 52주 × 7일 그리드
  - 색상 5단계: 0 / 1-2 / 3-5 / 6-10 / 11+
  - 월 레이블 (상단), 요일 레이블 Mon/Wed/Fri (좌측)
  - hover title에 날짜 + 횟수 표시 (`title` attribute)

- [ ] Step 3: `page.tsx`에 Frequency 섹션 추가
  - Disk Breakdown 위에 배치
  - 봇별 히트맵 나열
  - 각 봇 이름 + 총 대화 수 표시

---

## 6. 테스트 계획

**단위 테스트 (`tests/test_abyss_ts.ts` 없으므로 수동 검증):**
- [ ] 케이스 1: 대화 파일 없는 봇 → 빈 히트맵 렌더링 (에러 없음)
- [ ] 케이스 2: 파일명이 `YYMMDD` 형식이 아닌 파일 → 무시
- [ ] 케이스 3: 365일 이전 파일 → 결과에 포함 안 됨

**통합 테스트:**
- [ ] 시나리오 1: 대시보드 로드 → Frequency 섹션이 Disk Breakdown 위에 표시됨
- [ ] 시나리오 2: 각 봇의 히트맵이 실제 파일 수와 일치하는지 확인
- [ ] 시나리오 3: `next build` 성공

---

## 7. 사이드 이펙트

- 기존 기능 영향: 없음 (읽기 전용)
- 하위 호환성: 해당 없음
- 마이그레이션: 해당 없음

---

## 8. 보안 검토

- 파일 경로: `abyss_home()` 헬퍼 사용, path traversal 없음
- 인증/인가 변경: 없음
- 민감 데이터: 대화 내용 미표시, 카운트 수치만 노출
- PCI-DSS: 해당 없음
