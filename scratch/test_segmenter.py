import asyncio
from backend.db.supabase_client import get_supabase_client
from backend.services.document_segmenter import segment_resume

def main():
    client = get_supabase_client()
    res = client.table('profiles').select('user_id, profile_data').execute()
    for row in res.data:
        p = row.get('profile_data', {})
        if not p: continue
        resume = p.get('original_resume', {})
        personal = resume.get('personal_info', {}) or {}
        if personal.get('name'):
            print(f"Found user: {personal.get('name')}")
            # Try to fetch their resume from storage
            user_id = row['user_id']
            try:
                # We need to find the filename. Let's just list the bucket.
                files = client.storage.from_("resumes").list(user_id)
                if files:
                    for f in files:
                        if f['name'].endswith('.pdf'):
                            file_path = f"{user_id}/{f['name']}"
                            file_bytes = client.storage.from_("resumes").download(file_path)
                            segments = segment_resume(file_bytes, "application/pdf")
                            print("=== ALL SECTIONS ===")
                            for k, v in segments.items():
                                print(f"[{k.upper()}]\n{v}\n")
                            print("======================")
                            return
            except Exception as e:
                print(e)

if __name__ == '__main__':
    main()
