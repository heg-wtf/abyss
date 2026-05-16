"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ChatSession } from "@/lib/abyss-api";

export function DeleteSessionDialog({
  session,
  onClose,
  onDeleted,
}: {
  session: ChatSession | null;
  onClose: () => void;
  onDeleted: (deleted: { bot: string; id: string }) => void;
}) {
  const [submitting, setSubmitting] = React.useState(false);
  const handleDelete = async () => {
    if (!session) return;
    setSubmitting(true);
    try {
      const resp = await fetch(
        `/api/chat/sessions/${encodeURIComponent(session.bot)}/${encodeURIComponent(session.id)}`,
        { method: "DELETE" },
      );
      if (!resp.ok) return;
      onDeleted({ bot: session.bot, id: session.id });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Dialog open={!!session} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete chat?</DialogTitle>
          <DialogDescription>
            This permanently removes the session and its workspace files.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={submitting}
          >
            {submitting ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
