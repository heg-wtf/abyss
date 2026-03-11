import Link from "next/link";
import { notFound } from "next/navigation";
import { getBot, getCronJobs, getBotSessions, getBotMemory } from "@/lib/cclaw";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { ModelBadge } from "@/components/status-badge";

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
      </div>

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="cron">
            Cron Jobs{cronJobs.length > 0 && ` (${cronJobs.length})`}
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
          {cronJobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No cron jobs configured
            </p>
          ) : (
            <div className="space-y-3">
              {cronJobs.map((job) => (
                <Card key={job.name}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm">{job.name}</CardTitle>
                      <Badge
                        variant={job.enabled ? "default" : "secondary"}
                        className="text-xs"
                      >
                        {job.enabled ? "Active" : "Disabled"}
                      </Badge>
                    </div>
                    <CardDescription className="font-mono text-xs">
                      {job.schedule}
                      {job.timezone && ` (${job.timezone})`}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm">{job.message}</p>
                    {job.model && (
                      <Badge variant="outline" className="text-xs mt-2">
                        {job.model}
                      </Badge>
                    )}
                    {job.skills && job.skills.length > 0 && (
                      <div className="flex gap-1 mt-2">
                        {job.skills.map((s) => (
                          <Badge
                            key={s}
                            variant="secondary"
                            className="text-xs"
                          >
                            {s}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="sessions" className="mt-4">
          {sessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active sessions</p>
          ) : (
            <div className="space-y-3">
              {sessions.map((session) => (
                <Card key={session.chatId}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-mono">
                        chat_{session.chatId}
                      </CardTitle>
                      {session.hasSessionId && (
                        <Badge variant="outline" className="text-xs">
                          Active Session
                        </Badge>
                      )}
                    </div>
                    {session.lastActivity && (
                      <CardDescription className="text-xs">
                        Last activity:{" "}
                        {session.lastActivity.toLocaleDateString()}{" "}
                        {session.lastActivity.toLocaleTimeString()}
                      </CardDescription>
                    )}
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-1">
                      {session.conversationFiles.map((file) => (
                        <Badge
                          key={file}
                          variant="secondary"
                          className="text-xs font-mono"
                        >
                          {file.replace("conversation-", "").replace(".md", "")}
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="memory" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">MEMORY.md</CardTitle>
              <CardDescription>
                Bot long-term memory (read/written by Claude Code)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {memory ? (
                <pre className="text-sm whitespace-pre-wrap bg-muted p-4 rounded-md">
                  {memory}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No memory content
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
