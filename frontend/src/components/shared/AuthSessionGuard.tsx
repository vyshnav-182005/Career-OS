"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

const sessionKey = "career-os-auth-session";

/**
 * Auth cookies are shared by all tabs, but this marker is scoped to one tab.
 * When a new tab is opened without the marker, any stale cookie is cleared so
 * the user is required to sign in again.
 */
export default function AuthSessionGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const supabase = createClient();
    let cancelled = false;

    async function validateBrowserSession() {
      const { data: { session } } = await supabase.auth.getSession();

      if (!session) {
        sessionStorage.removeItem(sessionKey);
        return;
      }

      if (sessionStorage.getItem(sessionKey) === "active") return;

      await supabase.auth.signOut();
      if (!cancelled && pathname !== "/login") {
        router.replace("/login");
      }
      router.refresh();
    }

    void validateBrowserSession();

    const { data: listener } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") {
        sessionStorage.setItem(sessionKey, "active");
      }
      if (event === "SIGNED_OUT") {
        sessionStorage.removeItem(sessionKey);
      }
    });

    return () => {
      cancelled = true;
      listener.subscription.unsubscribe();
    };
  }, [pathname, router]);

  return <>{children}</>;
}
