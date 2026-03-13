# Group Mission: Multi-Bot Collaboration

> Plan created: 2026-03-13
> Branch: TBD

## Overview

Telegram 그룹에 여러 cclaw 봇을 초대하고, orchestrator 봇이 미션을 분해/위임/종합하는 협업 시스템. 사장님(유저)은 그룹에 미션만 던지고, 부서장(orchestrator)이 알아서 팀원(member)에게 분배한다.

## Problem

현재 cclaw 봇은 완전히 독립적으로 동작한다:
- 같은 그룹에 3개 봇이 있으면 3개가 동시에 각자 응답
- 봇 간 인지, 조율, 결과 공유 메커니즘이 없음
- 복잡한 미션을 하나의 봇에게 모두 맡겨야 함

## Solution

**조직 비유:**
- 유저 = 사장님
- Telegram 그룹 = 부서
- Orchestrator 봇 = 부서장
- Member 봇들 = 팀원

사장님이 그룹에 미션을 던지면 부서장이 분석, 분해, @멘션으로 위임, 결과 종합까지 처리한다.

## 설계 원칙

1. **봇은 그냥 봇이다** -- `bot.yaml`에 specialty 같은 그룹 전용 필드를 추가하지 않는다. 기존 `personality`, `role`, `goal`로 충분하다
2. **역할은 그룹에서 정해진다** -- 같은 봇이 A 그룹에서는 member, B 그룹에서는 orchestrator일 수 있다
3. **개인비서와 팀원은 겸직** -- 1:1 DM에서는 개인비서, 그룹에서는 팀원/부서장으로 동시에 동작한다
4. **mission.yaml 없음** -- 미션 상태는 orchestrator의 Claude 세션이 관리한다. 파일로 중복 추적하지 않는다
5. **CLAUDE.md는 자동 생성** -- 그룹 컨텍스트도 `compose_claude_md()`가 자동으로 조립한다
6. **Orchestrator는 먼저 질문한다** -- 사장님의 요구사항이 모호하면 바로 태스크를 분해하지 않고, 먼저 명확화 질문을 던진다. 이것은 모든 orchestrator의 기본 소양이다

## 조직 구조

```
사장님 (User)
|
+-- 개발부서 (Telegram Group A)
|   +-- dev_lead (orchestrator)
|   +-- coder (member)
|   +-- tester (member)
|
+-- 리서치부서 (Telegram Group B)
|   +-- analyst (orchestrator)
|   +-- searcher (member)
|   +-- coder (member)          <-- 개발부서와 겸직
|
+-- 개인비서 (1:1 DM)
    +-- coder                   <-- 그룹과 별개로 개인비서 역할
    +-- dev_lead
    +-- ...
```

## 데이터 구조

### 디렉토리

```
~/.cclaw/
+-- config.yaml
+-- bots/
|   +-- dev_lead/
|   |   +-- bot.yaml              # 기존 그대로 (변경 없음)
|   |   +-- MEMORY.md             # DM + 그룹 모두에서 축적
|   |   +-- sessions/
|   |       +-- chat_111/         # 1:1 DM (개인비서)
|   |       +-- chat_-12345/      # dev_team 그룹 (orchestrator)
|   +-- coder/
|   |   +-- bot.yaml
|   |   +-- MEMORY.md
|   |   +-- sessions/
|   |       +-- chat_222/         # 1:1 DM (개인비서)
|   |       +-- chat_-12345/      # dev_team 그룹 (member)
|   |       +-- chat_-67890/      # infra_team 그룹 (orchestrator!)
|   +-- tester/
|       +-- bot.yaml
|       +-- sessions/
|           +-- chat_-12345/      # dev_team 그룹 (member)
|
+-- groups/
    +-- dev_team/
    |   +-- group.yaml            # 역할 매핑
    |   +-- conversation/         # 공유 대화 로그
    |   |   +-- 260313.md
    |   +-- workspace/            # 공유 작업 결과물
    |       +-- scraper.py        # coder가 작성
    |       +-- test_scraper.py   # tester가 작성
    +-- infra_team/
        +-- group.yaml
        +-- conversation/
        +-- workspace/
```

### group.yaml

```yaml
name: dev_team
telegram_chat_id: null         # /bind 시 자동 기록
orchestrator: dev_lead
members:
  - coder
  - tester
created_at: 2026-03-13
```

역할 매핑만 담는다. 각 봇의 능력은 해당 봇의 `bot.yaml`에서 읽는다.

### 공유 Workspace

Flat 구조. 봇별 서브디렉토리 없이 한 폴더에 모든 결과물을 저장한다.

```
groups/dev_team/workspace/
+-- scraper.py            # coder가 작성
+-- test_scraper.py       # tester가 작성
+-- requirements.txt      # coder가 작성
```

모든 봇이 이 디렉토리를 읽고 쓸 수 있다. tester가 coder의 scraper.py를 직접 읽어서 테스트를 작성한다.

### 병렬 태스크 실행

Orchestrator가 여러 member에게 동시에 태스크를 위임할 수 있다. 각 봇의 Claude 호출은 독립적인 프로세스이므로 병렬 실행에 문제없다.

```
dev_lead: "@coder_bot 크롤러 작성해줘. @researcher_bot 쿠팡 API 문서 조사해줘."
  |
  +-- coder: Claude 호출 (비동기)
  +-- researcher: Claude 호출 (비동기)   <- 동시 진행
```

### bot.yaml (변경 없음)

