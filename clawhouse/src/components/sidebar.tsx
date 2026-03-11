"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

const navigation = [
  { name: "Dashboard", href: "/", icon: "🏠" },
  {
    name: "Skills",
    icon: "🔧",
    children: [
      { name: "Built-in", href: "/skills/builtin" },
      { name: "Custom", href: "/skills/custom" },
    ],
  },
  { name: "Settings", href: "/settings", icon: "⚙️" },
  { name: "Logs", href: "/logs", icon: "📋" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-56 flex-col border-r bg-muted/30">
      <div className="flex h-14 items-center border-b px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <img src="/logo.png" alt="Clawhouse" className="h-8 w-auto" />
          <span>Clawhouse</span>
        </Link>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {navigation.map((item) => {
          if ("children" in item && item.children) {
            const isActive = pathname.startsWith("/skills");
            return (
              <div key={item.name}>
                <div
                  className={cn(
                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                    isActive
                      ? "text-foreground font-medium"
                      : "text-muted-foreground",
                  )}
                >
                  <span>{item.icon}</span>
                  <span>{item.name}</span>
                </div>
                <div className="ml-8 space-y-0.5">
                  {item.children.map((child) => (
                    <Link
                      key={child.href}
                      href={child.href}
                      className={cn(
                        "block rounded-md px-3 py-1.5 text-sm transition-colors",
                        pathname === child.href
                          ? "bg-accent text-accent-foreground font-medium"
                          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                      )}
                    >
                      {child.name}
                    </Link>
                  ))}
                </div>
              </div>
            );
          }

          const href = "href" in item ? item.href : "/";
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                pathname === href
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
              )}
            >
              <span>{item.icon}</span>
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>
      <div className="border-t p-3 flex items-center justify-between">
        <span className="text-xs text-muted-foreground">cclaw dashboard</span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
