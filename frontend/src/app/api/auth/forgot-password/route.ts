import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY!
);

/**
 * Placeholder — replace with your preferred email service
 * (Resend, SendGrid, Nodemailer, etc.)
 */
async function sendResetEmail(email: string, resetUrl: string) {
  console.log(`\n========== PASSWORD RESET EMAIL ==========`);
  console.log(`To: ${email}`);
  console.log(`Reset URL: ${resetUrl}`);
  console.log(`==========================================\n`);
}

export async function POST(request: NextRequest) {
  try {
    const { email } = await request.json();

    if (!email) {
      return NextResponse.json(
        { error: "Email is required." },
        { status: 400 }
      );
    }

    // Always return success to avoid email enumeration
    const successResponse = NextResponse.json({ success: true });

    // Look up user
    const { data: user } = await supabase
      .from("users")
      .select("id")
      .eq("email", email)
      .single();

    if (!user) {
      // User doesn't exist, but don't reveal that
      return successResponse;
    }

    // Generate reset token
    const rawToken = crypto.randomBytes(32).toString("hex");
    const tokenHash = crypto
      .createHash("sha256")
      .update(rawToken)
      .digest("hex");

    // Store token (expires in 1 hour)
    const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();

    // Delete any existing tokens for this user
    await supabase
      .from("password_reset_tokens")
      .delete()
      .eq("user_id", user.id);

    // Insert new token
    await supabase.from("password_reset_tokens").insert({
      token_hash: tokenHash,
      user_id: user.id,
      expires_at: expiresAt,
    });

    // Build reset URL
    const origin =
      request.headers.get("origin") ||
      process.env.NEXT_PUBLIC_APP_URL ||
      "http://localhost:3000";
    const resetUrl = `${origin}/reset-password?token=${rawToken}`;

    await sendResetEmail(email, resetUrl);

    return successResponse;
  } catch (err) {
    console.error("Forgot password error:", err);
    return NextResponse.json(
      { error: "An unexpected error occurred." },
      { status: 500 }
    );
  }
}