```yaml
telegram_token: "..."
telegram_username: "coder_bot"
display_name: "코더"
personality: "꼼꼼한 시니어 개발자"
role: "코드 작성과 리뷰"
goal: "깨끗하고 동작하는 코드를 만든다"
model: sonnet
streaming: true
skills: [...]
```

그룹 관련 필드는 추가하지 않는다.

## 셋업 흐름

```
Step 1: 봇 만들기 (기존 기능)
  cclaw bot add coder
  cclaw bot add tester
  cclaw bot add dev_lead

Step 2: 그룹 만들기 (신규 CLI)
  cclaw group create dev_team \
    --orchestrator dev_lead \
    --members coder,tester

  -> ~/.cclaw/groups/dev_team/group.yaml 생성
  -> telegram_chat_id는 아직 null

Step 3: Telegram 그룹 생성 + 봇 초대
  사장님이 Telegram에서:
  1. "개발부서" 그룹 생성
  2. @dev_lead_bot, @coder_bot, @tester_bot 초대
  3. BotFather에서 각 봇의 Privacy Mode 비활성화

Step 4: 바인딩 (그룹방에서)
  사장님이 그룹방에서: /bind dev_team

  -> dev_lead가 수신 (모든 봇이 수신하지만 orchestrator만 처리)
  -> config.yaml에서 "dev_team" 그룹 설정 확인
  -> 현재 chat_id를 group.yaml에 기록
  -> getChatMember API로 멤버 전원 재석 확인
  -> 그룹에 안내 메시지 전송
```

### /bind 처리 로직

```
/bind dev_team 수신
  |
  +-- 모든 봇이 수신
  |
  +-- 각 봇: "내가 dev_team의 orchestrator인가?"
  |   +-- dev_lead: YES -> 처리 진행
  |   +-- coder: NO -> 무시
  |   +-- tester: NO -> 무시
  |
  +-- dev_lead가 처리:
      1. groups/dev_team/group.yaml 로드
      2. telegram_chat_id 기록
      3. getChatMember(chat_id, coder_bot_id) -> 확인
      4. getChatMember(chat_id, tester_bot_id) -> 확인
      5. 그룹 메시지: "개발부서 활성화. Orchestrator: @dev_lead_bot, Members: @coder_bot, @tester_bot"
```

## 메시지 흐름

### 요구사항 명확화 흐름

Orchestrator의 기본 소양: 모호한 미션은 바로 분해하지 않고 먼저 질문한다.

```
사장님: "쇼핑몰 크롤러 만들어줘"
  |
  +-- dev_lead (orchestrator) 수신
  |   +-- Claude가 판단: 요구사항이 충분한가?
  |   +-- 부족하다고 판단
  |   +-- 응답: "몇 가지 확인이 필요합니다.
  |             1. 어떤 쇼핑몰인가요? (쿠팡, 네이버, 특정 사이트?)
  |             2. 어떤 데이터를 수집할까요? (상품명, 가격, 리뷰, 이미지?)
  |             3. 결과 형식은? (CSV, JSON, DB 저장?)
  |             4. 테스트도 필요한가요?"
  |
  +-- 사장님: "쿠팡. 상품명이랑 가격. CSV로. 테스트도."
  |
  +-- dev_lead 수신
      +-- Claude가 판단: 이제 충분하다
      +-- 태스크 분해 시작
      +-- 응답: "미션 접수. 2개 태스크로 분해.
                @coder_bot 쿠팡 상품 크롤러 작성. 상품명+가격 수집, CSV 출력.
                @tester_bot 크롤러 완성 후 pytest 작성."
```

반대로, 요구사항이 명확하면 바로 진행한다:

```
사장님: "쿠팡에서 노트북 카테고리 상품명/가격을 CSV로 크롤링해줘. 테스트도."
  |
  +-- dev_lead 수신
      +-- Claude가 판단: 충분히 명확하다
      +-- 바로 태스크 분해 (질문 없이)
```

### 미션 실행 흐름

```
사장님: "쇼핑몰 상품 크롤러 만들어줘. 테스트도."
  |
  +-- dev_lead (orchestrator) 수신
  |   +-- 유저 메시지 -> 미션으로 처리
  |   +-- Claude 호출 (팀원 정보 포함된 CLAUDE.md)
  |   +-- 응답: "미션 접수. 2개 태스크로 분해.
  |             @coder_bot 쇼핑몰 크롤러 Python으로 작성해줘.
  |             @tester_bot 크롤러 완성 후 pytest 작성해줘. 대기."
  |
  +-- coder (member) 수신
  |   +-- @멘션됨 -> Claude 호출
  |   +-- workspace/에 scraper.py 작성
  |   +-- 응답: "@dev_lead_bot 크롤러 완성. workspace/scraper.py"
  |
  +-- dev_lead가 coder 결과 수신
  |   +-- 팀원 봇 메시지 -> 결과 확인, 다음 단계 판단
  |   +-- 응답: "@tester_bot scraper.py 테스트 작성 시작해."
  |
  +-- tester (member) 수신
  |   +-- @멘션됨 -> Claude 호출
  |   +-- workspace/에 test_scraper.py 작성
  |   +-- 응답: "@dev_lead_bot 테스트 5개 작성, 전부 통과."
  |
  +-- dev_lead가 tester 결과 수신
      +-- 모든 태스크 완료 판단
      +-- 종합 보고: "미션 완료.
           - scraper.py: 상품 크롤러 (coder)
           - test_scraper.py: 테스트 5개 통과 (tester)
           workspace/에서 확인 가능."
```

### 사장님이 member를 직접 @멘션한 경우

Orchestrator 경유를 강제한다. 사장님이 팀원을 직접 호출해도 orchestrator가 가로챈다.

