import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SkillTypeBadge } from "@/components/status-badge";
import { SkillConfig } from "@/lib/cclaw";

export function SkillCard({
  skill,
  usedBy,
}: {
  skill: SkillConfig;
  usedBy: string[];
}) {
  return (
    <Card id={skill.name}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">
            {skill.emoji && `${skill.emoji} `}
            {skill.name}
          </CardTitle>
          <SkillTypeBadge type={skill.type} />
        </div>
        <CardDescription className="text-xs">
          {skill.description}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {usedBy.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Used by</p>
            <div className="flex flex-wrap gap-1">
              {usedBy.map((botName) => (
                <Badge key={botName} variant="secondary" className="text-xs">
                  {botName}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {skill.allowed_tools && skill.allowed_tools.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">
              Tools ({skill.allowed_tools.length})
            </p>
            <div className="flex flex-wrap gap-1">
              {skill.allowed_tools.slice(0, 5).map((tool) => (
                <Badge
                  key={tool}
                  variant="outline"
                  className="text-xs font-mono"
                >
                  {tool.length > 30 ? tool.substring(0, 30) + "..." : tool}
                </Badge>
              ))}
              {skill.allowed_tools.length > 5 && (
                <Badge variant="outline" className="text-xs">
                  +{skill.allowed_tools.length - 5} more
                </Badge>
              )}
            </div>
          </div>
        )}

        {skill.required_commands && skill.required_commands.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Requires</p>
            <div className="flex flex-wrap gap-1">
              {skill.required_commands.map((cmd) => (
                <Badge
                  key={cmd}
                  variant="outline"
                  className="text-xs font-mono"
                >
                  {cmd}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {skill.environment_variables &&
          skill.environment_variables.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Env Vars</p>
              <div className="flex flex-wrap gap-1">
                {skill.environment_variables.map((env) => (
                  <Badge
                    key={env}
                    variant="outline"
                    className="text-xs font-mono"
                  >
                    {env}
                  </Badge>
                ))}
              </div>
            </div>
          )}
      </CardContent>
    </Card>
  );
}
