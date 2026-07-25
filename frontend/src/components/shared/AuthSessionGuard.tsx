"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "next-auth/react";

const sessionKey = "career-os-auth-session";

/**
 * Auth cookies are shared by all tabs, but this marker is scoped to one tab.
 * When a new tab is opened without the marker, any stale cookie is cleared so
 * the user is required to sign in again.
 */
export default function AuthSessionGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: session, status } = useSession();

  useEffect(() => {
    const publicPages = ["/", "/login", "/register", "/forgot-password", "/reset-password"];
    const isPublicPage = publicPages.includes(pathname);

    if (status === "unauthenticated" && !isPublicPage) {
      sessionStorage.removeItem(sessionKey);
      router.replace("/login");
    } else if (status === "authenticated") {
      sessionStorage.setItem(sessionKey, "active");
    }
  }, [status, pathname, router]);

  return <>{children}</>;
}