```
사장님: "@coder_bot 이거 빨리 고쳐"
  |
  +-- coder (member) 수신
  |   +-- @멘션됨 BUT 발신자가 유저(봇이 아님)
  |   +-- 그룹 모드에서 유저 직접 멘션은 무시
  |   +-- (로그만 기록)
  |
  +-- dev_lead (orchestrator) 수신
      +-- 유저 메시지 -> 미션으로 처리
      +-- Claude가 판단: 사장님이 coder에게 직접 지시하려 함
      +-- 응답: "접수했습니다. @coder_bot 사장님 요청: 이거 빨리 고쳐줘."
```

Member 반응 규칙: **@멘션 + 발신자가 봇(orchestrator)**일 때만 반응. 유저가 직접 멘션해도 무시.

### 팀원이 orchestrator에게 되묻는 경우

Member가 작업 중 불명확한 점이 있으면 orchestrator에게 질문한다. Orchestrator가 직접 답한다 (사장님에게 올리지 않음).

```
coder: "@dev_lead_bot CSV 인코딩은 UTF-8로 하면 될까요?"
  |
  +-- dev_lead (orchestrator) 수신
  +-- Claude가 판단: 기술적 질문 → 직접 답변 가능
  +-- 응답: "@coder_bot UTF-8로 해. BOM 없이."
```

Orchestrator가 판단할 수 없는 경우에만 사장님에게 에스컬레이션:

```
coder: "@dev_lead_bot 쿠팡 로그인이 필요한데 계정 정보가 없습니다."
  |
  +-- dev_lead 수신
  +-- Claude가 판단: 사장님의 결정이 필요
  +-- 응답: "사장님, 쿠팡 크롤링에 로그인이 필요합니다. 계정 정보를 제공해주시겠어요?"
```

### 방향 변경 시

```
사장님: "아 크롤러 말고 API로 바꿔"
  |
  +-- dev_lead 수신 (유저 메시지 -> 미션 수정)
  +-- Claude가 맥락 파악 (세션 유지 중)
  +-- 응답: "방향 변경. @coder_bot 크롤러 중단하고 공식 API 연동으로 변경해줘."
```

### 팀원 실패 시

```
coder: "@dev_lead_bot 이 사이트는 Cloudflare 보호가 있어서 크롤링 불가합니다."
  |
  +-- dev_lead 수신
  +-- Claude가 판단: 다른 팀원에게 재분배 or 대안 제시
  +-- 응답: "@coder_bot 그러면 공식 API가 있는지 먼저 확인해줘."
      또는: "사장님, 크롤링이 차단됩니다. 대안: 1) API 사용, 2) 다른 사이트. 어떻게 할까요?"
```

## 핸들러 분기 로직

### handle_message 수정

```python
async def handle_message(update, context):
    chat_id = update.message.chat_id
    message = update.message

    # 자기 자신의 메시지는 무시
    if message.from_user.id == context.bot.id:
        return

    # 이 chat_id에 바인딩된 그룹이 있는가?
    group_config = find_group_by_chat_id(chat_id)

    if group_config is None:
        # 기존 로직: 1:1 DM 또는 일반 그룹
        return await handle_individual(update, context)

    # 그룹 미션 모드
    my_role = get_my_role(group_config, bot_name)

    # 모든 메시지를 공유 대화 로그에 기록
    log_to_shared_conversation(group_config, message)

    if my_role == "orchestrator":
        if not message.from_user.is_bot:
            # 유저(사장님) 메시지 -> 미션 처리
            await handle_as_orchestrator(update, context, group_config)
        elif is_member_bot(message.from_user, group_config):
            # 팀원 봇 결과 -> 수집 및 다음 단계 판단
            await handle_member_report(update, context, group_config)

    elif my_role == "member":
        if is_mentioned(message, bot_username) and message.from_user.is_bot:
            # @멘션됨 + 발신자가 봇(orchestrator) -> 태스크 수행
            await handle_as_member(update, context, group_config)
        # 그 외 (유저 직접 멘션 포함) -> 대화 로그만 기록 (위에서 이미 완료)
```

### 무한 루프 방지 (다중 레이어)

```
Layer 1: 자기 메시지 무시
  message.from_user.id == bot.id -> return

Layer 2: 역할 기반 필터
  orchestrator: 유저 메시지 + 멤버 봇 메시지만 처리
  member: @멘션된 경우만 처리

Layer 3: 발신자 기반 멘션 필터
  member는 봇(orchestrator)의 @멘션에만 반응
  유저가 member를 직접 @멘션해도 member는 무시 (orchestrator 경유 강제)
  orchestrator가 유저의 의도를 파악해서 재위임
```

## CLAUDE.md 자동 생성

### 기존 compose_claude_md() 확장

```python
def compose_claude_md(bot_name, group_context=None):
    # 기존: personality + skills + memory + rules
    content = compose_base(bot_name)

    # 신규: 그룹 컨텍스트 주입
    if group_context:
        content += "\n\n" + compose_group_context(bot_name, group_context)

    return content
```

### 그룹 컨텍스트 생성

