import { Badge } from "@/components/ui/badge";

export function StatusBadge({ running }: { running: boolean }) {
  return (
    <Badge variant={running ? "default" : "secondary"}>
      <span
        className={`mr-1 inline-block h-2 w-2 rounded-full ${running ? "bg-green-400" : "bg-gray-400"}`}
      />
      {running ? "Running" : "Stopped"}
    </Badge>
  );
}

export function ModelBadge({ model }: { model: string }) {
  return (
    <Badge variant="outline" className="text-xs">
      {model || "sonnet"}
    </Badge>
  );
}

export function SkillTypeBadge({ type }: { type?: string }) {
  // Some skill entries (e.g. github-imported skills without a
  // ``skill.yaml``) don't carry a ``type`` field. Render nothing
  // rather than crashing on ``type.toUpperCase()``, which is what
  // surfaced as the "Application error: a client-side exception"
  // on /skills/custom for users with such skills installed.
  if (!type) return null;
  return (
    <Badge variant={type === "mcp" ? "default" : "outline"} className="text-xs">
      {type.toUpperCase()}
    </Badge>
  );
}
