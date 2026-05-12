# Plan: 한국 도메인 빌트인 스킬 제거 (best-price, daiso, dart, kakao-local, naver-map, naver-search)

- date: 2026-05-13
- status: done
- author: claude
- approved-by: ash84 (2026-05-13)

## 1. 목적 및 배경

abyss의 빌트인 스킬은 "모든 사용자에게 보편적으로 유용한 스킬"이어야 한다. 현재 빌트인 19개 중 6개는 한국 시장 전용 서비스에 종속되어 있어 글로벌 사용자에게는 불필요한 노출이다.

- 제거 대상: `best-price`, `daiso`, `dart`, `kakao-local`, `naver-map`, `naver-search`
- 유지: 글로벌 플랫폼 10개(`gcalendar`, `gmail`, `imessage`, `reminders`, `image`, `supabase`, `translate`, `twitter`, `jira`, `qmd`) + 에이전트 내부 인프라 3개(`code_review`, `conversation_search`, `qmd` 자동 주입)

도메인 스킬은 abyss 코어에서 제공하지 않고, 사용자가 자체 작성하거나 `abyss skills import <github-url>`로 가져오는 방식으로 통일한다.

## 2. 예상 임팩트

### 영향 받는 영역
- `src/abyss/builtin_skills/`: 6개 디렉토리 삭제 (`best-price/`, `daiso/`, `dart/`, `kakao-local/`, `naver-map/`, `naver-search/`)
- `tests/test_builtin_skills.py`: 6개 스킬 관련 테스트 함수 제거 (`*_returns_naver_map`, `*_naver_map`, `*_best_price`, `*_dart` 등)
- `abysscope/src/lib/abyss.ts`: `BUILTIN_SKILL_NAMES` Set에서 6개 이름 제거
- `abysscope/src/lib/__tests__/abyss.test.ts`: `naver-search`, `dart`를 사용하는 테스트 케이스 수정 (다른 빌트인으로 교체 또는 가상 스킬명 사용)
- `docs/skills/`: 6개 문서 삭제 (`BEST-PRICE.md`, `DAISO.md`, `DART.md`, `KAKAO-LOCAL.md`, `NAVER-MAP.md`, `NAVER-SEARCH.md`)
- `docs/ARCHITECTURE.md`: 빌트인 스킬 목록 문장에서 6개 항목 제거
- `README.md`: Built-in Skills 표에서 6개 행 제거, "abyss의 빌트인 스킬은 보편적 도구만 제공" 철학 문장 추가, `abyss skills import` 명령 노출
- `docs/landing/index.html`: skill-tag 6개 제거 (`Naver Map`, `Best Price`, `Naver Search`, `Kakao Local`, `DART Disclosure`, `Daiso`)
- 신규 문서: `docs/SKILL_AUTHORING.md` (사용자가 직접 스킬을 작성/공유하는 방법 가이드)

### 사용자 경험
- `abyss skills builtins`, `abyss skills install` 목록에서 6개 사라짐
- 이미 `~/.abyss/skills/<name>/`에 설치된 사용자: 그대로 동작 (스킬 파일은 독립 복사본). 별도 경고/마이그레이션 없음
- 신규 사용자: 한국 서비스 스킬은 직접 작성하거나 외부 GitHub에서 import

### 성능/가용성
- 영향 없음. 패키지 크기 약간 감소

## 3. 구현 방법 비교

### 방법 A: 일괄 삭제 + 사용자 책임 (선택)
- 6개 빌트인 디렉토리, 관련 테스트, 문서, abysscope 상수 한 PR에서 삭제
- 기존 설치본은 자연 잔존, 별도 처리 없음
- 장점: 단순, 빠름, 코드 정리 명확
- 단점: 기존 빌트인 의존 사용자가 직접 알아채야 함

### 방법 B: Deprecated 마킹 후 단계적 제거
- skill.yaml에 `deprecated: true` 추가하고 `abyss skills install` 시 경고
- 다음 릴리즈에서 실제 삭제
- 장점: 사용자 인지 시간 확보
- 단점: 2단계 작업, abyss는 개인용/소규모 도구라 deprecation 사이클 과함

### 방법 C: 외부 레지스트리 + 자동 마이그레이션
- `heg-wtf/abyss-skills` 레포 신설, 6개를 옮긴 뒤 자동 import 안내
- 장점: 발견성 유지
- 단점: 사용자 답변에 따르면 불필요 (도메인은 사용자 책임)

→ **선택: 방법 A**. abyss 사용자 규모와 도메인 스킬 특성상 일괄 삭제가 가장 깔끔하며, 사용자 답변과 일치한다.

## 4. 구현 단계

- [ ] Step 1: 브랜치 생성 `feat/remove-domain-builtin-skills`
- [ ] Step 2: `src/abyss/builtin_skills/` 하위 6개 디렉토리 삭제
  - `best-price/`, `daiso/`, `dart/`, `kakao-local/`, `naver-map/`, `naver-search/`
