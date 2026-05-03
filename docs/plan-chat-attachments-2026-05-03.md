# Plan: 대시보드 채팅 파일 첨부 (이미지 + PDF)

- date: 2026-05-03
- status: done
- author: claude
- approved-by: user (auto-mode 2026-05-03)
- target-repo: /Users/ash84/workspace/heg/cclaw
- pr: feat/chat-attachments

## 완료 기록 (2026-05-03)

| 항목 | 결과 |
|---|---|
| Python tests | `uv run pytest` → **956 passed** (회귀 0, +11 신규) |
| Python lint+format | All checks passed, 71 files formatted |
| Node tests | `npm run test` → 71 passed (vitest, +3 신규 attachment 테스트) |
| Node TS / lint / build | 0 errors, `/chat`/`/api/chat/upload`/`/api/chat/sessions/[bot]/[id]/file/[name]` 라우트 등록 |

### 누락 기능 복구 (PR #30 squash 시 손실분)
PR #30 squash 머지 과정에서 `UpstreamError`/`upstreamErrorToResponse`, `ChatSession.bot_display_name`, ChatMessage 의 `botName`/`botDisplayName` 등 일부 정의가 main에 누락되어 있어 본 PR에서 함께 복구했음.

## 1. 목적 및 배경

PR #30(`5d80ad8`) 이후 대시보드 채팅에 텍스트만 보낼 수 있음. Telegram 봇은 이미 `file_handler`로 사진·문서를 받아 `workspace/`에 떨어뜨리고 prompt에 path를 박아 Claude에게 전달함. 같은 봇이 두 채널에서 동일하게 동작하도록 **대시보드도 이미지(PNG/JPG/WebP/GIF) + PDF 첨부 지원**.

**핵심 회수 — Telegram 패턴 그대로**
- `LLMRequest.images`는 데드 필드 (현재 모든 backend가 무시). 진짜 동작은: 파일을 `session_dir/workspace/`에 저장 → `user_prompt`에 `File: <abs path>` 박음 → Claude가 `Read` tool로 알아서 열어봄.
- 따라서 multimodal SDK 와이어링 **불필요**. 단순 파일 저장 + prompt 텍스트 조립.
- `claude_code` backend면 이미지/PDF 모두 처리 가능. `openai_compat`(text-only)면 이미지를 못 봐도 path 텍스트는 읽으니 동작 자체는 깨지지 않음 (단순 무시).

## 2. 예상 임팩트

| 영역 | 변경 |
|---|---|
| `src/abyss/chat_core.py` | `process_chat_message`에 `attachments: tuple[Path,...]=()` 추가. user_prompt 조립 시 `File: <path>` lines append (Telegram `file_handler`와 동형). log 줄도 `[file: a.png, b.pdf]` 프리픽스. |
| `src/abyss/chat_server.py` | 신규 `POST /chat/upload` (multipart), `GET /chat/sessions/<bot>/<id>/file/<name>` (서빙), 기존 `POST /chat`이 JSON body에서 `attachments` 받아 chat_core로 forward. |
| `abysscope/src/lib/abyss-api.ts` | `uploadAttachment()`, `attachmentUrl()`, `streamChatRaw` body에 `attachments` 필드 추가. |
| `abysscope/src/app/api/chat/upload/route.ts` (신규) | multipart 프록시 (Next 라우트는 multipart를 그대로 sidecar로 흘려 보냄). |
| `abysscope/src/app/api/chat/sessions/[bot]/[id]/file/[name]/route.ts` (신규) | sidecar로부터 binary 프록시. |
| `abysscope/src/components/chat/prompt-input.tsx` | 클립 아이콘, 파일 picker, 드래그앤드롭, 클립보드 paste, preview 칩. |
| `abysscope/src/components/chat/chat-message.tsx` | user 메시지에 attachment thumbnail 행 추가. PDF는 아이콘 + 파일명 + 클릭=새 탭. 이미지는 inline thumbnail. |
| `abysscope/src/components/chat/chat-view.tsx` | pending uploads 상태, 전송 시 업로드→채팅 2-phase. |
| 데이터 | `~/.abyss/bots/<bot>/sessions/chat_web_*/workspace/uploads/` 하위. 봇이 `workspace/`만 보면 되는 격리는 그대로. |
| 성능 | 파일당 10MB → SDK 한입 처리 가능. 업로드는 multipart 스트리밍. |
| UX | 첨부 미리보기, 제거, 진행상태 표시. |

## 3. 핵심 설계 결정 (사용자 확정)

