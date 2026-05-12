# Plan: 대시보드 채팅 헤더에 봇 workspace 파일트리 사이드패널 추가

- date: 2026-05-13
- status: done
- author: claude
- approved-by: ash84

## 1. 목적 및 배경

abysscope 대시보드 채팅에서 활성 세션의 `sessions/chat_<id>/workspace/` 내용을 즉시 들여다볼 수 있는 수단이 없다. Claude가 만든 파일을 확인하려면 Finder를 열거나 별도 페이지를 거쳐야 한다. 채팅 흐름을 끊지 않고 봇이 사이드이펙트로 생성·수정한 파일 구조를 시각적으로 확인할 수 있어야 한다.

요구사항: 채팅 헤더 마이크 버튼 옆에 "디렉토리" 아이콘을 두고, 클릭 시 우측 사이드 패널이 열리면서 현재 세션이 속한 봇의 `workspace/` 디렉토리를 파일트리 형태로 탐색할 수 있어야 한다.

## 2. 예상 임팩트

- **영향 모듈**:
  - `abysscope/src/components/chat/chat-view.tsx` — 헤더 버튼 추가, 사이드 패널 토글 상태
  - `abysscope/src/components/chat/workspace-tree.tsx` (신규) — 파일트리 UI
  - `abysscope/src/app/api/chat/workspace/route.ts` (신규) — workspace 디렉토리 트리 조회 API
  - `abysscope/src/lib/abyss.ts` — `listBotWorkspaceTree(bot, sessionId)` 헬퍼 추가
- **API**: 새 GET 엔드포인트 `/api/chat/workspace?bot=<name>&session=<chat_id>&path=<rel>` 추가. 기존 API 변경 없음
- **성능/가용성**: 파일 시스템 읽기만, 채팅 SSE 스트림과 무관. 트리는 lazy expand로 처음에는 1depth만 fetch
- **사용자 경험**: 채팅 헤더에 디렉토리 아이콘 1개 추가, 음성 모드 사이드 패널과 동일한 폭(`w-72`)·테마의 패널이 우측에서 슬라이드. 음성 모드와 동시 표시 가능 여부는 §3에서 결정

## 3. 구현 방법 비교

### 방법 A — Voice 패턴 그대로 우측 aside 1개로, 음성/파일트리 상호 배타

- chat-view에 `voiceMode` 옆에 `workspaceOpen` 상태를 두고, 둘 중 하나만 열리도록 한다.
- 장점: 레이아웃 단순, 좁은 디스플레이에서도 컨텐츠 면적 보존
- 단점: 음성 모드 사용 중 파일 확인 불가 → "음성으로 질문하면서 결과 파일 확인" 같은 시나리오 못 함

### 방법 B — 별도 aside 2개를 동시 표시 (voice 옆에 workspace 추가)

- 음성 + 워크스페이스 동시 표시. 본문은 더 좁아짐
- 장점: 음성 모드 중에도 파일 확인 가능
- 단점: 본문이 매우 좁아져 채팅 가독성 저하. 1280px 미만에서 깨질 수 있음

### 방법 C — 별도 사이드 패널이 아닌 모달/Dialog로 트리 표시

- 장점: 레이아웃 영향 없음
- 단점: 채팅과 동시에 보기 어려움. 요구사항 "우측에서 나오게"와 부합 안 함

### 선택: 방법 A

요구사항이 우측 사이드 패널을 명시했고, 음성 모드와 파일 탐색은 서로 다른 흐름이라 동시 사용 빈도가 낮다. 좁은 화면에서 본문이 부서지는 것을 피하기 위해 상호 배타로 둔다. 향후 데스크탑 와이드(≥1536px)에 한해 방법 B로 확장 가능.

## 4. 구현 단계

- [x] **Step 1**: `abysscope/src/lib/abyss.ts`에 `listBotWorkspaceTree(bot: string, sessionId: string, relativePath: string = "")` 추가
  - 반환: `{ name, path, type: "file"|"dir", size?: number, mtime: string, children?: TreeNode[] }`
  - 보안: `path.resolve` 후 `abyssHome/bots/<bot>/sessions/chat_<sessionId>/workspace` 루트 밖이면 throw
  - lazy: depth 1만 children 채움. 디렉토리 children 없을 때는 빈 배열 vs 미로드 구분 위해 `children: undefined` 사용
- [x] **Step 2**: `abysscope/src/app/api/chat/workspace/route.ts` GET 라우트 추가
  - query: `bot`, `session`, `path?` 모두 검증
  - 응답: `{ root: string, tree: TreeNode[] }` 또는 워크스페이스 없을 시 `{ root, tree: [], missing: true }`
  - 404: 봇 또는 세션이 없을 때
- [x] **Step 3**: `abysscope/src/components/chat/workspace-tree.tsx` 신규 컴포넌트
  - props: `bot: string`, `sessionId: string`, `onClose: () => void`
  - 상태: `tree`, `expanded: Set<string>`, `loading: Set<string>`, `error`
  - 디렉토리 클릭 시 lazy fetch (캐시 with `expanded`). 파일 클릭 시 동작 없음(향후 미리보기 확장 여지)
  - 헤더에 새로고침 버튼 + 닫기 버튼(`X`). "Open in Finder" 링크는 기존 `path-link.tsx`와 `/api/open-finder` 재사용
  - 아이콘: `Folder`, `FolderOpen`, `File`, `FileCode`(.py/.ts/.tsx) — lucide-react
