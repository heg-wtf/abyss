/**
 * "여기까지 읽음" inline divider for chat / routine detail screens.
 *
 * Anchored to the index of the first unread assistant message at
 * mount time and rendered as a hairline + label. Re-render is a
 * no-op past the initial paint — the position never shifts as the
 * user scrolls. New SSE-arrived messages are inherently read and
 * appear below the divider without retriggering it.
 */
export function UnreadDivider() {
  return (
    <li
      role="separator"
      aria-label="여기까지 읽음"
      className="flex items-center gap-2 px-1 py-1 text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400"
    >
      <span aria-hidden className="h-px flex-1 bg-emerald-500/40" />
      <span>여기까지 읽음</span>
      <span aria-hidden className="h-px flex-1 bg-emerald-500/40" />
    </li>
  );
}
