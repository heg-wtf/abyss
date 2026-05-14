import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * Root mobile entry.
 *
 * Phase 2 ships only the route skeleton — the rich chat UI arrives in
 * Phase 4. Until then, sending users to the session picker is the
 * sensible default: a fresh-install mobile user has no active session,
 * and a returning user wants to pick which conversation to resume.
 */
export default function MobileIndexPage() {
  redirect("/mobile/sessions");
}
