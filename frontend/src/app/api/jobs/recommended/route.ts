import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

const DEFAULT_LIMIT = 30;
const MAX_LIMIT = 50;

/**
 * GET /api/jobs/recommended — proxies to the FastAPI backend, deriving the
 * user id from the verified session instead of trusting a client-supplied one.
 *
 * `limit` is passed through (clamped) so the Jobs page can ask for enough
 * matches to paginate over, without re-running the LLM ranker on each page turn.
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
      limit: String(limit),
    });

    const backendResponse = await fetch(`${BACKEND_URL}/jobs/recommended?${params.toString()}`, {
      headers: {
        "X-Internal-Secret": process.env.INTERNAL_API_SECRET || "",
      },
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to fetch recommended jobs.";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
