import { createClient as createSupabaseClient } from "@supabase/supabase-js";

/**
 * Creates a Supabase client for use in Server Components, Route Handlers,
 * and Server Actions. Uses the service key to bypass RLS — all auth
 * is handled by Auth.js at the application layer.
 */
export function createClient() {
  return createSupabaseClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_KEY!
  );
}
