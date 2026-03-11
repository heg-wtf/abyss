import { NextRequest, NextResponse } from "next/server";
import { getCronJobs, updateCronJobs } from "@/lib/cclaw";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const jobs = getCronJobs(name);
  return NextResponse.json({ jobs });
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const { jobs } = await request.json();
  updateCronJobs(name, jobs);
  return NextResponse.json({ success: true });
}
