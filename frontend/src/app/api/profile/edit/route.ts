import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { BACKEND_UNREACHABLE, backendFetch, internalHeaders } from "@/lib/backendFetch";

// Room for the save plus backendFetch's connect budget, so a platform default
// can't drop the user's edit mid-flight. See lib/backendFetch.ts.
export const maxDuration = 30;

/**
 * PUT /api/profile/edit — saves hand-edited profile sections (certifications,
 * publications, project bullets), deriving the user id from the verified
 * session rather than trusting the client with it.
 *
 * Sections the body leaves out are not touched by the backend, so the editor
 * can save one panel without restating the whole profile.
 */
export async function PUT(request: NextRequest) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json(
      { success: false, message: "Nothing to save." },
      { status: 400 },
    );
  }

  let response: Response;
  try {
    response = await backendFetch("/resume-management/profile/sections", {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...internalHeaders() },
      body: JSON.stringify({ ...body, user_id: session.user.id }),
    });
  } catch {
    return NextResponse.json(
      { success: false, message: BACKEND_UNREACHABLE },
      { status: 503 },
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    // A 422 carries the field rule the save broke (an empty project
    // description, say), which is worth showing rather than flattening.
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? String(detail[0].msg).replace(/^Value error, /, "")
          : "Could not save your changes.";

    return NextResponse.json({ success: false, message }, { status: response.status });
  }

  return NextResponse.json(data);
}
