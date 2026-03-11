import { getConfig, getGlobalMemory } from "@/lib/cclaw";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { MemoryEditor } from "@/components/memory-editor";
import { SettingsEditor } from "@/components/settings-editor";

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

      <SettingsEditor initialConfig={config} />

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
              <div key={bot.name} className="flex justify-between items-center">
                <span className="font-medium">{bot.name}</span>
                <span className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
                  {bot.path}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <MemoryEditor
        title="Global Memory"
        description="GLOBAL_MEMORY.md — Shared read-only memory for all bots"
        initialContent={globalMemory}
        apiEndpoint="/api/global-memory"
      />
    </div>
  );
}
