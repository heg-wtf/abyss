import { listSkills, getSkillUsageByBots, isBuiltinSkill } from "@/lib/cclaw";
import { SkillCard } from "@/components/skill-card";

export const dynamic = "force-dynamic";

export default function CustomSkillsPage() {
  const skills = listSkills().filter((s) => !isBuiltinSkill(s.name));
  const usage = getSkillUsageByBots();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Custom Skills</h1>
        <p className="text-muted-foreground text-sm">
          {skills.length} user-created skill{skills.length !== 1 ? "s" : ""} in
          ~/.cclaw/skills/
        </p>
      </div>

      {skills.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No custom skills found. Custom skills are created in ~/.cclaw/skills/
          and are not part of the built-in skill set.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {skills.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              usedBy={usage[skill.name] || []}
            />
          ))}
        </div>
      )}
    </div>
  );
}
