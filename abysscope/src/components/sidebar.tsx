"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { BotAvatar } from "@/components/bot-avatar";

interface BotSummary {
  name: string;
  display_name: string;
}

const STORAGE_KEY = "abysscope.sidebar.collapsed";

/**
 * Public entry point. Skips rendering on the `/mobile` route tree so
 * the mobile layout owns the full viewport. Wrapping the conditional
 * outside `SidebarImpl` keeps the hooks-rules invariant intact.
 */
export function Sidebar() {
  const pathname = usePathname();
  if (pathname.startsWith("/mobile")) {
    return null;
  }
  return <SidebarImpl />;
}

function SidebarImpl() {
  const pathname = usePathname();
  const [bots, setBots] = useState<BotSummary[]>([]);
  const [botsOpen, setBotsOpen] = useState(true);
  const [skillsOpen, setSkillsOpen] = useState(true);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  });

  const toggleCollapsed = (next: boolean) => {
    setCollapsed(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      // ignore (private mode etc.)
    }
  };

  useEffect(() => {
    fetch("/api/bots")
      .then((r) => r.json())
      .then((data) => setBots(data))
      .catch(() => {});
  }, []);

  const botsActive = pathname.startsWith("/bots");
  const skillsActive = pathname.startsWith("/skills");

  if (collapsed) {
    return (
      <aside className="flex h-screen w-14 flex-col border-r bg-muted/30">
        <div className="flex h-14 items-center justify-center border-b">
          <button
            type="button"
            onClick={() => toggleCollapsed(false)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Expand sidebar"
            title="Expand sidebar"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
        <nav className="flex-1 space-y-1 overflow-auto p-2">
          <CollapsedLink
            href="/"
            label="Dashboard"
            icon="🏠"
            active={pathname === "/"}
          />
          <CollapsedLink
            href="/mobile"
            label="Chats"
            icon="💬"
            active={false}
            newTab
          />
          <CollapsedLink
            href="/bots"
            label="Bots"
            icon="🤖"
            active={botsActive}
          />
          <CollapsedLink
            href="/skills/builtin"
            label="Skills"
            icon="🔧"
            active={skillsActive}
          />
          <CollapsedLink
            href="/settings"
            label="Settings"
            icon="⚙️"
            active={pathname === "/settings"}
          />
          <CollapsedLink
            href="/logs"
            label="Logs"
            icon="📋"
            active={pathname === "/logs"}
          />
        </nav>
      </aside>
    );
  }

  return (
    <aside className="flex h-screen w-56 flex-col border-r bg-muted/30">
      <div className="flex h-14 items-center justify-between border-b px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <img src="/logo-square.png" alt="Abysscope" className="size-6 object-contain" />
          <span>Abysscope</span>
        </Link>
        <button
          type="button"
          onClick={() => toggleCollapsed(true)}
          className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Collapse sidebar"
          title="Collapse sidebar"
        >
          <ChevronLeft className="size-4" />
        </button>
      </div>
      <nav className="flex-1 space-y-1 overflow-auto p-3">
        <Link
          href="/"
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
            pathname === "/"
              ? "bg-accent text-accent-foreground font-medium"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          <span>🏠</span>
          <span>Dashboard</span>
        </Link>

        <a
          href="/mobile"
          target="_blank"
          rel="noopener noreferrer"
          title="Open mobile chat in a new tab"
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
            "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          <span>💬</span>
          <span>Chats</span>
          <span className="ml-auto text-[10px] text-muted-foreground">↗</span>
        </a>

        <div>
          <button
            onClick={() => setBotsOpen(!botsOpen)}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              botsActive
                ? "text-foreground font-medium"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
            )}
          >
            <span
              className={cn(
                "text-xs transition-transform",
                botsOpen ? "rotate-90" : "",
              )}
            >
              ▶
            </span>
            <span>🤖</span>
            <span>Bots</span>
          </button>
          {botsOpen && (
            <div className="ml-4 space-y-0.5">
              {bots.map((bot) => (
                <Link
                  key={bot.name}
                  href={`/bots/${bot.name}`}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                    pathname.startsWith(`/bots/${bot.name}`)
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                  )}
                >
                  <BotAvatar
                    botName={bot.name}
                    displayName={bot.display_name || bot.name}
                    size="xs"
                  />
                  <span className="truncate">
                    {bot.display_name || bot.name}
                  </span>
                </Link>
              ))}
              <Link
                href="/bots/new"
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                  pathname === "/bots/new"
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                <span className="flex size-5 items-center justify-center rounded-md border text-xs text-muted-foreground">
                  +
                </span>
                <span className="truncate">New</span>
              </Link>
            </div>
          )}
        </div>

        <div>
          <button
            onClick={() => setSkillsOpen(!skillsOpen)}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              skillsActive
                ? "text-foreground font-medium"
                : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
            )}
          >
            <span
              className={cn(
                "text-xs transition-transform",
                skillsOpen ? "rotate-90" : "",
              )}
            >
              ▶
            </span>
            <span>🔧</span>
            <span>Skills</span>
          </button>
          {skillsOpen && (
            <div className="ml-8 space-y-0.5">
              <Link
                href="/skills/builtin"
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                  pathname === "/skills/builtin"
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                <span>📦</span>
                <span>Built-in</span>
              </Link>
              <Link
                href="/skills/custom"
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                  pathname === "/skills/custom"
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                <span>🧩</span>
                <span>Custom</span>
              </Link>
            </div>
          )}
        </div>

        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
            pathname === "/settings"
              ? "bg-accent text-accent-foreground font-medium"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          <span>⚙️</span>
          <span>Settings</span>
        </Link>

        <Link
          href="/logs"
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
            pathname === "/logs"
              ? "bg-accent text-accent-foreground font-medium"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          <span>📋</span>
          <span>Logs</span>
        </Link>
      </nav>
      <div className="border-t p-3">
        <span className="text-xs text-muted-foreground font-mono">
          {process.env.NEXT_PUBLIC_ABYSS_VERSION || "dev"}
          {process.env.NEXT_PUBLIC_ABYSS_COMMIT && (
            <span className="ml-1.5 opacity-70">
              ({process.env.NEXT_PUBLIC_ABYSS_COMMIT})
            </span>
          )}
        </span>
      </div>
    </aside>
  );
}

interface CollapsedLinkProps {
  href: string;
  label: string;
  icon: string;
  active: boolean;
  /** Open in a new tab via ``target="_blank"``. Used for the Chats entry
   * that points to the mobile PWA — convenient to leave a chat session
   * open side-by-side with the dashboard. */
  newTab?: boolean;
}

function CollapsedLink({
  href,
  label,
  icon,
  active,
  newTab = false,
}: CollapsedLinkProps) {
  const className = cn(
    "flex h-9 items-center justify-center rounded-md text-base transition-colors",
    active
      ? "bg-accent text-accent-foreground"
      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
  );
  if (newTab) {
    return (
      <a
        href={href}
        title={label}
        aria-label={label}
        target="_blank"
        rel="noopener noreferrer"
        className={className}
      >
        <span>{icon}</span>
      </a>
    );
  }
  return (
    <Link
      href={href}
      title={label}
      aria-label={label}
      className={className}
    >
      <span>{icon}</span>
    </Link>
  );
}
