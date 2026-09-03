import { auth } from "@/auth";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import DashboardClient from "./DashboardClient";
import type { ProfileIntelligence } from "@/lib/types/resume";

export default async function DashboardPage() {
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }

  const user = session.user;
  const supabase = await createClient();

  // Fetch existing profile from Supabase
  const { data: profileRow } = await supabase
    .from("profiles")
    .select("profile_data, source_filename, resume_url")
    .eq("user_id", user.id)
    .single();

  const displayName =
    user.name ||
    user.email?.split("@")[0] ||
    "there";

  const avatarChar = displayName[0].toUpperCase();

  return (
    <DashboardClient
      displayName={displayName}
      avatarChar={avatarChar} 
      initialProfileIntelligence={profileRow?.profile_data as ProfileIntelligence | null}
      initialFilename={profileRow?.source_filename}
      initialResumeUrl={profileRow?.resume_url ?? null}
    />
  );
}