- **2-phase 업로드** ✅ — `POST /chat/upload` (multipart, 1파일/요청)로 저장 후 path 받음 → `POST /chat` (JSON, `attachments: [...]`)으로 채팅. 병렬 업로드 가능, 업로드 실패 시 채팅 재시도 분리.
- **하드 리밋** ✅ — 10MB/파일, 5/메시지, 50/세션 누적. MIME whitelist: `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `application/pdf`.
- **저장 경로** — `session_dir/workspace/uploads/<8hex>__<safe_basename>.<ext>`. uuid 프리픽스로 충돌 방지, sanitized 원본명 보존(읽기 좋음). path는 `session_dir.resolve().relative_to(abyss_home)` 검사로 traversal 차단.
- **대화 로그 포맷** — `[file: foo.png, doc.pdf]\n\n<caption>` (Telegram의 `[file: filename] {caption}` 패턴을 다중 파일로 확장). 캡션 없으면 첫 줄만.

## 4. 구현 단계

### Phase A — Python (chat_core + chat_server)

- [ ] **A1.** `src/abyss/chat_core.py`
  - `process_chat_message(...)` 시그니처에 `attachments: tuple[Path, ...] = ()` 추가.
  - 분기:
    - `attachments`가 비면 기존 동작 그대로.
    - 비지 않으면 `user_message_with_files = f"[file: {', '.join(p.name for p in attachments)}] {user_message}".rstrip()`로 conversation log entry 작성, `prompt_text = (user_message or "I sent files.") + "\n\n" + "\n".join(f"File: {p}" for p in attachments)`로 prompt 조립. (`file_handler` L998-1002 미러링)
  - `prepare_session_context(bot_path, session_dir, prompt_text)` 호출.

- [ ] **A2.** `src/abyss/chat_server.py` 보안 헬퍼
  - 상수: `MAX_UPLOAD_BYTES = 10 * 1024 * 1024`, `MAX_UPLOADS_PER_MESSAGE = 5`, `MAX_UPLOADS_PER_SESSION = 50`.
  - `ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}`.
  - `EXT_BY_MIME = {"image/png":".png", "image/jpeg":".jpg", "image/webp":".webp", "image/gif":".gif", "application/pdf":".pdf"}`.
  - `_sanitize_basename(name) -> str` — `Path(name).stem`만 추출, `[^a-zA-Z0-9가-힣_-]` → `_`, max 60chars, 빈 문자열이면 `"file"`.
  - `_uploads_dir(session_dir) -> Path` — `session_dir / "workspace" / "uploads"` (mkdir parents).
  - `_validate_path_under(child, parent)` — resolve 후 `relative_to`로 검증, 실패 시 HTTP 400.

- [ ] **A3.** `POST /chat/upload` 핸들러
  - Body: multipart with form fields `bot`, `session_id`, file under `file`. (`aiohttp.MultipartReader` or `request.post()`).
  - 검증: bot/session_id regex, MIME (`Content-Type`)이 whitelist에 있는지, 파일 크기 ≤ 10MB (스트리밍 중 누적 카운트), 세션 누적 업로드 수 < 50.
  - 저장: `_uploads_dir(session_dir) / f"{uuid.uuid4().hex[:8]}__{sanitized}{ext_by_mime}"`.
  - 응답: `{path: "uploads/<filename>", display_name: "<original>", mime: "...", size: <int>}`.
  - 실패 응답: `400 invalid_mime`, `413 too_large`, `429 too_many_uploads`.

- [ ] **A4.** `GET /chat/sessions/<bot>/<id>/file/<name>` 핸들러
  - bot/session_id/name regex 검증 (`name`: `^[a-zA-Z0-9가-힣_-]+\.(png|jpg|jpeg|webp|gif|pdf)$`).
  - resolve 후 `_uploads_dir(session_dir)` 하위 검증, `web.FileResponse`로 서빙. mime 추정. cache-control: private.

- [ ] **A5.** `POST /chat` 확장 (기존 핸들러 수정, 호환 유지)
  - JSON body에 `attachments: list[str] | None` 옵셔널.
  - 각 항목은 `_uploads_dir(session_dir)` 안의 파일이어야 함 (existence + path traversal 검증).
  - `chat_core.process_chat_message(..., attachments=tuple(resolved_paths))`로 전달.
  - 첨부 0개면 정확히 기존 동작.

- [ ] **A6.** Cleanup 정책
  - 세션 삭제(`DELETE /chat/sessions/<bot>/<id>`) 시 `workspace/uploads/`도 같이 삭제됨 (기존 `shutil.rmtree(session_dir)`로 자동).
  - 별도 GC 없음 (50개 리밋이 사실상 cap).

### Phase B — Next.js (proxy + client)

- [ ] **B1.** `abysscope/src/lib/abyss-api.ts`
  - `interface Attachment { path: string; display_name: string; mime: string; size: number; }`
  - `streamChatRaw(bot, sessionId, message, signal?, attachments?: Attachment[])` 추가 (body JSON에 `attachments` 필드 포함; 빈 배열이면 생략).
  - `uploadAttachment(bot, sessionId, file: File, signal?) -> Promise<Attachment>` — multipart `FormData`, `/api/chat/upload`로 POST, `UpstreamError` 처리.
  - `attachmentUrl(bot, sessionId, name) -> string`.

- [ ] **B2.** `abysscope/src/app/api/chat/upload/route.ts` (신규)
  - `POST` — `request.formData()` 받아 그대로 sidecar `/chat/upload`로 multipart 프록시. `upstreamErrorToResponse`로 4xx 보존.

- [ ] **B3.** `abysscope/src/app/api/chat/sessions/[bot]/[id]/file/[name]/route.ts` (신규)
  - `GET` — sidecar `/chat/sessions/<bot>/<id>/file/<name>` fetch → 응답 body + content-type 헤더 그대로 forward.

- [ ] **B4.** `abysscope/src/app/api/chat/route.ts`
  - 변경 없음. body는 이미 raw text로 forward.

### Phase C — UI

- [ ] **C1.** `prompt-input.tsx` 재작성
  - props 확장: `onSubmit: (text: string, attachments: Attachment[]) => void`.
  - 파일 picker `<input type="file" hidden accept="image/png,image/jpeg,image/webp,image/gif,application/pdf" multiple ref={fileInputRef}>` + `Paperclip` 아이콘 버튼.
  - 드래그앤드롭: textarea wrapper에 `onDragOver` / `onDrop` 핸들러. drop 시 file picker와 동일 처리.
  - 클립보드 paste: textarea `onPaste`에서 `event.clipboardData.files` 처리 (Chrome/Safari 이미지 paste).
  - pending state: `Map<localId, {file, attachment?, uploading: boolean, error?: string}>`.
  - 파일 add 시 즉시 `uploadAttachment` 호출 (병렬). 완료되면 `attachment` 채움.
  - preview 행: 이미지는 thumbnail (`URL.createObjectURL` 로컬 미리보기, 업로드 완료 후에도 유지), PDF는 `FileText` 아이콘 + 파일명, 모두에 X 제거 버튼 (제거 시 빈 attachment면 그냥 drop, 업로드 완료된 attachment면 백엔드에 cleanup 요청은 생략 — 50 리밋만 신경).
  - 5장 초과 / 10MB 초과 / 잘못된 MIME → 클라이언트 측 alert.
  - 업로드 진행 중에는 Send 버튼 disabled. 업로드 1개라도 실패하면 Send 비활성 + 메시지.
  - submit 시 완료된 attachment list만 onSubmit으로 전달.

- [ ] **C2.** `chat-message.tsx`
  - 새 prop: `attachments?: { display_name: string; mime: string; url: string }[]`.
  - user 메시지일 때 thumbnail row를 텍스트 위에 렌더 (이미지: `<img>`, PDF: 파일 카드).
  - 이미지 클릭 → 새 탭. PDF 클릭 → 새 탭.

- [ ] **C3.** `chat-view.tsx`
  - `handleSubmit(text, attachments)` 시그니처로 수정. `useChatStream.send(bot, sessionId, text, attachments)`로 전달.
  - 메시지 객체에 `attachments` 보존. assistant 응답에는 attachments 없음.
  - `/messages` 응답을 다시 부를 때 user 메시지의 `[file: a.png, b.pdf]` 프리픽스를 파싱해 `attachments` 추출하는 헬퍼 (B5 참조).

- [ ] **C4.** `use-chat-stream.ts`
  - `send(bot, sessionId, message, attachments?)` 시그니처에 attachments 추가, body에 그대로 전달.

- [ ] **C5.** 메시지 히스토리 attachment 복원
  - `chat_server.py` `_parse_conversation_messages`가 `[file: a, b]` 프리픽스를 검출해 `attachments` 필드 채워 응답하도록 확장. 각 attachment는 `{display_name, mime, url}` 구조 (mime은 확장자로 추정, url은 `/api/chat/sessions/<bot>/<id>/file/<sanitized_real_name>` — 단 real filename은 uuid 프리픽스가 붙어 다름 → log에는 display_name만 있어 매핑 어려움. **대안**: 로그에 real filename도 적어 `[file: foo.png(8a3f__foo.png), bar.pdf(2c1e__bar.pdf)]` 형태). 결정: **log에 real filename 함께 저장**, 단 UI에는 display_name만 표시. 파싱은 `(display(real))` 페어로.

### Phase D — 테스트

- [ ] **D1.** `tests/test_chat_core.py` 추가
  - `attachments=(workspace/foo.png,)` 전달 시 user_prompt에 `File: <abs>` 포함 + log에 `[file: foo.png]` 프리픽스 검증.
  - 다중 파일.
  - attachments 빈 튜플이면 기존 동작 동일 (회귀 가드).

- [ ] **D2.** `tests/test_chat_server.py` 추가
  - upload happy path: PNG bytes multipart → 200, 디스크에 파일 존재, 응답 `path` 정확.
  - 검증 실패: invalid_mime (text/plain), too_large (12MB 모킹), too_many (51번째).
  - bot/session 검증, path traversal (`session_id="../etc"`).
  - 파일 서빙: 200 + 올바른 content-type, 존재 안 함은 404, real filename 변조 시도는 400.
  - `/chat`에 `attachments` 동봉: chat_core가 받았는지 monkeypatch로 검증, log에 프리픽스 기록 확인.
  - `_parse_conversation_messages`가 attachments 필드 채워 반환.

- [ ] **D3.** `abysscope/src/lib/__tests__/abyss-api.test.ts` 추가
  - `uploadAttachment` 성공/실패 (mock fetch).
  - `attachmentUrl` 인코딩 검증.

- [ ] **D4.** `abysscope/src/components/chat/__tests__/prompt-input.test.tsx` (신규)
  - 5장 초과 시 거절.
  - 잘못된 MIME 거절.
  - upload 진행 중 send 비활성.
  - 완료된 attachment만 onSubmit 인자에 전달.

## 5. 사이드 이펙트

| 항목 | 영향 | 대응 |
|---|---|---|
| `chat_core.process_chat_message` 시그니처 변경 | 호출자(chat_server) 1곳만 사용 | 기본값 `attachments=()` → backward compatible |
| `_parse_conversation_messages` 응답 스키마 확장 | 메시지 JSON에 `attachments` 추가 | 기존 클라이언트는 모르면 무시. 신규 메시지 컴포넌트가 active 사용 |
| workspace에 uploads/ 디렉토리 생성 | session_dir 청소 시 함께 정리됨 | 기존 `shutil.rmtree`로 OK |
| Telegram 호환성 | `file_handler`는 `attachments` 파라미터 안 씀, 자체 prompt 합성 그대로 | 영향 없음 |
| openai_compat backend가 이미지를 못 봄 | path만 텍스트로 보일 뿐 | 봇 응답이 "이미지를 볼 수 없다" 같은 식이 될 수 있음. UI에 "이 봇은 이미지를 직접 볼 수 없습니다" 안내 추후. 이번 PR은 claude_code 봇만 정상 동작 가정. |
| MEMORY/conversation FTS5 인덱스 | log에 `[file: ...]` 프리픽스 들어가 indexing됨 | 검색 시 히트 가능, 의도된 동작 |
| 디스크 사용량 | 봇별 50개 × 10MB = 500MB 상한 | 사용자 인지 가능 수준. 향후 `/chat/sessions/cleanup` API 검토 |

## 6. 보안 검토 (OWASP)

- **A01 Access Control**: sidecar는 loopback only 그대로. Origin 화이트리스트도 기존 미들웨어가 multipart에도 적용됨 (확인 필요).
- **A03 Injection / Path Traversal**:
  - 업로드 filename: 원본 그대로 사용 안 함. `<8hex>__<sanitized>` 형태로 저장.
  - 업로드 path 응답: `"uploads/<filename>"` 상대경로로만. `/chat`에서 다시 받을 때 `_uploads_dir(session_dir)` 하위인지 `relative_to` 검사.
  - 파일 서빙 endpoint: name 정규식 `^[a-zA-Z0-9가-힣_-]+\.(png|jpg|jpeg|webp|gif|pdf)$`만 허용, resolve 후 검사.
- **A04 Insecure Design**: MIME header 신뢰. 추가로 magic byte sniff (image/png == `\x89PNG`, jpeg == `\xff\xd8\xff`, webp == `RIFF...WEBP`, gif == `GIF8`, pdf == `%PDF-`)도 적용 → MIME spoof 차단.
- **A05 Misconfiguration**: 응답 헤더 `Content-Disposition: attachment` (PDF), 이미지는 inline 허용. 단 모든 응답에 `X-Content-Type-Options: nosniff` 추가.
- **A07 Auth**: 단일 사용자 로컬 가정 그대로. 옵션 `ABYSS_API_TOKEN` 미래 도입 시 자동 적용.
- **A08 SSRF/RCE**: 업로드된 파일을 서버가 실행하지 않음 (정적 서빙 only). Claude SDK의 `Read` tool은 텍스트 추출만 (PDF는 SDK 측에서 처리).
- **CSRF**: SSE/multipart 모두 POST + Origin 화이트리스트로 차단.
- **DoS**:
  - 파일당 10MB, 메시지 5장, 세션 50개 → 최대 500MB/세션.
  - aiohttp `client_max_size`를 11MB로 설정해 거대한 multipart 거절.
  - 동일 세션 동시 업로드 제한? 락 불필요 (각 파일 독립).
- **Privacy**: 업로드 파일은 봇 워크스페이스에만 저장, 외부 전송 없음. `claude_code` SDK로 넘어가는 것은 Claude API 정책 적용.
- **PCI-DSS**: 해당 없음.

## 7. 핵심 재사용 함수/모듈

| 무엇 | 위치 | 용도 |
|---|---|---|
| `file_handler` 로직 | `src/abyss/handlers.py:952` | prompt 합성 (`File: <path>`), log 프리픽스(`[file: ...]`) 패턴 그대로 미러링 |
| `_validate_bot_name` / `_validate_session_id` | `src/abyss/chat_server.py` | 업로드 endpoint도 동일 검증 |
| `_resolve_session_dir` | `src/abyss/chat_server.py` | path traversal 가드 재사용 |
| `_cors_middleware` | `src/abyss/chat_server.py` | multipart에도 자동 적용 |
| avatar route 패턴 | `abysscope/src/app/api/bots/[name]/avatar/route.ts` | 바이너리 서빙 패턴 |
| `UpstreamError` / `upstreamErrorToResponse` | `abysscope/src/lib/abyss-api.ts` | 4xx 보존하며 프록시 |
| `ChatSession` + `ChatMessage` 타입 확장 | `abysscope/src/lib/abyss-api.ts` | `attachments` 필드 추가 |
| `BotAvatar` (참고) | `abysscope/src/components/bot-avatar.tsx` | 이미지 fallback 패턴 |

## 8. 검증 (E2E)

```bash
# Python
cd /Users/ash84/workspace/heg/cclaw
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pytest

