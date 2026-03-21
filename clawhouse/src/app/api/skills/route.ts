import { NextRequest, NextResponse } from "next/server";
import {
  listSkills,
  getSkillUsageByBots,
  createSkill,
  isBuiltinSkill,
} from "@/lib/cclaw";

export async function GET() {
  const skills = listSkills();
  const usage = getSkillUsageByBots();

  const skillsWithUsage = skills.map((skill) => ({
    ...skill,
    usedBy: usage[skill.name] || [],
    isBuiltin: isBuiltinSkill(skill.name),
  }));

  return NextResponse.json(skillsWithUsage);
}

export async function POST(request: NextRequest) {
  const { name, config, skillMarkdown } = await request.json();
  if (!name) {
    return NextResponse.json({ error: "name is required" }, { status: 400 });
  }
  const created = createSkill(name, config || {}, skillMarkdown || "");
  if (!created) {
    return NextResponse.json(
      { error: "Skill already exists" },
      { status: 409 },
    );
  }
  return NextResponse.json({ success: true }, { status: 201 });
}
