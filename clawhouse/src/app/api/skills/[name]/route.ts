import { NextRequest, NextResponse } from "next/server";
import {
  getSkill,
  updateSkill,
  deleteSkill,
  isBuiltinSkill,
} from "@/lib/cclaw";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const skill = getSkill(name);
  return NextResponse.json(skill);
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  if (isBuiltinSkill(name)) {
    return NextResponse.json(
      { error: "Cannot edit built-in skills" },
      { status: 403 },
    );
  }
  const { config, skillMarkdown } = await request.json();
  const updated = updateSkill(name, config || {}, skillMarkdown);
  if (!updated) {
    return NextResponse.json({ error: "Skill not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true });
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  if (isBuiltinSkill(name)) {
    return NextResponse.json(
      { error: "Cannot delete built-in skills" },
      { status: 403 },
    );
  }
  const deleted = deleteSkill(name);
  if (!deleted) {
    return NextResponse.json({ error: "Skill not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true });
}
