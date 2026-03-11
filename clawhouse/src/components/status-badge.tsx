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

export function SkillTypeBadge({ type }: { type: string }) {
  return (
    <Badge variant={type === "mcp" ? "default" : "outline"} className="text-xs">
      {type.toUpperCase()}
    </Badge>
  );
}