- [ ] Step 3: `tests/test_builtin_skills.py`에서 6개 스킬 테스트 제거
  - `test_list_builtin_skills_returns_naver_map`, `test_get_builtin_skill_path_naver_map`, `test_is_builtin_skill_naver_map`, `test_install_builtin_skill_naver_map`, `test_installed_naver_map_skill_starts_inactive`
  - `test_list_builtin_skills_returns_best_price`, `test_get_builtin_skill_path_best_price`, `test_is_builtin_skill_best_price`, `test_install_builtin_skill_best_price`, `test_installed_best_price_skill_starts_inactive`
  - `test_list_builtin_skills_returns_dart`, `test_get_builtin_skill_path_dart`, `test_is_builtin_skill_dart`, `test_install_builtin_skill_dart`, `test_installed_dart_skill_starts_inactive`
  - daiso, kakao-local, naver-search 동일 패턴이 있다면 함께 제거
- [ ] Step 4: `abysscope/src/lib/abyss.ts`의 `BUILTIN_SKILL_NAMES`에서 6개 항목 제거
- [ ] Step 5: `abysscope/src/lib/__tests__/abyss.test.ts` 수정
  - `skills: ["imessage", "dart"]` → `skills: ["imessage", "translate"]` (또는 다른 유지 스킬)
  - `isBuiltinSkill("dart")` 테스트는 `isBuiltinSkill("translate")` 등으로 교체
  - `naver-search`를 사용한 listSkills 테스트는 임의 외부 스킬명(`my-custom-skill`)으로 교체
  - `usage["dart"]` assertion도 유지 스킬로 교체
- [ ] Step 6: `docs/skills/` 하위 6개 문서 파일 삭제
- [ ] Step 7: `docs/ARCHITECTURE.md`의 빌트인 스킬 목록 문장(line 194)에서 6개 항목 제거
- [ ] Step 8: 문서화 갱신
  - [ ] 8-1: `README.md` "Built-in Skills" 표에서 6개 행 제거 (line 97, 99, 103-104의 jira는 유지 등 신중히 식별 후 한국 6개만 삭제)
  - [ ] 8-2: `README.md` Skills 섹션 도입부에 "빌트인은 보편적 도구만 제공, 도메인/지역 특화 스킬은 사용자가 작성하거나 `abyss skills import <github-url>`로 가져온다" 문장 추가
  - [ ] 8-3: `README.md` 명령 목록에 누락된 `abyss skills import <url>` 추가
  - [ ] 8-4: `docs/landing/index.html`에서 한국 도메인 skill-tag 6개 제거
  - [ ] 8-5: `docs/ARCHITECTURE.md` line 194 빌트인 스킬 나열 문장에서 6개 제거
  - [ ] 8-6: `docs/SKILL_AUTHORING.md` 신규 작성. 포함 내용:
    - 스킬 디렉토리 구조 (`SKILL.md`, `skill.yaml`, 선택적 `mcp.json`)
    - `skill.yaml` 필드 레퍼런스 (`type`, `status`, `emoji`, `required_commands`, `install_hints`, `environment_variables`, `allowed_tools`)
    - 로컬 작성 워크플로 (`abyss skills add` 인터랙티브 → `~/.abyss/skills/<name>/` 직접 편집)
    - GitHub 공유 워크플로 (레포 구조, `tree/branch/subdir` URL 지원, `abyss skills import <url>` 사용법)
    - untrusted 플래그와 `disableSkillShellExecution` 보안 가드 설명
    - 한국 도메인 스킬 예시 링크 (만약 사용자가 작성해서 외부 레포로 옮긴 게 있다면 "Community Examples" 섹션에 링크. 없으면 생략)
  - [ ] 8-7: `README.md`에서 "Custom skills" 설명 라인에 `SKILL_AUTHORING.md` 링크 추가
- [ ] Step 9: `make lint` 통과 (ruff check + ruff format)
- [ ] Step 10: `uv run pytest` 통과
- [ ] Step 11: `abysscope` 측 `npm test` 통과 (워크스페이스에 따라 `pnpm test` 등)
- [ ] Step 12: 버전 범프 (`pyproject.toml`, `src/abyss/__init__.py`) — calendar versioning `2026.05.13` 또는 다음 날짜
- [ ] Step 13: 커밋 → PR (`feat/remove-domain-builtin-skills` → `main`)

## 5. 테스트 계획

### 단위 테스트
- [ ] 케이스 1: `list_builtin_skills()` 반환 길이 = 13 (19 - 6)
- [ ] 케이스 2: `is_builtin_skill("naver-search")` → False, `is_builtin_skill("naver-map")` → False, 나머지 5개도 False
- [ ] 케이스 3: `get_builtin_skill_path("dart")` → None
- [ ] 케이스 4: `install_builtin_skill("daiso")` → `ValueError("Unknown built-in skill: daiso")`
- [ ] 케이스 5: 유지된 빌트인 13개 각각이 `list_builtin_skills()`에 존재
- [ ] 케이스 6: abysscope `isBuiltinSkill("translate")` → true, `isBuiltinSkill("naver-search")` → false

