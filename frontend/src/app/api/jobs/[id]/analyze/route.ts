import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

/**
 * POST /api/jobs/[id]/analyze — proxies the fast job-fit analysis (optimized
 * project bullets + ATS score) to FastAPI, deriving the user id from the
 * verified session instead of trusting a client-supplied one.
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

  let forceRefresh = false;
  try {
    const body = await request.json();
    forceRefresh = Boolean(body?.forceRefresh);
  } catch {
    // No body provided — default to a normal (cached) analysis.
  }

  try {
    const params = new URLSearchParams({
      user_id: session.user.id,
      force_refresh: String(forceRefresh),
    });
    const backendResponse = await fetch(
      `${BACKEND_URL}/jobs/${encodeURIComponent(id)}/analyze?${params.toString()}`,
      {
        method: "POST",
        headers: {
          "X-Internal-Secret": process.env.INTERNAL_API_SECRET || "",
        },
      }
    );

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to analyze job fit.";
    return NextResponse.json({ success: false, message }, { status: 502 });
  }
}
