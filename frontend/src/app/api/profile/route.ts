import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/auth";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY!
);

/**
 * GET /api/profile — returns the authenticated user's profile data.
 * Used by client-side polling in the dashboard.
 */
export async function GET(request: NextRequest) {
  const session = await auth();

  if (!session?.user?.id) {
    return NextResponse.json(
      { error: "Unauthorized" },
      { status: 401 }
    );
  }

  const { data, error } = await supabase
    .from("profiles")
    .select("profile_data, resume_url")
    .eq("user_id", session.user.id)
    .single();

  if (error && error.code !== "PGRST116") {
    // PGRST116 = no rows found (not an error for us)
    console.error("Failed to fetch profile:", error);
    return NextResponse.json(
      { error: "Failed to fetch profile." },
      { status: 500 }
    );
  }

  return NextResponse.json({
    profile_data: data?.profile_data ?? null,
    resume_url: data?.resume_url ?? null,
  });
}
