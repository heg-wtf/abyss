"use client";

import * as React from "react";
import { Bell, BellOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useWebPushContext } from "@/components/web-push-provider";

/**
 * Web Push enable / disable toggle.
 *
 * Reads from the single ``useWebPush`` instance hoisted into
 * ``WebPushProvider`` at the root layout — visibility tracking +
 * notification-click routing must work on every page, not just the
 * surface that happens to render the bell.
 *
 * Used to live inside the now-deleted ``MobileSessionsScreen``. The
 * drawer footer mounts it so it stays one tap away from anywhere
 * inside ``/mobile``.
 */
export function PushToggle() {
  const push = useWebPushContext();
  const [open, setOpen] = React.useState(false);

  const subscribed = push.status === "subscribed";
  const unsupported = push.status === "unsupported";

  return (
    <>
      <button
        type="button"
        aria-label={subscribed ? "Notifications on" : "Notifications off"}
        onClick={() => setOpen(true)}
        className="flex size-9 items-center justify-center rounded-md border bg-background text-foreground transition-colors hover:bg-muted"
        title={`push: ${push.status}`}
      >
        {subscribed ? (
          <Bell className="size-4" />
        ) : (
          <BellOff className="size-4 text-muted-foreground" />
        )}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Push notifications</DialogTitle>
            <DialogDescription className="text-xs">
              The phone fires a notification when a bot replies, a cron
              job finishes, or a heartbeat reports something worth
              looking at. Active tabs are skipped so you don&apos;t get
              double-notified.
            </DialogDescription>
          </DialogHeader>

          <p className="rounded-md bg-muted/40 px-3 py-2 text-xs">
            Current status: <span className="font-mono">{push.status}</span>
          </p>

          {unsupported && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
              This browser / origin does not support Web Push. Open the
              dashboard over HTTPS (or localhost) in iOS Safari 16.4+,
              Chrome, or Edge.
            </p>
          )}

          {push.status === "permission-denied" && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
              Notifications are blocked for this site. Re-enable them in
              your browser settings, then reload the page.
            </p>
          )}

          <p className="text-xs text-muted-foreground">
            iOS Safari requires the dashboard be added to your home
            screen before push notifications work. Tap{" "}
            <span className="font-medium">Share → Add to Home Screen</span>{" "}
            once, then open the icon to register.
          </p>

          {push.error && (
            <p className="text-xs text-destructive">{push.error}</p>
          )}

          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Close
            </Button>
            {subscribed ? (
              <Button
                variant="outline"
                onClick={() => push.disable()}
                disabled={push.pending}
              >
                {push.pending ? "Disabling…" : "Disable"}
              </Button>
            ) : (
              <Button
                onClick={() => push.enable()}
                disabled={
                  push.pending ||
                  push.status === "permission-denied" ||
                  push.status === "unsupported"
                }
              >
                {push.pending ? "Enabling…" : "Enable"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
