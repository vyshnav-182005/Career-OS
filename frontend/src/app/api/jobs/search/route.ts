import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;

/**
 * GET /api/jobs/search — proxies job search to the FastAPI backend, deriving
 * the user id from the verified session rather than trusting the client.
 *
 * The user id matters here even though search itself isn't personalized: the
 * backend scores every result against that user's profile so search cards can
 * show the same match percentage the recommendation cards do.
 */
export async function GET(request: NextRequest) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const requestedLimit = Number(request.nextUrl.searchParams.get("limit"));
  const limit =
    Number.isFinite(requestedLimit) && requestedLimit > 0
      ? Math.min(Math.trunc(requestedLimit), MAX_LIMIT)
      : DEFAULT_LIMIT;

  try {
    const params = new URLSearchParams({
      user_id: session.user.id,
      q: request.nextUrl.searchParams.get("q") || "",
      limit: String(limit),
    });

    const backendResponse = await fetch(`${BACKEND_URL}/jobs/search?${params.toString()}`, {
      headers: {
        "X-Internal-Secret": process.env.INTERNAL_API_SECRET || "",
      },
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to search jobs.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