### 통합 테스트
- [ ] 시나리오 1: `abyss skills builtins` CLI 실행 → 출력 목록에 한국 6개 없음
- [ ] 시나리오 2: `abyss skills install naver-search` → "Unknown built-in skill" 에러
- [ ] 시나리오 3: 테스트용 `~/.abyss/skills/naver-search/` 수동 생성 → `abyss skills list`에 `custom` 타입으로 표시되고 동작 (기존 설치본 동작 보장)
- [ ] 시나리오 4: abysscope 대시보드 `/skills` 페이지 → 빌트인 섹션에 6개 미노출, 사용자 설치본은 `custom` 라벨로 표시
- [ ] 시나리오 5: `abyss skills import https://github.com/...` 으로 외부 스킬 import → 정상 동작 (회귀 없음 확인)

### 문서 검증
- [ ] 케이스 D1: `README.md` Built-in Skills 표에서 한국 6개 행이 모두 사라졌고, 유지 13개는 그대로
- [ ] 케이스 D2: `README.md`에 `abyss skills import` 명령이 노출됨
- [ ] 케이스 D3: `docs/SKILL_AUTHORING.md` 파일 존재 및 헤더(스킬 디렉토리 구조, skill.yaml 필드, GitHub import) 항목 포함
- [ ] 케이스 D4: `docs/landing/index.html`에 `Naver Map`, `Best Price`, `Naver Search`, `Kakao Local`, `DART Disclosure`, `Daiso` 문자열이 모두 없음 (`grep -c` 결과 0)
- [ ] 케이스 D5: `docs/ARCHITECTURE.md` line 194 영역에 제거 대상 스킬명 미존재
- [ ] 케이스 D6: 모든 마크다운 내부 링크(`docs/skills/*.md`)가 깨지지 않음 — `grep -rn "docs/skills/" docs/ README.md`로 잔존 링크 확인

## 6. 사이드 이펙트

- **기존 빌트인 의존 사용자**: `~/.abyss/skills/<name>/` 설치본은 그대로 동작. 단 `abyss skills builtins` 목록과 abysscope 대시보드에서 `builtin` 라벨이 `custom`으로 바뀜. 기능적 회귀 없음
- **하위 호환성**: 빌트인이었던 스킬을 참조하는 `bot.yaml` 파일은 영향 없음 (설치본이 있으면 그대로 attach됨)
- **마이그레이션**: 사용자 책임. 별도 자동화 없음 (사용자 답변)
- **abysscope 테스트**: `dart`, `naver-search`를 하드코딩한 fixture 케이스를 유지 스킬로 교체 필요 (Step 5에서 처리)
- **landing page / 트위터 홍보 자료**: 한국 도메인 스킬 강조가 있었다면 톤 조정 필요 (Step 8-4에서 처리)
- **문서 내부 링크 깨짐**: `docs/skills/{BEST-PRICE,DAISO,DART,KAKAO-LOCAL,NAVER-MAP,NAVER-SEARCH}.md`를 가리키는 링크가 다른 마크다운에 잔존 시 404. 케이스 D6에서 검증

## 7. 보안 검토

- OWASP Top 10 해당 없음 — 코드/문서 삭제만 수행, 새 입력 경로 없음
- 인증/인가 변경 없음
- 민감 데이터 처리 변경 없음. 기존 빌트인의 환경 변수(`NAVER_CLIENT_ID`, `KAKAO_REST_API_KEY`, `DART_API_KEY`)는 사용자 환경에 잔존할 수 있으나 abyss 입장에서는 더 이상 참조 안 함. 사용자 책임
- PCI-DSS 영향 없음
- `abyss skills import`는 GitHub 외부 스킬을 untrusted 플래그로 자동 표시하는 기존 보안 가드(`disableSkillShellExecution`) 유지

## 8. 완료 조건

- 구현 단계 13개 100% 체크 (Step 8 하위 7개 항목 포함)
- 단위/통합 테스트 11개 + 문서 검증 6개 100% 통과
- `make lint && uv run pytest` 통과
- abysscope `npm test` 통과
- `docs/SKILL_AUTHORING.md` 작성 완료, README에서 링크
- 마크다운 내부 링크 깨짐 0건
- PR 생성 및 머지
- plan 상단 `status: done` 기재

## 9. 중단 기준

- abysscope 테스트에서 6개 스킬을 fixture로 참조하는 곳이 광범위해 단순 치환만으로 회복 불가한 경우 → plan 업데이트 후 재검토
- 보안 가드(`untrusted` 플래그, `disableSkillShellExecution`) 관련 빌트인-only 분기 발견 시 → plan 업데이트
