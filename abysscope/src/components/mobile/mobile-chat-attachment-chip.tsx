"use client";

import { X } from "lucide-react";
import type { PendingAttachment } from "./mobile-chat-types";

export function PendingAttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: PendingAttachment;
  onRemove: () => void;
}) {
  return (
    <div className="relative flex items-center gap-2 rounded-md border bg-background px-2 py-1 text-xs">
      <span className="max-w-[120px] truncate">{attachment.file.name}</span>
      {attachment.uploading && (
        <span className="text-muted-foreground">…</span>
      )}
      {attachment.error && (
        <span className="text-destructive">!</span>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="ml-1 text-muted-foreground hover:text-foreground"
        aria-label="Remove attachment"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}
