# Plan: abysscope `lib/abyss.ts` 도메인 분리

- date: 2026-05-16
- status: approved
- author: claude
- approved-by: user (via `/goal 웹관련 코드 모듈화 및 리팩토링`)

## 1. 목적 및 배경

`abysscope/src/lib/abyss.ts`가 949줄, 40+ exports, 11개 도메인을 한 파일에 담은 god-module이다.
- Config / Bots / Memory / Cron / Skills / Sessions / Conversations / Logs / Status / Metrics / Workspace
- 23개 파일이 이 파일을 import 중
- 신규 기능 추가, 수정 시 cognitive load 큼

목표: 도메인별 모듈로 분리. 외부 API는 동일 (`@/lib/abyss`에서 import 그대로).

## 2. 예상 임팩트

- **영향 모듈**: 23개 importer (API routes + components). 외부 API 그대로 유지하므로 변경 없음
- **성능/가용성**: tree-shaking 이득 가능 (개별 모듈 import 시), 그 외 0
- **사용자 경험**: 변화 없음 (내부 리팩토링)
- **테스트**: `abyss.test.ts` (879줄, 152 cases) 그대로 통과해야 함

## 3. 구현 방법 비교

### A. Barrel re-export (선택)
- `lib/abyss/` 디렉토리 신설, 도메인별 파일 분리
- 기존 `lib/abyss.ts`는 모두 re-export하는 barrel로 변환
- 장점: 호환성 100%, 23개 importer 무수정
- 단점: barrel 자체가 한 줄 더 늘긴 함

### B. 직접 path 변경
- 새 위치로 옮기고 모든 importer 수정
- 장점: 명시적 의존
- 단점: 23개 파일 수정 = diff 폭증, conflict 위험

→ **A 선택**: 안전, 최소 변경, 단계적 후속 마이그레이션 여지

## 4. 구현 단계

- [ ] Step 1: `lib/abyss/` 디렉토리 생성 + 도메인별 파일 11개 분리
  - `paths.ts` — getAbyssHome
  - `config.ts` — GlobalConfig, getConfig, updateConfig
  - `bots.ts` — BotConfig, listBots, getBot, updateBot
  - `memory.ts` — getBotMemory, updateBotMemory, getGlobalMemory, updateGlobalMemory
  - `cron.ts` — CronJob, getCronJobs, updateCronJobs
  - `skills.ts` — SkillConfig, isBuiltinSkill, listSkills, getSkill, createSkill, updateSkill, deleteSkill, getSkillUsageByBots
  - `sessions.ts` — SessionInfo, getBotSessions, deleteSession, deleteConversation, getConversation
  - `logs.ts` — listLogFiles, getLogContent, deleteLogFiles, DaemonLogInfo, getDaemonLogInfo, truncateDaemonLogs
  - `status.ts` — SystemStatus, getSystemStatus, DiskUsage, getDiskUsage
  - `metrics.ts` — ToolMetricEvent, ToolMetricRow, readToolMetricEvents, getToolMetrics, BotConversationFrequency, getConversationFrequency
  - `workspace.ts` — WorkspaceTreeNode, WorkspaceTreeResult, WorkspaceAccessError, listBotWorkspaceTree
- [ ] Step 2: `lib/abyss.ts`를 barrel re-export only로 축소
- [ ] Step 3: `npm test` 152 cases 통과 확인
- [ ] Step 4: `npm run build` 통과 확인
- [ ] Step 5: 커밋 + PR + 머지

## 5. 테스트 계획

**기존 테스트**: 152 cases 모두 그대로 통과 — 테스트가 동작 보장.
- 신규 단위 테스트 추가 없음 (코드 동작 무변경, 위치만 이동)
- `abyss.test.ts`의 import 경로 `@/lib/abyss`도 변경 없음

**통합**:
- [ ] `npm run build` — Next.js 빌드 성공
- [ ] `npm run lint` — eslint 통과

## 6. 사이드 이펙트

- ✅ 외부 API 동일: 23 importers 무영향
- ✅ 테스트 import 동일
- ⚠️ TypeScript 타입 re-export — `export type` 명시 필요 (isolatedModules)
- ⚠️ Class re-export (`WorkspaceAccessError`) — `export {}` 그대로 OK

## 7. 보안 검토

- 동작 변경 없음 → OWASP 영향 없음
- 파일 시스템 access 코드 (workspace, logs, conversation) 그대로
- 인증/인가 변경 없음
- PCI-DSS 영향 없음

## 8. 완료 조건

- [ ] 11개 도메인 파일 생성
- [ ] barrel re-export 완료
- [ ] 152 vitest cases 통과
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과
- [ ] PR 머지

## 9. 후속 (별도 plan)

- `mobile-chat-screen.tsx` (1254줄) sub-component 추출
- `sessions-drawer-panel.tsx` (742줄) 분리
- 23개 importer를 점진적으로 직접 path로 마이그레이션 (선택)
