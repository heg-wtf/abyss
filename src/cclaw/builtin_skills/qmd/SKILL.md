# QMD - 마크다운 지식 검색

QMD로 사용자의 마크다운 지식베이스, 노트, 문서, 과거 대화 기록을 검색한다. 모든 처리는 로컬에서 수행된다.

## 검색 방법

- search: 키워드 기반 빠른 검색 (BM25, ~30ms)
- vector_search: 의미 기반 검색 — 다른 단어를 써도 비슷한 개념을 찾음 (~2s)
- deep_search: 쿼리 확장 + 키워드 + 의미 + 재정렬 — 가장 정확하지만 느림 (~10s)
- get / multi_get: 검색 결과에서 문서 전문 조회
- status: 인덱스 상태, collection 목록, 문서 수 확인

## 검색 전략

- 간단한 키워드 → search (빠름)
- 개념적/추상적 질문 → vector_search 또는 deep_search
- 특정 collection만 검색: collection 파라미터 사용
- minScore 0.5 이상인 결과만 신뢰

## 트리거 표현

사용자가 다음과 같이 요청하면 QMD 검색을 수행한다:
- "내 노트에서 찾아줘", "메모에서", "문서에서"
- "지난번에 뭐 물어봤지?", "예전에 얘기했던", "이전 대화에서"
- "기억나?", "전에 말했던"
- 특정 주제에 대한 기억/기록을 요청할 때

## Collection 구조

- cclaw 대화 기록: `cclaw-conversations` collection (자동 등록)
- 사용자 노트/문서: 사용자가 직접 추가한 collection (`qmd collection add`)

## 사용 규칙

- 검색 결과의 문서 경로와 관련 내용을 함께 제시
- collection을 알면 collection 파라미터로 범위 좁히기
- 대화 기록 검색 시 날짜와 맥락 함께 제시
- 검색 결과가 없으면 다른 검색 모드로 재시도 (search → deep_search)
