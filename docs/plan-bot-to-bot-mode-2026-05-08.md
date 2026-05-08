# Plan: Telegram Bot-to-Bot Communication Mode Support
- date: 2026-05-08
- status: done
- author: claude
- approved-by:

---

## 1. 목적 및 배경

Telegram이 **Bot-to-Bot Communication Mode**를 신규 도입했다 (BotFather MiniApp 설정).
현재 abyss 그룹 협업은 **모든 봇이 BotFather Group Privacy OFF** 필수다.
이 플랜은 새 모드를 활용해 **멤버 봇의 Privacy 설정 부담을 제거**하고,
부가적으로 **멤버↔멤버 직접 위임** 경로도 공식 지원한다.

### 현재 구조

```
Human → [Group Chat] → Orchestrator (Privacy OFF) → @mention → Member (Privacy OFF)
                    ↑                                              ↓
                    └──────────────── @mention ────────────────────┘
```

Privacy OFF = 그룹 내 모든 메시지를 Telegram이 봇에 전달.
멤버 봇은 @mention만 처리하지만 Privacy OFF 필수였음 (Telegram 인프라 제약).

### 새 모드 동작

> "If at least one of the bots has Bot-to-Bot Communication Mode enabled,
> the receiving bot will get the message."

- **Bot-to-Bot Communication Mode ON** = 다른 봇의 @mention / reply를 수신 가능
- Privacy Mode OFF와 달리 사람 메시지 전체를 수신하지 않음 — 봇 메시지만 선택 수신
- BotFather MiniApp에서 봇별로 토글 (API 호출 불필요, 라이브러리 업데이트 불필요)

### 변경 후 구조

```
Human → [Group Chat] → Orchestrator (Privacy OFF) → @mention → Member (Privacy ON + B2B ON)
                    ↑                                              ↓
                    └──────────────── @mention ────────────────────┘

Member A (Privacy ON + B2B ON) → @mention → Member B (Privacy ON + B2B ON)  ← NEW
```

---

## 2. 예상 임팩트

| 영역 | 변경 |
|------|------|
| BotFather 설정 | 오케스트레이터: Privacy OFF 유지 / 멤버: Privacy ON + Bot-to-Bot Mode ON |
| `handlers.py` | 변경 없음 — 라우팅 로직 이미 정확 |
| `group.py` | 변경 없음 |
| `group.yaml` schema | `bot_to_bot_mode` 필드 추가 (검증용, 선택) |
| docs/ | README, CLAUDE.md, ARCHITECTURE.md, TECHNICAL-NOTES.md 업데이트 |
| CLI (`abyss doctor`) | Bot-to-Bot Mode 미설정 경고 추가 |
| 테스트 | `should_handle_group_message` 봇 sender 시나리오 커버리지 확인 |
| 신규 기능 | 멤버↔멤버 직접 @mention 위임 (코드 변경 없이, 인프라 설정만으로 동작) |

---

## 3. 구현 방법 비교

### Option A: 문서만 업데이트 (최소 범위)
README/docs만 고치고 "멤버는 Bot-to-Bot Mode 사용 가능" 안내.

**장점**: 작업량 최소  
**단점**: `abyss doctor`가 잘못된 설정을 감지 못함, group.yaml에 설정 상태가 안 남음

### Option B: group.yaml 스키마 + doctor 연동 ← 선택
`group.yaml`에 `bot_to_bot_mode: true` 필드 추가.
`abyss doctor`에서 그룹 설정 로드 시 필드 없으면 안내 메시지 출력.
문서 전면 업데이트.

**장점**: 설정 상태가 추적되고, doctor가 가이드 제공  
**단점**: group.yaml 스키마 변경 (하위 호환 — 필드 없으면 무시)

### 선택: Option B
`bot_to_bot_mode` 필드는 기존 group.yaml에 없으면 `None`으로 취급 (하위 호환).
doctor는 필드가 `None`이거나 `False`면 "멤버 봇에 Bot-to-Bot Mode 설정 권장" 안내.

---

## 4. 구현 단계

