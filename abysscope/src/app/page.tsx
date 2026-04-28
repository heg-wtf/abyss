import Link from "next/link";
import {
  listBots,
  getCronJobs,
  getBotSessions,
  getSystemStatus,
  getConfig,
  listSkills,
  getDiskUsage,
} from "@/lib/abyss";
import { BotAvatar } from "@/components/bot-avatar";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ModelBadge } from "@/components/status-badge";
import { LiveStatus } from "@/components/live-status";
import { Separator } from "@/components/ui/separator";

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  const bots = listBots();
  const skills = listSkills();
  const status = getSystemStatus();
  const config = getConfig();

  const totalCronJobs = bots.reduce(
    (sum, bot) => sum + getCronJobs(bot.name).length,
    0,
  );
  const diskUsage = getDiskUsage();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground text-sm">abyss system overview</p>
        </div>
        <LiveStatus initialRunning={status.running} />
      </div>

      <div className="grid grid-cols-5 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Bots</CardDescription>
            <CardTitle className="text-3xl">{bots.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Skills</CardDescription>
            <CardTitle className="text-3xl">{skills.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Cron</CardDescription>
            <CardTitle className="text-3xl">{totalCronJobs}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Timezone</CardDescription>
            <CardTitle className="text-lg">
              {config?.timezone || "UTC"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Disk Usage</CardDescription>
            <CardTitle className="text-lg">
              {diskUsage.totalFormatted}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">~/.abyss Disk Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {diskUsage.breakdown.slice(0, 10).map((item) => {
              const percentage =
                diskUsage.totalBytes > 0
                  ? (item.bytes / diskUsage.totalBytes) * 100
                  : 0;
              return (
                <div key={item.name} className="flex items-center gap-3">
                  <span className="text-sm w-40 truncate font-mono">
                    {item.name}
                  </span>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full"
                      style={{ width: `${Math.max(percentage, 0.5)}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground w-20 text-right">
                    {item.formatted}
                  </span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Separator />

      <div>
        <h2 className="text-lg font-semibold mb-4">Bots</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {bots.map((bot) => {
            const cronJobs = getCronJobs(bot.name);
            const sessions = getBotSessions(bot.name);
            const lastSession = sessions
              .filter((s) => s.lastActivity)
              .sort(
                (a, b) =>
                  (b.lastActivity?.getTime() || 0) -
                  (a.lastActivity?.getTime() || 0),
              )[0];

            return (
              <Link key={bot.name} href={`/bots/${bot.name}`}>
                <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
                  <CardHeader className="pb-3">
                    <div className="flex items-center gap-3">
                      <BotAvatar
                        botName={bot.name}
                        displayName={bot.display_name || bot.telegram_botname || bot.name}
                        size="md"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <CardTitle className="text-base truncate">
                            {bot.display_name || bot.telegram_botname || bot.name}
                          </CardTitle>
                          <ModelBadge model={bot.model} />
                        </div>
                        <CardDescription className="text-xs">
                          {bot.telegram_username}
                        </CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {bot.personality && (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {bot.personality}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-1">
                      {(bot.skills || []).map((skill) => (
                        <Badge
                          key={skill}
                          variant="secondary"
                          className="text-xs"
                        >
                          {skill}
                        </Badge>
                      ))}
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {cronJobs.length > 0 &&
                          `${cronJobs.length} cron job${cronJobs.length > 1 ? "s" : ""}`}
                      </span>
                      <span>
                        {lastSession?.lastActivity &&
                          `Last: ${lastSession.lastActivity.toLocaleDateString()}`}
                      </span>
                    </div>
                    {bot.streaming && (
                      <Badge variant="outline" className="text-xs">
                        streaming
                      </Badge>
                    )}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