```python
def compose_group_context(bot_name, group_config):
    my_role = "orchestrator" if group_config.orchestrator == bot_name else "member"

    if my_role == "orchestrator":
        lines = [
            f"# Group: {group_config.name}",
            "",
            "You are the orchestrator of this group.",
            "",
            "## Team Members",
        ]
        for member_name in group_config.members:
            member_config = load_bot_config(member_name)
            username = member_config.telegram_username
            lines.append(f"### @{username}")
            lines.append(f"- personality: {member_config.personality}")
            lines.append(f"- role: {member_config.role}")
            lines.append(f"- goal: {member_config.goal}")
            lines.append("")
        lines.extend([
            "## Rules",
            "1. If the mission is ambiguous, ask clarifying questions BEFORE breaking it into tasks",
            "2. Analyze the mission and break it into tasks",
            "3. Delegate tasks to members via @mention",
            "4. Reallocate on failure or direction change",
            "5. Synthesize results and report to the user",
            "",
            "## Shared Workspace",
            f"Results go to: groups/{group_config.name}/workspace/",
        ])
        return "\n".join(lines)

    else:  # member
        orchestrator_config = load_bot_config(group_config.orchestrator)
        return "\n".join([
            f"# Group: {group_config.name}",
            "",
            "You are a member of this group.",
            "",
            "## Rules",
            "- Only respond when @mentioned",
            f"- Report results to @{orchestrator_config.telegram_username}",
            f"- Save work to: groups/{group_config.name}/workspace/",
        ])
```

### 세션별 CLAUDE.md 분기

같은 봇이라도 세션(chat_id)에 따라 다른 CLAUDE.md를 받는다:

```
ensure_session(bot_path, chat_id, bot_name)
  |
  +-- group_config = find_group_by_chat_id(chat_id)
  |
  +-- if group_config:
  |     claude_md = compose_claude_md(bot_name, group_context=group_config)
  |   else:
  |     claude_md = compose_claude_md(bot_name)  # 기존 DM용
  |
  +-- write(session_dir / "CLAUDE.md", claude_md)
```

## 공유 대화 로그

### 포맷

`groups/<name>/conversation/YYMMDD.md`:

```markdown
## 2026-03-13

[14:30:01] user: 쇼핑몰 상품 크롤러 만들어줘. 테스트도.
[14:30:15] @dev_lead_bot: 미션 접수. 2개 태스크로 분해합니다. @coder_bot ...
[14:31:42] @coder_bot: @dev_lead_bot 크롤러 완성했습니다. workspace/scraper.py
[14:32:10] @dev_lead_bot: @tester_bot scraper.py 테스트 작성 시작해.
[14:33:55] @tester_bot: @dev_lead_bot 테스트 5개 작성, 전부 통과.
[14:34:08] @dev_lead_bot: 미션 완료. ...
```

### 용도

- Orchestrator가 부트스트랩 시 전체 맥락 복원
- Member가 부트스트랩 시 자기 관련 맥락 확인
- 봇 재시작 후 세션 복원에 사용

## CLI 명령어

### cclaw group create

```bash
cclaw group create <name> --orchestrator <bot_name> --members <bot1,bot2,...>

# 예시
cclaw group create dev_team --orchestrator dev_lead --members coder,tester
```

- `groups/<name>/group.yaml` 생성
- orchestrator와 members가 `config.yaml`에 등록된 봇인지 검증
- `conversation/`, `workspace/` 디렉토리 생성

### cclaw group list

```bash
cclaw group list

# 출력
Name        Orchestrator  Members        Telegram
dev_team    dev_lead      coder, tester  bound (-12345)
infra_team  coder         deployer       not bound
```

### cclaw group show

```bash
cclaw group show dev_team

# 출력
Name: dev_team
Orchestrator: dev_lead (@dev_lead_bot)
Members: coder (@coder_bot), tester (@tester_bot)
Telegram: -12345 (bound)
Workspace: 3 files
```

### cclaw group delete

```bash
cclaw group delete dev_team
```

### /bind (Telegram 명령)

```
# 그룹방에서
/bind dev_team
```

Orchestrator 봇이 처리. chat_id를 group.yaml에 기록.

### /unbind (Telegram 명령)

```
# 그룹방에서
/unbind
```

group.yaml에서 telegram_chat_id를 null로 초기화.

### 기존 슬래시 커맨드의 그룹 동작

그룹 대화와 개인 DM은 chat_id가 다르므로 세션이 완전히 분리되어 있다.

```
bots/coder/sessions/
+-- chat_222/           # 1:1 DM 세션 (개인비서)
+-- chat_-12345/        # dev_team 그룹 세션
```

| 명령 | 그룹에서의 동작 | DM 영향 |
|------|----------------|---------|
| `/reset` | 그룹 내 모든 봇의 그룹 세션 리셋 (chat_-12345). 공유 대화 로그 초기화. 공유 workspace 유지. | DM 세션(chat_222)에 영향 없음 |
| `/cancel` | 현재 그룹에서 실행 중인 모든 봇의 Claude 프로세스 취소 | DM에서 실행 중인 프로세스에 영향 없음 |
| `/memory` | orchestrator만 처리. orchestrator의 MEMORY.md 표시 | 각 봇 자기 MEMORY.md |

`/reset`은 orchestrator가 처리하며, 해당 그룹에 속한 모든 봇의 그룹 세션을 리셋한다:

## 변경 범위

### 변경하는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `cli.py` | `cclaw group` 서브커맨드 추가 (create/list/show/delete) |
| `handlers.py` | 그룹 분기 로직, /bind /unbind 핸들러, @멘션 감지 |
| `skill.py` | `compose_claude_md()`에 group_context 파라미터 추가 |
| `session.py` | `ensure_session()`에서 그룹 여부 판단 후 CLAUDE.md 분기 |

### 신규 파일

| 파일 | 역할 |
|------|------|
| `group.py` | 그룹 CRUD, group.yaml 로드/저장, find_group_by_chat_id, 공유 대화 로그 |