# Node
cd abysscope
npx tsc --noEmit && npm run lint && npm run test && npm run build

# 실제 동작
uv run abyss start  # in another terminal
# Browser → /chat → New chat (claude_code 봇)
# 1) 클립 클릭으로 PNG 첨부 → 미리보기 thumbnail 확인
# 2) 텍스트 + Send → SSE 스트리밍 응답 (Claude가 이미지 내용을 묘사하는지)
# 3) 새로고침 → 메시지 히스토리에 thumbnail 복원되는지
# 4) 5장 초과 시 거절
# 5) 11MB 파일 거절 (413)
# 6) 드래그앤드롭 / 클립보드 paste 동작
# 7) PDF 첨부 → 파일 카드 + 클릭 시 새 탭 PDF
# 8) 세션 삭제 → uploads/도 같이 사라지는지
```

## 9. 완료 조건

- [ ] 4번 모든 체크 박스 100%
- [ ] 5번 단위/통합 100%, 회귀 0
- [ ] `uv run ruff check . && uv run pytest` 통과 (945+ 테스트)
- [ ] `npm run lint && npm run test && npx tsc --noEmit && npm run build` 통과
- [ ] 6번 보안 검토 항목 각각에 "대응 완료" 명시
- [ ] plan 상단 `status: done`
- [ ] PR 생성, 자동 리뷰 봇 피드백 반영, CI green

## 10. 중단 기준

- aiohttp multipart 사이즈 제한 설정과 streaming validation이 예상대로 동작 안 하면 → magic byte 검사를 download 후로 미루는 대신 streaming 중 abort하는 더 복잡한 로직 → 중단 후 plan 수정.
- claude_code SDK가 PDF를 path-via-Read로 처리 못 한다고 확인되면 → multimodal 직접 wiring 필요(LLMRequest.images 활성화) → plan을 multimodal 분기 추가로 수정.
- multipart 프록시(Next → sidecar)가 streaming 단계에서 깨지면 → 일단 small file 한정으로 ship, large file은 후속 PR.
- 자동 리뷰 봇이 P1 수준 보안 이슈를 내면 즉시 수정 후 재검토.

## 11. 별도 PR 분리 추천

이번 PR(브랜치 제안: `feat/chat-attachments`)은 **이 plan만** 다룸. PR #30 머지 직후라 본문이 깔끔. 향후 Telegram-style 음성/문서 첨부 확장은 별도 PR.
