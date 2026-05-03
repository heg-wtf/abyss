"use client";

import * as React from "react";
import { FileText, Paperclip, Send, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  ALLOWED_UPLOAD_MIME_TYPES,
  MAX_UPLOAD_BYTES,
  MAX_UPLOADS_PER_MESSAGE,
  uploadAttachment,
  UpstreamError,
  type UploadedAttachment,
} from "@/lib/abyss-api";

const ACCEPT_ATTR = ALLOWED_UPLOAD_MIME_TYPES.join(",");
const ALLOWED_SET = new Set<string>(ALLOWED_UPLOAD_MIME_TYPES as readonly string[]);

interface PendingAttachment {
  localId: string;
  file: File;
  previewUrl: string;
  uploaded?: UploadedAttachment;
  uploading: boolean;
  error?: string;
}

export interface PromptSubmitPayload {
  text: string;
  attachments: UploadedAttachment[];
}

interface Props {
  bot: string | null;
  sessionId: string | null;
  onSubmit: (payload: PromptSubmitPayload) => void;
  onCancel: () => void;
  disabled?: boolean;
  streaming?: boolean;
  placeholder?: string;
}

const newId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function PromptInput({
  bot,
  sessionId,
  onSubmit,
  onCancel,
  disabled,
  streaming,
  placeholder,
}: Props) {
  const [value, setValue] = React.useState("");
  const [pending, setPending] = React.useState<PendingAttachment[]>([]);
  const [transientError, setTransientError] = React.useState<string | null>(null);
  const [dragActive, setDragActive] = React.useState(false);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const updatePending = React.useCallback(
    (id: string, patch: Partial<PendingAttachment>) => {
      setPending((prev) =>
        prev.map((item) => (item.localId === id ? { ...item, ...patch } : item))
      );
    },
    []
  );

  // Revoke object URLs on unmount to avoid blob leaks.
  React.useEffect(() => {
    const urls = pending.map((p) => p.previewUrl);
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [pending]);

  // Drop pending attachments whenever the active bot or session changes —
  // their `uploads/...` paths belong to the previous session's workspace
  // and `/chat` would reject them as missing.
  React.useEffect(() => {
    setPending((prev) => {
      prev.forEach((item) => URL.revokeObjectURL(item.previewUrl));
      return [];
    });
    setTransientError(null);
  }, [bot, sessionId]);

  const startUpload = React.useCallback(
    async (file: File) => {
      if (!bot || !sessionId) {
        setTransientError("Pick or create a chat before attaching files");
        return;
      }
      const localId = newId();
      const item: PendingAttachment = {
        localId,
        file,
        previewUrl: URL.createObjectURL(file),
        uploading: true,
      };
      setPending((prev) => [...prev, item]);
      try {
        const uploaded = await uploadAttachment(bot, sessionId, file);
        updatePending(localId, { uploaded, uploading: false });
      } catch (error) {
        const message =
          error instanceof UpstreamError
            ? `${error.status}: ${error.body || error.message}`
            : error instanceof Error
              ? error.message
              : String(error);
        updatePending(localId, { uploading: false, error: message });
      }
    },
    [bot, sessionId, updatePending]
  );

  const addFiles = React.useCallback(
    (files: FileList | File[]) => {
      setTransientError(null);
      const incoming = Array.from(files);
      if (pending.length + incoming.length > MAX_UPLOADS_PER_MESSAGE) {
        setTransientError(
          `Up to ${MAX_UPLOADS_PER_MESSAGE} files per message`
        );
        return;
      }
      for (const file of incoming) {
        if (!ALLOWED_SET.has(file.type)) {
          setTransientError(
            `Unsupported file type: ${file.type || "unknown"}. Allowed: ${ALLOWED_UPLOAD_MIME_TYPES.join(", ")}`
          );
          continue;
        }
        if (file.size > MAX_UPLOAD_BYTES) {
          setTransientError(
            `${file.name} is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}`
          );
          continue;
        }
        void startUpload(file);
      }
    },
    [pending.length, startUpload]
  );

  const removePending = (id: string) => {
    setPending((prev) => {
      const target = prev.find((item) => item.localId === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((item) => item.localId !== id);
    });
  };

  const submit = () => {
    const trimmed = value.trim();
    const ready = pending.filter((p) => p.uploaded && !p.error);
    const hasErrorOrPending = pending.some((p) => p.uploading || p.error);
    if (hasErrorOrPending) return;
    if (!trimmed && ready.length === 0) return;
    if (disabled) return;

    onSubmit({
      text: trimmed,
      attachments: ready.map((p) => p.uploaded!),
    });
    setValue("");
    pending.forEach((p) => URL.revokeObjectURL(p.previewUrl));
    setPending([]);
    setTransientError(null);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData?.files ?? []);
    if (files.length > 0) {
      event.preventDefault();
      addFiles(files);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    if (Array.from(event.dataTransfer.types).includes("Files")) {
      event.preventDefault();
      setDragActive(true);
    }
  };

  const handleDragLeave = () => setDragActive(false);

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    if (event.dataTransfer.files.length > 0) {
      addFiles(event.dataTransfer.files);
    }
  };

  React.useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 240)}px`;
  }, [value]);

  const anyUploading = pending.some((p) => p.uploading);
  const anyError = pending.some((p) => p.error);
  const sendDisabled =
    disabled ||
    anyUploading ||
    anyError ||
    (!value.trim() && pending.filter((p) => p.uploaded).length === 0);

  return (
    <div className="border-t bg-background px-4 py-3">
      {transientError && (
        <div className="mb-2 rounded-md bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          {transientError}
        </div>
      )}
      {pending.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {pending.map((item) => (
            <AttachmentChip
              key={item.localId}
              item={item}
              onRemove={() => removePending(item.localId)}
            />
          ))}
        </div>
      )}
      <div
        className={cn(
          "flex items-end gap-2 rounded-lg border bg-muted/40 p-2 focus-within:ring-2 focus-within:ring-ring",
          dragActive && "ring-2 ring-primary"
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTR}
          hidden
          onChange={(event) => {
            if (event.target.files) addFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <Button
          type="button"
          size="icon"
          variant="ghost"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || !bot || !sessionId}
          title="Attach files"
          aria-label="Attach files"
        >
          <Paperclip className="size-4" />
        </Button>
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          rows={1}
          placeholder={
            placeholder ?? "Type a message…  (Enter to send, Shift+Enter for newline)"
          }
          className="min-h-[36px] resize-none border-none bg-transparent shadow-none focus-visible:ring-0"
          disabled={disabled}
        />
        {streaming ? (
          <Button
            type="button"
            size="icon"
            variant="destructive"
            onClick={onCancel}
            aria-label="Stop"
          >
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            type="button"
            size="icon"
            onClick={submit}
            disabled={sendDisabled}
            aria-label="Send"
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

function AttachmentChip({
  item,
  onRemove,
}: {
  item: PendingAttachment;
  onRemove: () => void;
}) {
  const isImage = item.file.type.startsWith("image/");
  return (
    <div
      className={cn(
        "group flex items-center gap-2 rounded-md border bg-background px-2 py-1 text-xs",
        item.error && "border-destructive bg-destructive/5"
      )}
    >
      {isImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={item.previewUrl}
          alt={item.file.name}
          className="size-8 rounded object-cover"
        />
      ) : (
        <FileText className="size-5 text-muted-foreground" />
      )}
      <div className="flex max-w-[140px] flex-col">
        <span className="truncate font-medium">{item.file.name}</span>
        <span className="text-[10px] text-muted-foreground">
          {item.uploading
            ? "Uploading…"
            : item.error
              ? item.error
              : formatBytes(item.file.size)}
        </span>
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        aria-label={`Remove ${item.file.name}`}
      >
        <X className="size-3" />
      </button>
    </div>
  );
}
