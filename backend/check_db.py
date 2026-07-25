import asyncio
from backend.db.supabase_client import get_supabase_client

def main():
    client = get_supabase_client()
    res = client.table("profiles").select("*").order("created_at", desc=True).limit(1).execute()
    if res.data:
        profile = res.data[0]
        p_data = profile.get("profile_data", {})
        original = p_data.get("original_resume", {})
        personal_info = original.get("personal_info", {})
        print("GitHub URL extracted:", personal_info.get("github"))
        projects = original.get("projects", [])
        print(f"Total projects in profile: {len(projects)}")
        for p in projects:
            print("-", p.get("name"), "URL:", p.get("url"))
    else:
        print("No profiles found")

if __name__ == "__main__":
    main()
