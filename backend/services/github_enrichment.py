import asyncio
import httpx
import logging
from openai import AsyncOpenAI
from backend.config import settings
from backend.db.supabase_client import get_profile_data, get_supabase_client
from backend.services.workflow_orchestrator import trigger_profile_intelligence_workflow
from backend.models.resume import Project

logger = logging.getLogger(__name__)

async def _fetch_github_repos(github_url: str) -> list[dict]:
    if not github_url:
        return []

    username = github_url.rstrip('/').split('/')[-1]
    if not username or username.lower() in ["github", "github.com", "http", "https"]:
        logger.info("Invalid or generic GitHub username extracted: %s", username)
        return []

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Career-OS-Agent",
    }
    
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    all_repos: list[dict] = []
    page = 1

    try:
        async with httpx.AsyncClient(headers=headers) as client:
            user_response = await client.get(f"https://api.github.com/users/{username}")
            if user_response.status_code != 200:
                logger.info("GitHub user not found: %s", username)
                return []

            while True:
                response = await client.get(
                    f"https://api.github.com/users/{username}/repos",
                    params={"per_page": 100, "page": page, "sort": "updated", "type": "owner"},
                )
                response.raise_for_status()
                repos = response.json()
                if not repos:
                    break
                all_repos.extend(repos)
                page += 1

            # Filter forks without commits
            async def _should_keep(repo):
                if not repo.get("fork"):
                    return True
                if not repo.get("size"):
                    return False
                url = f"https://api.github.com/repos/{repo['owner']['login']}/{repo['name']}/commits"
                try:
                    res = await client.get(url, params={"author": username, "per_page": 1})
                    if res.status_code == 200:
                        return len(res.json()) > 0
                    return False
                except Exception:
                    return False

            keep_results = await asyncio.gather(*[_should_keep(r) for r in all_repos])
            filtered_repos = [r for r, keep in zip(all_repos, keep_results) if keep]
            
            return filtered_repos
    except Exception as e:
        logger.error("Failed to fetch GitHub repos: %s", e)

    return []

async def _generate_github_summary(repos: list[dict]) -> str:
    if not repos:
        return "No public GitHub repositories found."
        
    repo_strings = []
    for r in repos[:30]:
        lang = r.get('language') or 'Unknown'
        desc = r.get('description') or 'No description'
        repo_strings.append(f"- {r.get('name')} ({lang}): {desc}")
        
    repos_text = "\n".join(repo_strings)
    
    prompt = f"""
Summarize this candidate's GitHub profile based on their public repositories.
Focus on their primary languages, the types of projects they build, and any notable patterns.
Keep the summary under 3 sentences.

Repositories:
{repos_text}
"""
    client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=60.0,
        max_retries=1,
    )
    
    try:
        completion = await client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"Error generating github summary: {e}")
        return "Candidate has several public GitHub repositories."

async def enrich_profile_with_github_projects(user_id: str, github_url: str):
    logger.info("Starting GitHub enrichment for user_id=%s, github_url=%s", user_id, github_url)
    
    repos = await _fetch_github_repos(github_url)
    
    profile_data = get_profile_data(user_id)
    if not profile_data or "original_resume" not in profile_data:
        logger.error("Profile data not found for user_id=%s to update with GitHub repos", user_id)
        return

    if not repos:
        logger.info("No GitHub repos found for user_id=%s", user_id)
        profile_data["github_summary"] = "No public GitHub repositories."
    else:
        logger.info("Found %d repos for user_id=%s", len(repos), user_id)
        
        projects = profile_data["original_resume"].get("projects", [])
        
        def normalize_name(n: str) -> str:
            return "".join(c.lower() for c in n if c.isalnum())

        for repo in repos:
            name = repo.get("name", "Unknown Repository")
            repo_url = repo.get("html_url")
            
            # Check if project exists by URL or normalized name
            existing_project = None
            for p in projects:
                if p.get("url") == repo_url or normalize_name(p.get("name") or "") == normalize_name(name):
                    existing_project = p
                    break
            
            if existing_project:
                # If we found it, ensure we attach the URL if it's missing
                if not existing_project.get("url") and repo_url:
                    existing_project["url"] = repo_url
                continue
                
            description = []
            if repo.get("description"):
                description.append(repo["description"])
                
            technologies = []
            if repo.get("language"):
                technologies.append(repo["language"])
                
            project = Project(
                name=name,
                description=description,
                technologies=technologies,
                url=repo_url
            )
            projects.append(project.model_dump())
            
        profile_data["original_resume"]["projects"] = projects
        
        # Generate summary
        github_summary = await _generate_github_summary(repos)
        profile_data["github_summary"] = github_summary
    
    client = get_supabase_client()
    try:
        client.table("profiles").update({"profile_data": profile_data}).eq("user_id", user_id).execute()
        logger.info("Successfully updated GitHub projects for user_id=%s", user_id)
    except Exception as e:
        logger.error("Failed to update profile with GitHub projects for user_id=%s: %s", user_id, e)


async def enrich_and_trigger_workflow(user_id: str, github_url: str):
    try:
        await enrich_profile_with_github_projects(user_id, github_url)
    except Exception as e:
        logger.error("Error during GitHub enrichment for user_id=%s: %s", user_id, e)
    
    await trigger_profile_intelligence_workflow(user_id)
