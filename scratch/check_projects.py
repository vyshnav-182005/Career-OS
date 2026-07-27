import sys
from backend.db.supabase_client import get_supabase_client
client = get_supabase_client()
res = client.table('profiles').select('user_id, profile_data').execute()
for row in res.data:
    p = row.get('profile_data', {})
    if not p: continue
    resume = p.get('original_resume', {})
    projects = resume.get('projects', [])
    print(f"User: {row['user_id']}")
    print(f"Projects ({len(projects)}): {[pr.get('name') for pr in projects]}")
