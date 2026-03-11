import { NextResponse } from "next/server";
import { listSkills, getSkillUsageByBots } from "@/lib/cclaw";

export async function GET() {
  const skills = listSkills();
  const usage = getSkillUsageByBots();

  const skillsWithUsage = skills.map((skill) => ({
    ...skill,
    usedBy: usage[skill.name] || [],
  }));

  return NextResponse.json(skillsWithUsage);
}
