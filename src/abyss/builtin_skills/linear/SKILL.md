# Linear

Linear 이슈 트래커 공식 MCP (OAuth). 이슈 검색·생성·수정, 코멘트, 워크스페이스 메타 조회.

**Always confirm before creating/updating issues or posting comments.** 생성 전 team·project·title·assignee 확인 후 승인. 상태 전환 전 현재→목표 확인 후 승인. 일괄 수정 금지. 삭제는 사용 안 함 (status를 cancelled / done으로 전환 제안).

## Auth

첫 사용 시 호스트 Claude Code가 브라우저로 Linear OAuth 동의 화면을 띄움. 이후 토큰은 호스트 `~/.claude/`에 저장되어 봇 세션이 그대로 재사용. 별도 env 변수 / API key 불필요.

## Operations

### list_teams / list_projects / list_users
이슈를 만들거나 검색하기 전에 팀·프로젝트·할당자 식별. 사람이 “PayHere 이슈” 식으로 말하면 먼저 list_teams로 team ID 확인.

### list_workflow_states
팀별 상태 목록 (Backlog / Todo / In Progress / In Review / Done / Cancelled 등). 상태 전환 전 후보 상태 ID 확인.

### list_issue_labels / list_cycles
라벨 / 사이클(스프린트) 매핑.

### search_issues — 자연어 검색
필터 예시:
```
team = PAY                        # 팀 키
assignee = @me                    # 본인
state = "In Progress"
priority >= 2                     # Urgent(1) / High(2) / Med(3) / Low(4)
label = "bug"
updated > -7d
text ~ "checkout flow"
```

### list_my_issues — 나에게 할당된 이슈
가장 자주 쓰는 메서드. 본인 워크로드 요약 / 데일리 스탠드업 준비용.

### get_issue
이슈 ID (예: `PAY-123`) → title, description, status, assignee, labels, comments, child issues.

### create_issue — 생성
필수: team ID, title. 선택: description, assignee, priority, project, labels, parent, due date, estimate.
**반드시 사용자 승인 후 호출.** title이 모호하면 description 보강 제안.

### update_issue — 수정
이슈 ID + 변경 필드 (상태 전환 포함). 변경 내용을 보여주고 승인 후 실행. 한 번에 여러 이슈 수정 금지 (개별 confirm).

### create_comment — 코멘트
이슈 ID + body. 봇이 자동으로 코멘트 다는 경우는 명시적 사용자 지시가 있을 때만.

### list_comments
이슈 코멘트 타임라인 — get_issue로 안 보이는 세부 논의 추적.

## Notes

- 이슈 ID 언급되면 먼저 `get_issue`로 상세 확인 후 사람에게 요약.
- Linear 이슈 키는 `<TEAM>-<NUM>` (예: `ENG-42`, `PAY-7`).
- 응답은 한국어, 이슈 본문 인용 / 필드명은 영어 원문 유지.
- Priority 매핑: 1=Urgent, 2=High, 3=Medium, 4=Low (0=No priority).
