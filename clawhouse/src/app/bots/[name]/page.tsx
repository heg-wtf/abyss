import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getBot,
  getCronJobs,
  getBotSessions,
  getBotMemory,
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
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ModelBadge } from "@/components/status-badge";
import { SessionList } from "@/components/session-list";
import { MemoryEditor } from "@/components/memory-editor";
import { CronEditor } from "@/components/cron-editor";

export const dynamic = "force-dynamic";

export default async function BotDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;
  const bot = getBot(name);
  if (!bot) return notFound();

  const cronJobs = getCronJobs(name);
  const sessions = getBotSessions(name);
  const memory = getBotMemory(name);
  const availableSkillNames = listSkills().map((skill) => skill.name);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/"
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          Dashboard
        </Link>
        <span className="text-muted-foreground">/</span>
        <h1 className="text-2xl font-bold">
          {bot.display_name || bot.telegram_botname || bot.name}
        </h1>
        <ModelBadge model={bot.model} />
        <Link href={`/bots/${name}/edit`} className="ml-auto">
          <Button variant="outline" size="sm">
            Edit
          </Button>
        </Link>
      </div>

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="cron">
            Cron{cronJobs.length > 0 && ` (${cronJobs.length})`}
          </TabsTrigger>
          <TabsTrigger value="sessions">
            Sessions{sessions.length > 0 && ` (${sessions.length})`}
          </TabsTrigger>
          <TabsTrigger value="memory">Memory</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Telegram</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Bot Name</span>
                  <span>{bot.telegram_botname}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Username</span>
                  <span>{bot.telegram_username}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Streaming</span>
                  <span>{bot.streaming ? "On" : "Off"}</span>
                </div>
                {bot.command_timeout && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Timeout</span>
                    <span>{bot.command_timeout}s</span>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Skills</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {(bot.skills || []).map((skill) => (
                    <Link key={skill} href={`/skills#${skill}`}>
                      <Badge
                        variant="secondary"
                        className="hover:bg-primary/20 cursor-pointer"
                      >
                        {skill}
                      </Badge>
                    </Link>
                  ))}
                  {(!bot.skills || bot.skills.length === 0) && (
                    <span className="text-sm text-muted-foreground">
                      No skills attached
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {bot.personality && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Personality</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap">{bot.personality}</p>
              </CardContent>
            </Card>
          )}

          {bot.role && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Role</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap">{bot.role}</p>
              </CardContent>
            </Card>
          )}

          {bot.goal && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Goal</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap">{bot.goal}</p>
              </CardContent>
            </Card>
          )}

          {bot.heartbeat && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Heartbeat</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Enabled</span>
                  <span>{bot.heartbeat.enabled ? "Yes" : "No"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Interval</span>
                  <span>{bot.heartbeat.interval_minutes} min</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Active Hours</span>
                  <span>
                    {bot.heartbeat.active_hours?.start} -{" "}
                    {bot.heartbeat.active_hours?.end}
                  </span>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="cron" className="mt-4">
          <CronEditor
            botName={name}
            initialJobs={cronJobs}
            availableSkills={availableSkillNames}
          />
        </TabsContent>

        <TabsContent value="sessions" className="mt-4">
          <SessionList
            botName={name}
            initialSessions={JSON.parse(JSON.stringify(sessions))}
          />
        </TabsContent>

        <TabsContent value="memory" className="mt-4">
          <MemoryEditor
            title="MEMORY.md"
            description="Bot long-term memory (read/written by Claude Code)"
            initialContent={memory}
            apiEndpoint={`/api/bots/${name}/memory`}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
