import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * Backward-compat redirect.
 *
 * ``/mobile/sessions`` used to be the canonical chat-list URL; the
 * Phase 4 polish flattened it into ``/mobile``. Anyone with a stale
 * bookmark, an installed PWA whose ``start_url`` was the old path,
 * or a Service Worker push-cache pointing here lands one redirect
 * away instead of a 404.
 */
export default function MobileSessionsRedirect() {
  redirect("/mobile");
}