### 변경하지 않는 파일

| 파일 | 이유 |
|------|------|
| `bot.yaml` | 그룹 관련 필드 추가하지 않음 |
| `claude_runner.py` | Claude 실행 방식 변경 없음 |
| `bot_manager.py` | 봇 시작/종료 방식 변경 최소화 (CLAUDE.md 재생성 시 그룹 고려만 추가) |
| `config.py` | 그룹은 별도 디렉토리로 관리 |

## 구현 단계

### Phase 1: 그룹 기반 구조
- [x] `group.py` 모듈: group.yaml CRUD, 디렉토리 관리
- [x] `cli.py`: `cclaw group create/list/show/delete` 명령
- [x] 테스트: group.py 단위 테스트

### Phase 2: Telegram 바인딩
- [x] `handlers.py`: `/bind`, `/unbind` 슬래시 커맨드 핸들러
- [x] `group.py`: `find_group_by_chat_id()` 구현
- [x] `handlers.py`: 그룹 메시지 분기 로직 (orchestrator vs member)
- [x] 테스트: 핸들러 그룹 분기 테스트

### Phase 3: CLAUDE.md 그룹 컨텍스트
- [x] `skill.py`: `compose_group_context()` 함수
- [x] `skill.py`: `compose_claude_md()`에 group_context 파라미터
- [x] `session.py`: `ensure_session()`에서 그룹 여부 판단
- [x] 테스트: CLAUDE.md 생성 테스트 (DM vs 그룹 orchestrator vs 그룹 member)

### Phase 4: 공유 대화 로그 & Workspace
- [x] `group.py`: `log_to_shared_conversation()` 구현
- [x] `group.py`: 공유 workspace 경로 관리
- [x] `handlers.py`: 모든 그룹 메시지를 공유 로그에 기록
- [x] 테스트: 공유 로그 읽기/쓰기

### Phase 5: 통합 테스트 & 안정화
- [x] 멀티봇 그룹 시나리오 통합 테스트
- [x] 무한 루프 방지 검증
- [x] 봇 재시작 후 세션 복원 테스트
- [x] 멀티 그룹 겸직 시나리오 테스트

## 검증 체크리스트

### 1. group.py 단위 테스트

group.yaml CRUD 및 디렉토리 관리 검증.

```
테스트 환경: tmp_path + monkeypatch.setenv("CCLAW_HOME", ...)
```

- [x] **create_group**: group.yaml 생성, conversation/ workspace/ 디렉토리 생성 확인
- [x] **create_group 중복 방지**: 같은 이름으로 재생성 시 에러
- [x] **create_group 봇 검증**: 존재하지 않는 봇 이름 지정 시 에러
- [x] **create_group orchestrator 중복 소속 허용**: orchestrator가 다른 그룹에도 소속 가능
- [x] **load_group_config**: group.yaml 정상 로드, 필드 확인
- [x] **load_group_config 없는 그룹**: 존재하지 않는 그룹명 시 None 반환
- [x] **list_groups**: 여러 그룹 생성 후 전체 목록 반환
- [x] **list_groups 빈 상태**: 그룹이 없을 때 빈 리스트
- [x] **delete_group**: 디렉토리 전체 삭제 확인
- [x] **delete_group 없는 그룹**: 존재하지 않는 그룹 삭제 시 에러
- [x] **find_group_by_chat_id**: telegram_chat_id로 group_config 조회
- [x] **find_group_by_chat_id 미바인딩**: 바인딩 안 된 그룹은 조회 안 됨
- [x] **find_group_by_chat_id 멀티 그룹**: 여러 그룹 중 정확한 그룹 반환
- [x] **bind_group**: telegram_chat_id를 group.yaml에 기록
- [x] **bind_group 이미 바인딩됨**: 이미 바인딩된 그룹에 재바인딩 시 덮어쓰기
- [x] **unbind_group**: telegram_chat_id를 null로 초기화
- [x] **get_my_role**: orchestrator 봇이면 "orchestrator" 반환
- [x] **get_my_role**: member 봇이면 "member" 반환
- [x] **get_my_role**: 소속 안 된 봇이면 None 반환

### 2. 공유 대화 로그 단위 테스트

- [x] **log_to_shared_conversation**: 메시지 기록, 타임스탬프 포맷 확인
- [x] **log_to_shared_conversation 날짜별 파일**: 다른 날짜 메시지가 다른 파일에 기록
- [x] **log_to_shared_conversation append**: 기존 파일에 추가 (덮어쓰지 않음)
- [x] **log_to_shared_conversation 발신자 구분**: user vs @bot_username 표기 확인
- [x] **load_shared_conversation**: 최근 N개 메시지 로드
- [x] **load_shared_conversation 빈 상태**: 대화 없을 때 빈 문자열 반환

### 3. CLI 명령어 테스트

Typer CliRunner로 검증.

- [x] **cclaw group create**: 정상 생성, 출력 메시지 확인
- [x] **cclaw group create --orchestrator 미존재 봇**: 에러 메시지 확인
- [x] **cclaw group create --members 미존재 봇 포함**: 에러 메시지 확인
- [x] **cclaw group create 중복 이름**: 에러 메시지 확인
- [x] **cclaw group list**: 빈 상태, 1개, 여러 개 출력 확인
- [x] **cclaw group list 바인딩 상태 표시**: bound/not bound 구분 확인
- [x] **cclaw group show**: 상세 정보 출력 확인
- [x] **cclaw group show 미존재 그룹**: 에러 메시지 확인
- [x] **cclaw group delete**: 삭제 후 list에서 제거 확인
- [x] **cclaw group delete 미존재 그룹**: 에러 메시지 확인

