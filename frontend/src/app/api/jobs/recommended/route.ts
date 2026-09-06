import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { BACKEND_UNREACHABLE, backendFetch, internalHeaders } from "@/lib/backendFetch";

// The backend re-ranks the shortlist with an LLM, which is bounded at 30s on
// its side (LLM_TIMEOUT_SECONDS) before it falls back to feature ranking.
// Without this, a deployment platform's default function limit could cut the
// proxy off first and turn a slow-but-succeeding request into an error.
export const maxDuration = 60;

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

    const backendResponse = await backendFetch(`/jobs/recommended?${params.toString()}`, {
      headers: internalHeaders(),
    });

    const data = await backendResponse.json();
    return NextResponse.json(data, { status: backendResponse.status });
  } catch (err) {
    // backendFetch only throws once every connection attempt failed, so this
    // is "backend not reachable", not "backend disagreed" - say that rather
    // than surfacing a raw fetch error like "ECONNREFUSED" to the user.
    console.error("GET /api/jobs/recommended - backend unreachable:", err);
    return NextResponse.json({ error: BACKEND_UNREACHABLE }, { status: 503 });
  }
}
