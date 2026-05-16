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

export function RenameSessionDialog({
  session,
  onClose,
  onRenamed,
}: {
  session: ChatSession | null;
  onClose: () => void;
  onRenamed: (updated: {
    bot: string;
    id: string;
    custom_name: string | null;
  }) => void;
}) {
  const [name, setName] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    setName(session?.custom_name ?? "");
  }, [session]);

  const handleSave = async () => {
    if (!session) return;
    setSubmitting(true);
    try {
      const resp = await fetch(
        `/api/chat/sessions/${encodeURIComponent(session.bot)}/${encodeURIComponent(session.id)}/rename`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        },
      );
      if (!resp.ok) return;
      const data = (await resp.json()) as { custom_name: string | null };
      onRenamed({
        bot: session.bot,
        id: session.id,
        custom_name: data.custom_name,
      });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={!!session} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Rename chat</DialogTitle>
          <DialogDescription className="text-xs">
            Leave blank to remove the custom name.
          </DialogDescription>
        </DialogHeader>
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="e.g. economy questions"
          maxLength={64}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          autoFocus
        />
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={submitting}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
