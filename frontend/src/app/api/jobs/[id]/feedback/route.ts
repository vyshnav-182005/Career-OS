import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

/**
 * POST /api/jobs/[id]/feedback — proxies a thumbs up/down vote to FastAPI,
 * deriving the user id from the verified session instead of trusting a
 * client-supplied one.
 */
export async function POST(
  request: NextRequest,
  segmentData: { params: Promise<{ id: string }> }
) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ success: false, message: "Unauthorized" }, { status: 401 });
  }

  const { id } = await segmentData.params;

  let vote: unknown;
  try {
    const body = await request.json();
    vote = body?.vote;
  } catch {
    return NextResponse.json({ success: false, message: "Missing vote" }, { status: 400 });
  }

  if (vote !== "up" && vote !== "down") {
    return NextResponse.json({ success: false, message: "vote must be 'up' or 'down'" }, { status: 400 });
  }

  try {
    const params = new URLSearchParams({ user_id: session.user.id });
    const backendResponse = await fetch(
      `${BACKEND_URL}/jobs/${encodeURIComponent(id)}/feedback?${params.toString()}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Secret": process.env.INTERNAL_API_SECRET || "",
        },
        body: JSON.stringify({ vote }),
      }
    );

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to record feedback.";
    return NextResponse.json({ success: false, message }, { status: 502 });
  }
}
