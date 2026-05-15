"use client";

import * as React from "react";
import { Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Avatar picker for the bot edit page.
 *
 * Reads + writes ``~/.abyss/bots/<name>/avatar.jpg`` via the
 * ``/api/bots/<name>/avatar`` route. Uses a local cache-busting
 * version stamp so the preview swaps the moment the upload completes
 * instead of waiting for the GET ``Cache-Control`` window to expire.
 */

interface AvatarUploaderProps {
  botName: string;
}

const ALLOWED_MIME = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_BYTES = 2 * 1024 * 1024;

export function AvatarUploader({ botName }: AvatarUploaderProps) {
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  const [version, setVersion] = React.useState(() => Date.now());
  const [hasAvatar, setHasAvatar] = React.useState<boolean | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Probe once on mount so we know whether to show the Remove button.
  React.useEffect(() => {
    let cancelled = false;
    fetch(`/api/bots/${botName}/avatar`, { method: "HEAD" })
      .then((response) => {
        if (cancelled) return;
        setHasAvatar(response.ok);
      })
      .catch(() => {
        if (!cancelled) setHasAvatar(false);
      });
    return () => {
      cancelled = true;
    };
  }, [botName]);

  const onPick = () => {
    setError(null);
    inputRef.current?.click();
  };

  const onFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-selecting the same file
    if (!file) return;

    if (!ALLOWED_MIME.has(file.type)) {
      setError("Use a JPEG, PNG, or WebP image.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("Image is larger than 2 MB.");
      return;
    }

    const form = new FormData();
    form.append("avatar", file);
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/bots/${botName}/avatar`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))) as {
          error?: string;
        };
        setError(detail.error || `Upload failed (${response.status}).`);
        return;
      }
      setHasAvatar(true);
      setVersion(Date.now());
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Network error.",
      );
    } finally {
      setBusy(false);
    }
  };

  const onRemove = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/bots/${botName}/avatar`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))) as {
          error?: string;
        };
        setError(detail.error || `Remove failed (${response.status}).`);
        return;
      }
      setHasAvatar(false);
      setVersion(Date.now());
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Network error.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <div className="relative size-16 shrink-0 overflow-hidden rounded-xl border bg-muted">
        {hasAvatar ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            key={version}
            src={`/api/bots/${botName}/avatar?v=${version}`}
            alt=""
            className="block size-full object-cover"
          />
        ) : (
          <div className="flex size-full items-center justify-center text-xs text-muted-foreground">
            No avatar
          </div>
        )}
      </div>
      <div className="flex-1 space-y-1.5">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={onFile}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onPick}
            disabled={busy}
          >
            <Upload className="size-4" aria-hidden />
            {hasAvatar ? "Replace" : "Upload"}
          </Button>
          {hasAvatar && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onRemove}
              disabled={busy}
            >
              <Trash2 className="size-4" aria-hidden />
              Remove
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          JPEG / PNG / WebP, up to 2 MB. Shown across the dashboard,
          mobile PWA, and push notifications.
        </p>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}
