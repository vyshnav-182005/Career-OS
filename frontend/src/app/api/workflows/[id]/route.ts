import { NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

/**
 * GET /api/workflows/[id] — proxies workflow status polling, scoping the
 * lookup to the verified session's user id so one user can't poll another
 * user's generated resume by guessing a workflow id.
 */
export async function GET(
  _request: Request,
  segmentData: { params: Promise<{ id: string }> }
) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ message: "Unauthorized" }, { status: 401 });
  }

  const { id } = await segmentData.params;

  try {
    const backendResponse = await fetch(
      `${BACKEND_URL}/workflows/${encodeURIComponent(id)}?user_id=${encodeURIComponent(session.user.id)}`,
      {
        headers: {
          "X-Internal-Secret": process.env.INTERNAL_API_SECRET || "",
        },
      }
    );

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to fetch workflow status.";
    return NextResponse.json({ message }, { status: 502 });
  }
}
