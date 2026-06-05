# Linear

Linear 이슈 트래커 MCP (stdio, personal API token). 이슈 검색·생성·수정·코멘트, 팀/프로젝트/사이클 조회, 우선순위/라벨/할당자 관리.

**Always confirm before creating/updating issues or posting comments.** 생성 전 team·project·title·assignee 확인 후 승인. 상태 전환 전 현재→목표 확인 후 승인. 일괄 수정 금지. 삭제는 사용 안 함 (status를 cancelled / done으로 전환 제안).

## Auth

서버: [`@tacticlaunch/mcp-linear`](https://www.npmjs.com/package/@tacticlaunch/mcp-linear) (stdio, `npx -y`).
인증: 환경변수 **`LINEAR_API_TOKEN`** (Linear → Settings → API → "Create new personal API key").
호스트 Claude Code 플러그인의 OAuth 토큰과는 분리됨 — 봇 subprocess가 OAuth callback listener를 turn 사이 유지 못하므로 personal token 방식만 동작.

## Operations

(도구명은 모두 `linear_*` 접미사. 응답은 한국어로, 필드명은 영어 원문 유지.)

### linear_getViewer / linear_getOrganization
첫 호출 — 본인 계정 + 워크스페이스 확인. "내가 누구로 연결됐어?" 같은 질문에 사용.

### linear_getTeams / linear_getUsers / linear_getLabels / linear_getProjects
워크스페이스 메타. 이슈 생성·검색 전에 team key / assignee ID / label / project ID 매핑할 때 호출.

### linear_getWorkflowStates
팀별 상태 목록 (Backlog / Todo / In Progress / In Review / Done / Cancelled 등). 상태 전환 전 후보 ID 확인.

### linear_getCycles / linear_getActiveCycle / linear_getCycleIssues
스프린트(=cycle) 조회. "이번 스프린트 뭐 남았어?" → `linear_getActiveCycle` → `linear_getCycleIssues`.

### linear_searchIssues — 자연어 + 필터 검색
필터 예시 (서버 spec 따라):
```
team = HEG
assignee = @me
state = "In Progress"
priority >= 2          # Urgent(1) / High(2) / Medium(3) / Low(4) / 0=None
label = "bug"
updated > -7d
text ~ "checkout flow"
```

### linear_getIssues / linear_getIssueById / linear_getIssueHistory
이슈 ID 형식 `<TEAM>-<NUM>` (예: `HEG-7`, `PAY-42`). 사람이 이슈 키 언급하면 먼저 `linear_getIssueById`로 상세 확인.

### linear_getComments
이슈 코멘트 타임라인 — `getIssueById`로 안 보이는 세부 논의 추적.

### linear_createIssue — 생성
필수: team ID, title. 선택: description, assignee, priority, project, labels, parent, cycle, dueDate, estimate.
**반드시 사용자 승인 후 호출.** title이 모호하면 description 보강 제안.

### linear_updateIssue — 수정
이슈 ID + 변경 필드 (상태 전환 포함). 변경 내용을 보여주고 승인 후 실행. 한 번에 여러 이슈 수정 금지 (개별 confirm).

### linear_setIssuePriority / linear_addIssueLabel / linear_removeIssueLabel / linear_assignIssue
부분 업데이트 헬퍼. updateIssue 대신 의도가 명확할 때 사용.

### linear_addIssueToProject / linear_addIssueToCycle / linear_removeIssueFromCycle
이슈 ↔ 프로젝트 / 사이클 매핑.

### linear_createComment
이슈 ID + body. 봇이 자동으로 코멘트 다는 경우는 명시적 사용자 지시가 있을 때만.

### linear_subscribeToIssue
본인을 옵저버로 추가. 알림 받고 싶은 이슈에만.

## Notes

- 이슈 ID 언급되면 먼저 `linear_getIssueById`로 상세 확인 후 사람에게 요약.
- Priority 매핑: 0=None, 1=Urgent, 2=High, 3=Medium, 4=Low.
- 일괄 변경은 항상 개별 confirm. 자동화된 bulk update 금지.
- 토큰이 안 잡혀 있으면 (`LINEAR_API_TOKEN` env var 누락) MCP 호출이 즉시 실패 — 사람한테 토큰 발급 + 환경변수 설정 안내.