### 4. 핸들러 그룹 분기 테스트

기존 mock_update 패턴 활용. `@pytest.mark.asyncio`.

#### 4-1. /bind, /unbind 핸들러

- [x] **/bind 정상**: orchestrator 봇이 수신 → chat_id 바인딩 → 안내 메시지
- [x] **/bind orchestrator가 아닌 봇**: member 봇이 수신 → 무시 (응답 없음)
- [x] **/bind 미존재 그룹명**: orchestrator 봇이 수신 → 에러 메시지
- [x] **/bind 이미 바인딩된 그룹**: 덮어쓰기 후 안내 메시지
- [x] **/unbind 정상**: 바인딩 해제 → 안내 메시지
- [x] **/unbind 바인딩 안 된 상태**: 에러 메시지

#### 4-2. 그룹 메시지 분기

- [x] **바인딩된 그룹 + 유저 메시지 + orchestrator 봇**: handle_as_orchestrator 호출
- [x] **바인딩된 그룹 + 유저 메시지 + member 봇**: 멘션 없으면 무시 (로그만 기록)
- [x] **바인딩된 그룹 + 봇 메시지(멤버 결과) + orchestrator 봇**: handle_member_report 호출
- [x] **바인딩된 그룹 + @멘션 메시지 + member 봇**: handle_as_member 호출
- [x] **바인딩된 그룹 + @멘션 없는 메시지 + member 봇**: 무시 (로그만 기록)
- [x] **미바인딩 그룹 chat_id**: 기존 handle_individual 호출 (그룹 로직 안 탐)
- [x] **1:1 DM**: 그룹 로직 안 타고 기존 동작

#### 4-3. 무한 루프 방지 & Orchestrator 경유 강제

- [x] **자기 메시지 무시**: bot.id == from_user.id → return
- [x] **member가 다른 member 메시지에 반응 안 함**: member 봇이 보낸 메시지에 다른 member 반응 없음
- [x] **orchestrator가 자기 메시지에 반응 안 함**: orchestrator 응답이 다시 orchestrator 트리거 안 됨
- [x] **member 응답이 다른 member 트리거 안 함**: member A 결과가 member B를 깨우지 않음 (멘션 없으면)
- [x] **유저가 member 직접 @멘션**: member 무시 (from_user.is_bot == False), orchestrator가 처리
- [x] **orchestrator가 member @멘션**: member 반응 (from_user.is_bot == True)

#### 4-4. 공유 대화 로그 기록

- [x] **유저 메시지**: 공유 로그에 "user:" 접두사로 기록
- [x] **orchestrator 응답**: 공유 로그에 "@bot_username:" 접두사로 기록
- [x] **member 응답**: 공유 로그에 "@bot_username:" 접두사로 기록
- [x] **무시된 메시지도 기록**: member가 처리하지 않은 메시지도 로그에는 기록

### 5. CLAUDE.md 그룹 컨텍스트 테스트

#### 5-1. compose_group_context

- [x] **orchestrator용 컨텍스트**: "orchestrator" 문자열 포함, 팀원 정보 포함
- [x] **orchestrator용 컨텍스트에 명확화 질문 규칙**: "ambiguous" 또는 "clarifying questions" 포함
- [x] **orchestrator용 팀원 정보**: 각 member의 personality, role, goal이 @username과 함께 포함
- [x] **member용 컨텍스트**: "member" 문자열 포함, @멘션 규칙 포함
- [x] **member용 컨텍스트에 orchestrator username**: 보고 대상 orchestrator @username 포함
- [x] **workspace 경로 포함**: orchestrator/member 모두 공유 workspace 경로 포함

#### 5-2. 세션별 CLAUDE.md 분기

- [x] **DM 세션**: 그룹 컨텍스트 없이 기존 CLAUDE.md 생성
- [x] **그룹 세션 (orchestrator)**: 기존 내용 + orchestrator 그룹 컨텍스트
- [x] **그룹 세션 (member)**: 기존 내용 + member 그룹 컨텍스트
- [x] **같은 봇, 다른 그룹**: 그룹별로 다른 CLAUDE.md 생성 (역할 다름)
- [x] **같은 봇, DM + 그룹 공존**: DM 세션은 그룹 컨텍스트 없음, 그룹 세션은 있음

### 6. 멀티 그룹 겸직 테스트

- [x] **봇이 2개 그룹에 member로 소속**: 각 그룹 chat_id에서 독립적으로 @멘션 반응
- [x] **봇이 1개 그룹 orchestrator + 1개 그룹 member**: 그룹별로 다른 역할로 동작
- [x] **봇이 그룹 member + 1:1 DM**: DM에서는 개인비서, 그룹에서는 member
- [x] **find_group_by_chat_id가 올바른 그룹 반환**: 여러 그룹 중 chat_id에 맞는 것만

### 7. 통합 시나리오 테스트

실제 메시지 흐름을 시뮬레이션. Claude API는 mock.

#### 7-1. 정상 미션 완료 시나리오

```
1. cclaw group create dev_team --orchestrator dev_lead --members coder,tester
2. /bind dev_team (chat_id 바인딩)
3. 유저: "쿠팡 크롤러 만들어줘"
4. dev_lead: 요구사항 명확화 질문 (Claude mock 응답)
5. 유저: "상품명, 가격. CSV로."
6. dev_lead: 태스크 분해 + @coder_bot 위임 (Claude mock 응답)
7. coder: @멘션 감지 → 작업 수행 → @dev_lead_bot 보고 (Claude mock 응답)
8. dev_lead: coder 결과 수신 → @tester_bot 위임 (Claude mock 응답)
9. tester: 작업 수행 → @dev_lead_bot 보고 (Claude mock 응답)
10. dev_lead: 종합 보고 (Claude mock 응답)
```

