import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";

export const maxDuration = 300;

export async function POST(request: NextRequest) {
  /* ── 1. Authenticate ─────────────────────────────────────────── */
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json(
      { success: false, error: "Unauthorized" },
      { status: 401 }
    );
  }

  /* ── 2. Validate FormData ────────────────────────────────────── */
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid form data" },
      { status: 400 }
    );
  }

  const file = formData.get("file");
  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { success: false, error: "No file provided" },
      { status: 400 }
    );
  }

  /* ── 3. Append user_id and forward to FastAPI Gateway ───────── */
  formData.append("user_id", session.user.id);

  try {
    const backendResponse = await fetch("http://localhost:8000/resume-parsing/parse", {
      method: "POST",
      body: formData,
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      console.error("FastAPI Gateway error:", errorText);
      return NextResponse.json(
        { success: false, error: `Backend failed: ${backendResponse.statusText}` },
        { status: backendResponse.status }
      );
    }

    const parsed = await backendResponse.json();
    return NextResponse.json({
        success: true,
        parsed_resume: parsed.data,
        profile_intelligence: null,
    });

  } catch (err) {
    const message = err instanceof Error ? err.message : "Pipeline execution failed.";
    console.error("Pipeline error:", message);
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
