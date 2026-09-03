import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

/**
 * POST /api/resume/optimize — queues the resume optimization workflow.
 * Accepts either { jobId } (job-card flow) or { jobTitle, jobDescription }
 * (manual paste flow). The user id always comes from the verified session,
 * never from the request body.
 */
export async function POST(request: NextRequest) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ success: false, message: "Unauthorized" }, { status: 401 });
  }

  let body: { jobId?: string; jobTitle?: string; jobDescription?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ success: false, message: "Invalid request body." }, { status: 400 });
  }

  if (!body.jobId && !(body.jobTitle && body.jobDescription)) {
    return NextResponse.json(
      { success: false, message: "Provide either a jobId or both jobTitle and jobDescription." },
      { status: 400 }
    );
  }

  try {
    const backendResponse = await fetch(`${BACKEND_URL}/workflows/resume-optimize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Secret": process.env.INTERNAL_API_SECRET || "",
      },
      body: JSON.stringify({
        user_id: session.user.id,
        job_id: body.jobId,
        job_title: body.jobTitle,
        job_description: body.jobDescription,
      }),
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to queue resume optimization.";
    return NextResponse.json({ success: false, message }, { status: 502 });
  }
}