- [x] **Step 4**: `chat-view.tsx` 헤더 수정
  - Mic 버튼 왼쪽에 `<Button>` + `<FolderTree />` 아이콘 추가, `title="작업 디렉토리 보기"`, `aria-label="작업 디렉토리 사이드 패널 토글"`
  - 상태 `workspaceOpen` 추가. 클릭 핸들러에서 `voiceMode`면 `handleVoiceClose()` 호출 후 open (상호 배타)
  - 사이드 패널 렌더: `workspaceOpen && activeSession && !voiceMode`일 때 `<aside className="w-72 shrink-0 border-l bg-background"><WorkspaceTree .../></aside>`
- [x] **Step 5**: 비활성 상태 처리
  - 세션 없을 때 디렉토리 버튼 `disabled`
  - 활성 세션 변경 시 `workspaceOpen` 유지하되 트리는 새 세션으로 refetch (workspace-tree 내부 `useEffect`의 deps에 `bot, sessionId`)
- [x] **Step 6**: 폴더/파일 정렬 규칙
  - dir 먼저, 그 다음 file. 각각 이름 오름차순. 숨김(점으로 시작) 항목 표시 (Claude가 만든 `.claude_session_id` 등 디버깅 필요)

## 5. 테스트 계획

**단위 테스트** (`abysscope/src/lib/__tests__/abyss.workspace.test.ts`):
- [x] 케이스 1: 정상 workspace 디렉토리 트리 반환 (tmp 디렉토리에 fixture 생성)
- [x] 케이스 2: workspace 없는 세션 → `missing: true` 또는 빈 배열
- [x] 케이스 3: relativePath에 `..` 포함 시 throw (path traversal 차단)
- [x] 케이스 4: relativePath가 심볼릭 링크로 abyss home 밖을 가리킬 때 throw (realpath 검증)
- [x] 케이스 5: 디렉토리 정렬 — dir 먼저, 이름 오름차순
- [x] 케이스 6: lazy depth=1 — 중첩 디렉토리는 `children: undefined`

**API 테스트** (`abysscope/src/app/api/chat/workspace/__tests__/route.test.ts`):
- [x] 시나리오 1: 정상 GET 200 반환
- [x] 시나리오 2: 봇 없음 → 404
- [x] 시나리오 3: 세션 없음 → 404
- [x] 시나리오 4: path traversal 시도 → 403
- [x] 시나리오 5: bot/session 파라미터 누락 → 400

**컴포넌트 테스트** (`abysscope/src/components/chat/__tests__/workspace-tree.test.ts`, 소스 레벨 가드 — vitest 환경이 node-only라 RTL 대신 `ui-regression.test.ts` 패턴 채택):
- [x] WorkspaceTree가 bot/sessionId 변경 시 재요청하는 deps 유지
- [x] 디렉토리 lazy fetch 경로 (fetchTree(bot, sessionId, key))
- [x] onClose 버튼 연결
- [x] Finder 연동 (/api/open-finder)
- [x] /api/chat/workspace 쿼리 파라미터 (bot/session/path)
- [x] ChatView가 WorkspaceTree import 및 FolderTree 버튼 렌더
- [x] voiceMode와 상호 배타 렌더링 (`workspaceOpen && !voiceMode`)

**수동 통합** (사용자 확인 필요):
- [ ] `abyss dashboard restart` 후 채팅에서 디렉토리 버튼 → 우측 패널 슬라이드
- [ ] Claude에게 파일 생성 요청 → 새로고침 버튼으로 트리 갱신 확인
- [ ] 음성 모드 켠 상태에서 디렉토리 버튼 누르면 음성 종료되고 워크스페이스 패널 열림 (반대도 확인)

## 6. 사이드 이펙트

- **기존 음성 모드**: 디렉토리 버튼 누를 때 자동으로 음성 종료됨. 명시적 동작이므로 회귀 아님
- **하위 호환성**: 신규 API라 기존 클라이언트 영향 없음
- **마이그레이션**: 불필요. 빈 workspace 디렉토리는 정상 처리
- **번들 크기**: lucide-react `FolderTree`, `FolderOpen` 아이콘 추가 — 미미함
- **CLAUDE.md / 문서**: `CLAUDE.md` Abysscope 섹션에 한 줄 추가 ("Workspace tree: chat 헤더의 디렉토리 아이콘으로 활성 세션 workspace 탐색")

## 7. 보안 검토

- **A01 (접근 제어)**: workspace 경로는 항상 `abyssHome/bots/<bot>/sessions/chat_<sessionId>/workspace` 하위만 허용. `path.resolve` 후 `startsWith(workspaceRoot)` 검사
- **A03 (인젝션)**: `bot`, `session`, `path` 파라미터에 `..`, 절대경로, NUL 바이트 차단. shell exec 안 함(순수 fs 호출)
- **심볼릭 링크**: `fs.realpathSync`로 실제 경로 검증해 외부 디렉토리로 빠지지 않게 한다
- **인증/인가**: 대시보드 자체가 로컬 바인딩이라 인증 레이어 변경 없음. 기존 origin 허용 정책 그대로
- **민감 데이터**: workspace에 토큰/시크릿이 들어있을 가능성 있음 → 트리 표시는 메타데이터(이름/크기/mtime)만, 파일 내용 조회 API는 본 plan 범위 밖 (다음 PR에서 별도 plan으로 진행)
- **PCI-DSS**: 해당 없음

## 8. 미해결 결정 사항

- 파일 다운로드/미리보기는 본 plan 범위 밖 → 후속 plan 필요 시 분리
- group 세션(`groups/<name>/workspace/`) 지원 여부 → 본 plan은 봇 단일 세션만, group 지원은 후속
