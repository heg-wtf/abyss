import Link from "next/link";
import {
  listBots,
  getCronJobs,
  getBotSessions,
  getSystemStatus,
  getConfig,
  listSkills,
} from "@/lib/cclaw";
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground text-sm">cclaw system overview</p>
        </div>
        <LiveStatus initialRunning={status.running} />
      </div>

      <div className="grid grid-cols-4 gap-4">
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
            <CardDescription>Cron Jobs</CardDescription>
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
      </div>

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
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">
                        {bot.display_name || bot.telegram_botname || bot.name}
                      </CardTitle>
                      <ModelBadge model={bot.model} />
                    </div>
                    <CardDescription className="text-xs">
                      {bot.telegram_username}
                    </CardDescription>
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
