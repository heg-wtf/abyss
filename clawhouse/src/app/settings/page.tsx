import { getConfig, getGlobalMemory } from "@/lib/cclaw";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const dynamic = "force-dynamic";

export default function SettingsPage() {
  const config = getConfig();
  const globalMemory = getGlobalMemory();

  if (!config) {
    return <p className="text-muted-foreground">Config not found</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground text-sm">Global configuration</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">General</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Timezone</span>
              <span className="font-mono">{config.timezone}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Language</span>
              <span>{config.language}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Log Level</span>
              <span className="font-mono">
                {config.settings?.log_level || "INFO"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Command Timeout</span>
              <span className="font-mono">
                {config.settings?.command_timeout || 300}s
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Registered Bots</CardTitle>
            <CardDescription className="text-xs">
              {config.bots.length} bots in config.yaml
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              {config.bots.map((bot) => (
                <div
                  key={bot.name}
                  className="flex justify-between items-center"
                >
                  <span className="font-medium">{bot.name}</span>
                  <span className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
                    {bot.path}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Global Memory</CardTitle>
          <CardDescription>
            GLOBAL_MEMORY.md — Shared read-only memory for all bots
          </CardDescription>
        </CardHeader>
        <CardContent>
          {globalMemory ? (
            <pre className="text-sm whitespace-pre-wrap bg-muted p-4 rounded-md">
              {globalMemory}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">
              No global memory content
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
