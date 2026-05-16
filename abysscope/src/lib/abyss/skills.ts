import fs from "fs";
import path from "path";
import { abyssPath } from "./paths";
import { readYaml, writeYaml, readMarkdown } from "./io";
import { listBots } from "./bots";

export interface SkillConfig {
  name: string;
  type: "mcp" | "cli";
  status: string;
  description: string;
  emoji?: string;
  allowed_tools: string[];
  environment_variables: string[];
  environment_variable_values: Record<string, string>;
  required_commands: string[];
  install_hints: Record<string, string>;
}

const BUILTIN_SKILL_NAMES = new Set([
  "code_review",
  "conversation_search",
  "gcalendar",
  "gmail",
  "image",
  "imessage",
  "jira",
  "qmd",
  "reminders",
  "supabase",
  "translate",
  "twitter",
]);

export function isBuiltinSkill(name: string): boolean {
  return BUILTIN_SKILL_NAMES.has(name);
}

export function listSkills(): SkillConfig[] {
  const skillsDir = abyssPath("skills");
  try {
    const entries = fs.readdirSync(skillsDir, { withFileTypes: true });
    return entries
      .filter((e) => e.isDirectory())
      .map((e) => {
        const skillYaml = readYaml<SkillConfig>(
          path.join(skillsDir, e.name, "skill.yaml"),
        );
        if (!skillYaml) return null;
        return { ...skillYaml, name: skillYaml.name || e.name };
      })
      .filter((s): s is SkillConfig => s !== null);
  } catch {
    return [];
  }
}

export function getSkill(name: string): {
  config: SkillConfig | null;
  skillMarkdown: string;
  mcpConfig: Record<string, unknown> | null;
} {
  const skillDir = abyssPath("skills", name);
  const config = readYaml<SkillConfig>(path.join(skillDir, "skill.yaml"));
  const skillMarkdown = readMarkdown(path.join(skillDir, "SKILL.md"));
  let mcpConfig: Record<string, unknown> | null = null;
  try {
    const mcpContent = fs.readFileSync(
      path.join(skillDir, "mcp.json"),
      "utf-8",
    );
    mcpConfig = JSON.parse(mcpContent);
  } catch {
    // no mcp.json
  }
  return { config, skillMarkdown, mcpConfig };
}

export function createSkill(
  name: string,
  config: Partial<SkillConfig>,
  skillMarkdown: string,
): boolean {
  const skillDir = abyssPath("skills", name);
  if (fs.existsSync(skillDir)) return false;
  fs.mkdirSync(skillDir, { recursive: true });
  const fullConfig: SkillConfig = {
    name,
    type: "cli",
    status: "active",
    description: "",
    allowed_tools: [],
    environment_variables: [],
    environment_variable_values: {},
    required_commands: [],
    install_hints: {},
    ...config,
  };
  writeYaml(path.join(skillDir, "skill.yaml"), fullConfig);
  fs.writeFileSync(path.join(skillDir, "SKILL.md"), skillMarkdown);
  return true;
}

export function updateSkill(
  name: string,
  config: Partial<SkillConfig>,
  skillMarkdown?: string,
): boolean {
  const skillDir = abyssPath("skills", name);
  if (!fs.existsSync(skillDir)) return false;
  const existing = readYaml<SkillConfig>(path.join(skillDir, "skill.yaml"));
  if (!existing) return false;
  writeYaml(path.join(skillDir, "skill.yaml"), { ...existing, ...config });
  if (skillMarkdown !== undefined) {
    fs.writeFileSync(path.join(skillDir, "SKILL.md"), skillMarkdown);
  }
  return true;
}

export function deleteSkill(name: string): boolean {
  const skillDir = abyssPath("skills", name);
  try {
    fs.rmSync(skillDir, { recursive: true, force: true });
    return true;
  } catch {
    return false;
  }
}

export function getSkillUsageByBots(): Record<string, string[]> {
  const bots = listBots();
  const usage: Record<string, string[]> = {};
  for (const bot of bots) {
    for (const skill of bot.skills || []) {
      if (!usage[skill]) usage[skill] = [];
      usage[skill].push(bot.name);
    }
  }
  return usage;
}
