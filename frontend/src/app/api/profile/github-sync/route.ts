import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { BACKEND_UNREACHABLE, backendFetch, internalHeaders } from "@/lib/backendFetch";

// The scan walks every page of the user's repos and may regenerate the LLM
// summary, so it outlives a default serverless function limit on a large account.
export const maxDuration = 60;

/**
 * POST /api/profile/github-sync — re-scans the linked GitHub account and
 * reconciles the profile's project list, deriving the user id from the
 * verified session rather than trusting the client.
 */
export async function POST() {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let response: Response;
  try {
    response = await backendFetch("/user-profile/github/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...internalHeaders() },
      body: JSON.stringify({ user_id: session.user.id }),
    });
  } catch {
    return NextResponse.json({ success: false, message: BACKEND_UNREACHABLE }, { status: 503 });
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    return NextResponse.json(
      { success: false, message: body?.detail ?? "GitHub sync failed." },
      { status: response.status },
    );
  }

  // A sync that could not run answers 200 with success:false and a reason —
  // "GitHub is unreachable" is an outcome to show, not an error to swallow.
  return NextResponse.json(body);
}