검증 포인트:
- [x] 각 단계에서 올바른 봇만 반응했는가
- [x] 공유 대화 로그에 모든 메시지가 시간순 기록되었는가
- [x] orchestrator가 명확화 질문을 먼저 했는가 (evaluation 테스트 작성 완료)
- [x] member는 @멘션 없이는 반응하지 않았는가

#### 7-2. 방향 변경 시나리오

```
1. 미션 진행 중 (coder가 작업 중)
2. 유저: "아 크롤러 말고 API로 바꿔"
3. dev_lead: 방향 변경 인지 → @coder_bot 재지시
4. coder: 새 지시 수행
```

검증 포인트:
- [x] orchestrator가 유저의 방향 변경을 처리했는가
- [x] orchestrator가 member에게 재지시 @멘션을 보냈는가
- [x] 공유 로그에 방향 변경 흐름이 기록되었는가

#### 7-3. 팀원 실패 시나리오

```
1. dev_lead가 @coder_bot에게 태스크 위임
2. coder: "@dev_lead_bot 불가능합니다. Cloudflare 차단."
3. dev_lead: 대안 판단 → 재분배 or 사장님에게 보고
```

검증 포인트:
- [x] orchestrator가 실패 보고를 수신했는가
- [x] orchestrator가 재분배 또는 에스컬레이션을 판단했는가 (evaluation 테스트 작성 완료)

#### 7-4. 봇 재시작 후 세션 복원 시나리오

```
1. 미션 진행 중 cclaw 재시작
2. 공유 대화 로그가 유지되는가
3. 봇이 그룹 메시지를 다시 받을 때 그룹 모드로 동작하는가
4. CLAUDE.md가 재생성되는가 (그룹 컨텍스트 포함)
```

검증 포인트:
- [x] group.yaml의 telegram_chat_id가 유지되는가
- [x] 공유 대화 로그 파일이 보존되는가
- [x] 재시작 후 ensure_session이 그룹용 CLAUDE.md를 다시 생성하는가
- [x] workspace 파일이 보존되는가

### 8. 그룹 슬래시 커맨드 테스트

- [x] **/reset 그룹**: orchestrator가 처리, 해당 그룹 모든 봇의 그룹 세션 리셋
- [x] **/reset 그룹 후 DM 세션 무사**: DM 세션(chat_222)이 영향받지 않음
- [x] **/reset 그룹 후 공유 대화 로그 초기화**: conversation/ 내 파일 삭제
- [x] **/reset 그룹 후 workspace 유지**: workspace/ 파일 보존
- [x] **/cancel 그룹**: 그룹 내 실행 중인 모든 봇 Claude 프로세스 취소
- [x] **/cancel 그룹 후 DM 프로세스 무사**: DM에서 실행 중인 Claude에 영향 없음

### 9. 공유 Workspace 테스트

- [x] **workspace flat 구조**: 봇별 서브디렉토리 없이 파일 직접 생성
- [x] **member가 workspace에 파일 쓰기**: 파일 생성 확인
- [x] **다른 member가 workspace 파일 읽기**: tester가 coder의 파일 접근 가능
- [x] **workspace 파일 목록 조회**: orchestrator가 결과물 목록 확인 가능
- [x] **/reset 후 workspace 보존**: 세션 리셋해도 workspace 파일 유지

### 10. 병렬 태스크 테스트

- [x] **동시 @멘션 2개 봇**: orchestrator가 한 메시지에서 2개 봇 동시 멘션 → 둘 다 반응
- [x] **동시 Claude 프로세스**: 2개 봇의 Claude가 동시에 실행되어도 충돌 없음
- [x] **동시 workspace 쓰기**: 2개 봇이 다른 파일을 동시에 쓸 때 문제 없음

### 11. Orchestrator 되묻기/에스컬레이션 테스트

- [x] **member → orchestrator 질문**: member가 @orchestrator 질문 → orchestrator 반응
- [x] **orchestrator 직접 답변**: 기술적 질문에 orchestrator가 직접 답 (evaluation 테스트 작성 완료)
- [x] **orchestrator 에스컬레이션**: 판단 불가 질문에 사장님에게 올림 (evaluation 테스트 작성 완료)

### 12. 엣지 케이스 테스트

- [x] **봇이 그룹에서 kick 당한 경우**: getChatMember 실패 처리 (Telegram API 에러 → 기존 핸들러 에러 로깅으로 대응, 수동 검증 대상)
- [x] **orchestrator 봇만 그룹에 있고 member가 없는 경우**: orchestrator가 혼자 처리 or 에러
- [x] **유저가 봇을 @멘션하지 않고 일반 메시지를 보낸 경우**: orchestrator만 반응
- [x] **유저가 member를 직접 @멘션한 경우**: member 무시, orchestrator가 가로채서 재위임
- [x] **두 봇이 동시에 같은 메시지에 반응하려는 경우**: 동시성 처리
- [x] **매우 긴 메시지 (4096자 초과)**: Telegram 메시지 분할 처리 (기존 split_message로 처리)
- [x] **그룹 이름에 특수문자/한글 포함**: group.yaml 파일명 안전성
- [x] **같은 chat_id에 두 그룹이 바인딩 시도**: 하나의 chat_id에는 하나의 그룹만