- [ ] Step 1: `group.yaml` 스키마에 `bot_to_bot_mode` 필드 추가 — `group.py` `create_group()` / `load_group_config()` 처리
- [ ] Step 2: `abyss doctor`에 그룹 Bot-to-Bot Mode 체크 추가 — 미설정 시 안내 메시지 (오류 아님, 정보성)
- [ ] Step 3: `abyss group create` / `abyss group add-member` CLI에 Bot-to-Bot Mode 설정 가이드 출력
- [ ] Step 4: `README.md` 그룹 설정 섹션 업데이트 — "각 봇 Privacy OFF" → 역할별 분리 안내
- [ ] Step 5: `CLAUDE.md` 업데이트 — "BotFather Group Privacy must be OFF for bots to receive group messages" 수정
- [ ] Step 6: `docs/ARCHITECTURE.md` 그룹 협업 섹션 업데이트
- [ ] Step 7: `docs/TECHNICAL-NOTES.md` 그룹 라우팅 매트릭스 업데이트 (멤버↔멤버 경로 추가)
- [ ] Step 8: 기존 `tests/test_handlers.py` bot sender 시나리오 테스트 확인 / 보강

---

## 5. 테스트 계획

### 단위 테스트

- [ ] `should_handle_group_message`: 오케스트레이터 — 봇 sender가 @mention 포함 시 True 반환
- [ ] `should_handle_group_message`: 오케스트레이터 — 봇 sender가 @mention 미포함 시 False
- [ ] `should_handle_group_message`: 멤버 — 봇 sender(@mention 포함) → True (Privacy ON 시뮬레이션: 메시지 자체가 안 오므로, 받은 경우 라우팅 확인)
- [ ] `should_handle_group_message`: 멤버 — 알 수 없는 봇 sender → False (group_config members에 없음)
- [ ] `group.py` `create_group()`: `bot_to_bot_mode` 필드 포함된 group.yaml 생성 확인
- [ ] `abyss doctor`: bot_to_bot_mode 미설정 그룹 → 안내 메시지 포함 여부

### 통합 테스트

- [ ] 멤버 봇이 봇 메시지(@mention 포함)를 받아 정상 처리 — 기존 Privacy OFF 경로와 동일 결과
- [ ] group.yaml에 `bot_to_bot_mode: false` 설정 시 doctor에서 경고 출력

---

## 6. 사이드 이펙트

- **group.yaml 스키마 변경**: `bot_to_bot_mode` 필드 없는 기존 설정파일 → `None` 처리, 하위 호환 유지
- **공유 대화 로그 완전성**: 멤버가 Privacy ON이면 사람 메시지를 수신하지 못해 공유 로그에 안 씀. 오케스트레이터(Privacy OFF)가 전체 로그를 커버하므로 누락 없음. 단, 멤버가 봇 메시지만 별도 로그에 쓰는 구조로 중복 감소 효과도 있음
- **기존 그룹 사용자**: Privacy OFF 유지해도 동작 — 이 플랜은 선택적 개선

---

## 7. 보안 검토

- **인증 우회 범위 변화 없음**: `message_handler`의 봇 sender 인증 우회(L983-985)는 그대로. Bot-to-Bot Mode는 Telegram 인프라 레벨이고 abyss 코드 로직에 영향 없음
- **신규 공격 벡터**: 없음 — Bot-to-Bot Mode는 BotFather에서 명시 활성화 필요. 임의 봇이 메시지를 보낼 수 없음 (group_config members 검증은 그대로 유지됨, L162-185)
- **OWASP**: 해당 없음 (네트워크 레벨 설정 변경, 코드 로직 무변경)

---

## 구현 메모

### `group.yaml` 스키마 변경 예시

```yaml
# 기존
name: my-group
orchestrator: assistant
members:
  - coder
  - researcher
telegram_chat_id: -1001234567890

# 변경 후 (선택 필드 추가)
name: my-group
orchestrator: assistant
members:
  - coder
  - researcher
telegram_chat_id: -1001234567890
bot_to_bot_mode: true   # 멤버 봇에 BotFather Bot-to-Bot Mode 활성화 여부
```

### BotFather 설정 가이드 (업데이트된 README 내용)

```
# 그룹 협업 BotFather 설정

## 오케스트레이터 봇
- BotFather → Edit Bot → Group Privacy → DISABLE (Privacy Mode OFF)
  이유: 사람 메시지 전체 수신 필요

## 멤버 봇
- BotFather MiniApp → Bot Settings → Bot-to-Bot Communication Mode → ENABLE
- Group Privacy는 ON 유지 가능 (사람 메시지 불필요)
  이유: 오케스트레이터/다른 멤버의 @mention만 수신하면 됨
```

### `abyss doctor` 출력 예시

```
[GROUP] my-group
  ✓ orchestrator: assistant (telegram_chat_id bound)
  ⚠ bot_to_bot_mode not set — member bots (coder, researcher) may require
    Group Privacy OFF unless Bot-to-Bot Communication Mode is enabled in BotFather.
    Run: abyss group info my-group for setup instructions.
```
