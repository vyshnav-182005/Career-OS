import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import bcrypt from "bcryptjs";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY!
);

export async function POST(request: NextRequest) {
  try {
    const { token, password } = await request.json();

    if (!token || !password) {
      return NextResponse.json(
        { error: "Token and password are required." },
        { status: 400 }
      );
    }

    if (password.length < 8) {
      return NextResponse.json(
        { error: "Password must be at least 8 characters." },
        { status: 400 }
      );
    }

    // Hash the incoming token to compare with stored hash
    const tokenHash = crypto
      .createHash("sha256")
      .update(token)
      .digest("hex");

    // Look up the token
    const { data: resetRecord, error: lookupError } = await supabase
      .from("password_reset_tokens")
      .select("user_id, expires_at")
      .eq("token_hash", tokenHash)
      .single();

    if (lookupError || !resetRecord) {
      return NextResponse.json(
        { error: "Invalid or expired reset link." },
        { status: 400 }
      );
    }

    // Check expiry
    if (new Date(resetRecord.expires_at) < new Date()) {
      // Clean up expired token
      await supabase
        .from("password_reset_tokens")
        .delete()
        .eq("token_hash", tokenHash);

      return NextResponse.json(
        { error: "This reset link has expired. Please request a new one." },
        { status: 400 }
      );
    }

    // Hash new password and update user
    const hashedPassword = await bcrypt.hash(password, 12);

    const { error: updateError } = await supabase
      .from("users")
      .update({ hashed_password: hashedPassword })
      .eq("id", resetRecord.user_id);

    if (updateError) {
      console.error("Failed to update password:", updateError);
      return NextResponse.json(
        { error: "Failed to update password. Please try again." },
        { status: 500 }
      );
    }

    // Delete used token
    await supabase
      .from("password_reset_tokens")
      .delete()
      .eq("token_hash", tokenHash);

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("Reset password error:", err);
    return NextResponse.json(
      { error: "An unexpected error occurred." },
      { status: 500 }
    );
  }
}