### 9. 수동 검증 (Evaluation 테스트)

실제 Claude API를 사용하는 테스트. `tests/evaluation/`에 위치. CI에서 제외.

#### 9-1. Orchestrator 요구사항 명확화 품질

```python
@pytest.mark.evaluation
CLARIFICATION_CASES = [
    # (유저 입력, 명확화 질문이 나와야 하는가)
    ("크롤러 만들어줘", True),
    ("뭔가 만들어줘", True),
    ("앱 하나 만들자", True),
    ("쿠팡에서 노트북 카테고리 상품명/가격 CSV 크롤링해줘", False),
    ("Python으로 2048 게임 만들어줘. pygame 사용. 테스트 포함.", False),
]
```

검증 포인트:
- [x] 모호한 미션에 대해 명확화 질문을 던지는가 (evaluation 테스트 작성 완료)
- [x] 명확한 미션에 대해 바로 태스크를 분해하는가 (evaluation 테스트 작성 완료)
- [x] 질문이 구체적이고 실행 가능한 답을 유도하는가 (evaluation 테스트 작성 완료)

#### 9-2. Orchestrator 태스크 분해 품질

```python
@pytest.mark.evaluation
DECOMPOSITION_CASES = [
    # (미션, 기대 @멘션 봇 목록)
    ("크롤러 만들고 테스트해줘", ["@coder_bot", "@tester_bot"]),
    ("코드만 짜줘", ["@coder_bot"]),
]
```

검증 포인트:
- [x] 태스크가 적절한 봇에게 @멘션으로 위임되는가 (evaluation 테스트 작성 완료)
- [x] 태스크 설명이 member가 실행할 수 있을 만큼 구체적인가 (evaluation 테스트 작성 완료)
- [x] 불필요한 봇을 부르지 않는가 (evaluation 테스트 작성 완료)

## Decisions

1. **specialty 필드를 추가하지 않는다** -- 봇의 기존 personality/role/goal이 충분하다. Orchestrator의 Claude가 이 정보를 읽고 스스로 판단한다. 필드를 추가하면 bot.yaml 스키마가 그룹에 종속된다

2. **역할은 group.yaml에서만 정의한다** -- 같은 봇이 그룹마다 다른 역할을 할 수 있어야 한다. bot.yaml에 역할을 넣으면 이게 불가능하다

3. **mission.yaml을 만들지 않는다** -- Orchestrator의 Claude 세션이 미션 상태를 관리한다. 공유 대화 로그가 영속적 기록이다. 별도 파일로 상태를 추적하면 Claude 세션과 동기화 문제가 생긴다

4. **공유 workspace에 결과물을 저장한다** -- Telegram 파일 업로드 대신 파일시스템 공유. 봇들이 같은 머신에서 돌아가므로 직접 파일 접근이 가능하고 간단하다

5. **@멘션 기반 트리거** -- 무한 루프를 구조적으로 방지한다. Orchestrator만 유저 메시지에 반응하고, member는 @멘션 시에만 반응한다. 추가 쿨다운이나 복잡한 턴 관리가 필요 없다

6. **공유 대화 로그는 groups/ 디렉토리에 둔다** -- 봇별 세션 디렉토리가 아닌 그룹 디렉토리에 공유 로그를 둔다. 모든 봇이 같은 로그를 읽을 수 있어야 하기 때문이다

7. **/bind는 orchestrator만 처리한다** -- 모든 봇이 /bind를 수신하지만, 해당 그룹의 orchestrator로 지정된 봇만 처리한다. 중복 처리를 방지한다

8. **Orchestrator는 모호한 미션에 먼저 질문한다** -- 사장님의 요구사항이 불명확하면 바로 분해하지 않고 명확화 질문을 던진다. 이것은 CLAUDE.md에 주입되는 모든 orchestrator의 기본 규칙이다. 명확한 미션은 질문 없이 바로 진행한다

9. **Orchestrator 경유 강제** -- 사장님이 member를 직접 @멘션해도 member는 무시한다. Orchestrator가 유저의 의도를 파악해서 재위임한다. Member는 봇(orchestrator)의 @멘션에만 반응한다. 지휘 체계를 일원화해서 혼선을 방지한다

10. **Member의 질문은 orchestrator가 답한다** -- Member가 작업 중 불명확한 점을 orchestrator에게 질문하면, orchestrator가 직접 답변한다. 사장님에게 올리는 것은 orchestrator가 판단할 수 없는 경우(계정 정보, 비즈니스 결정 등)에만 한다

11. **공유 workspace는 flat 구조** -- 봇별 서브디렉토리 없이 한 폴더에 모든 결과물을 저장한다. tester가 coder의 파일을 직접 읽을 수 있어야 하므로 단순한 flat 구조가 적합하다

12. **그룹 /reset은 그룹 세션만 리셋** -- 그룹과 DM은 chat_id가 다르므로 세션이 완전히 분리되어 있다. 그룹 /reset은 그룹 세션과 공유 대화 로그만 초기화하고, 각 봇의 DM 세션과 공유 workspace에는 영향 없다

13. **병렬 태스크 실행 허용** -- Orchestrator가 여러 member에게 동시 위임 가능. 각 봇의 Claude 호출은 독립 프로세스이므로 병렬 실행에 문제없다

14. **allowed_users 그룹 적용은 추후** -- 그룹에서 누구의 미션을 받을지는 일단 제외. 필요 시 나중에 추가한다

15. **Telegram rate limit은 실행 중 대응** -- 사전 설계 대신 실제 운영 중 429 에러 발생 시 대응한다
