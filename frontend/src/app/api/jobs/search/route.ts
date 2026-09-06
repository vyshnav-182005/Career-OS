import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { BACKEND_UNREACHABLE, backendFetch, internalHeaders } from "@/lib/backendFetch";

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

    const backendResponse = await backendFetch(`/jobs/search?${params.toString()}`, {
      headers: internalHeaders(),
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    console.error("GET /api/jobs/search - backend unreachable:", err);
    return NextResponse.json({ error: BACKEND_UNREACHABLE }, { status: 503 });
  }
}
