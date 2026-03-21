"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

interface BotSummary {
  name: string;
  display_name: string;
  telegram_botname: string;
}

export function Sidebar() {
  const pathname = usePathname();
  const [bots, setBots] = useState<BotSummary[]>([]);
  const [botsOpen, setBotsOpen] = useState(true);
  const [skillsOpen, setSkillsOpen] = useState(true);

  useEffect(() => {
    fetch("/api/bots")
      .then((r) => r.json())
      .then((data) => setBots(data))
      .catch(() => {});
  }, []);

  const botsActive = pathname.startsWith("/bots");
  const skillsActive = pathname.startsWith("/skills");

  return (
    <aside className="flex h-screen w-56 flex-col border-r bg-muted/30">
      <div className="flex h-14 items-center border-b px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <img src="/logo.png" alt="ClawHouse" className="h-8 w-auto" />
          <span>ClawHouse</span>
        </Link>
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
            <div className="ml-8 space-y-0.5">
              {bots.map((bot) => (
                <Link
                  key={bot.name}
                  href={`/bots/${bot.name}`}
                  className={cn(
                    "block rounded-md px-3 py-1.5 text-sm transition-colors truncate",
                    pathname.startsWith(`/bots/${bot.name}`)
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                  )}
                >
                  {bot.display_name || bot.telegram_botname || bot.name}
                </Link>
              ))}
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
                  "block rounded-md px-3 py-1.5 text-sm transition-colors",
                  pathname === "/skills/builtin"
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                Built-in
              </Link>
              <Link
                href="/skills/custom"
                className={cn(
                  "block rounded-md px-3 py-1.5 text-sm transition-colors",
                  pathname === "/skills/custom"
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                Custom
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
      <div className="border-t p-3 flex justify-end">
        <ThemeToggle />
      </div>
    </aside>
  );
}
