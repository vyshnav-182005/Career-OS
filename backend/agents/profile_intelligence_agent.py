import asyncio
import json
import logging
import re
import httpx
from openai import OpenAI

from backend.config import settings
from backend.db.supabase_client import get_profile_data, update_profile_intelligence
from backend.models.profile import (
    ProfileIntelligence,
    InferredJobRole,
)
from backend.models.resume import ParsedResume, Project

logger = logging.getLogger(__name__)


PROFILE_INTELLIGENCE_PROMPT = """\
You are a Profile Intelligence Agent. Analyze the candidate's resume and GitHub repositories.

Return a JSON object matching this EXACT schema (no markdown, no extra text):
{{
  "strengths": ["strength1", "strength2", ...],
  "preferred_job_roles": [
    {{
      "title": "Job title",
      "confidence": "High | Medium | Low",
      "reasoning": "Brief explanation"
    }}
  ],
  "github_project_summaries": {{
    "repository_name_1": ["Point 1", "Point 2", "... up to {max_points} points"],
    "repository_name_2": ["Point 1", "Point 2", "... up to {max_points} points"]
  }}
}}

Rules:
1. strengths: Extract only transferable professional strengths demonstrated across the resume.
   - Do not copy project titles or rewrite project descriptions.
   - Each strength should represent a reusable capability (e.g., "Agentic AI System Design", "Computer Vision", "Cloud Deployment", "REST API Development") rather than a specific application or project.
   - Keep each strength concise (2-5 words).
   - Deduplicate similar strengths.
   - Prioritize broad technical capabilities over project-specific implementations.
   - Limit to 8-12 strengths.
2. preferred_job_roles: Infer suitable job roles with confidence levels and reasoning.
3. github_project_summaries: For each NEW GitHub project (not in the resume), make a {max_points}-point summary of the project explaining the project and its technical depth. The format should be a list of strings matching the style of the resume projects.
4. Return ONLY valid JSON.

Candidate Data:

Resume (full):
{resume_json}

Resume Projects:
{resume_projects}

New GitHub Projects (not in resume):
{github_projects}
"""


async def _fetch_github_repos(github_url: str) -> list[dict]:
    """
    Fetch all repos for the candidate's GitHub username.
    Uses the candidate's GitHub URL from their resume.
    """
    if not github_url:
        logger.warning("No GitHub URL found in resume — skipping GitHub repo fetch")
        return []

    # Extract username from url (e.g., https://github.com/username)
    username = github_url.rstrip('/').split('/')[-1]
    if not username:
        return []

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Career-OS-Agent",
    }
    
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    else:
        logger.warning("No GITHUB_TOKEN configured — API rate limits will apply")

    all_repos: list[dict] = []
    page = 1

    async def _has_commits_by_user(client: httpx.AsyncClient, repo: dict, candidate_username: str) -> bool:
        if not repo.get("size"):
            return False
        url = f"https://api.github.com/repos/{repo['owner']['login']}/{repo['name']}/commits"
        try:
            response = await client.get(url, params={"author": candidate_username, "per_page": 1})
            if response.status_code == 200:
                commits = response.json()
                return len(commits) > 0
            return False
        except Exception:
            return False

    try:
        async with httpx.AsyncClient(headers=headers) as client:
            # Verify user exists
            user_response = await client.get(f"https://api.github.com/users/{username}")
            if user_response.status_code != 200:
                logger.warning("GitHub user %s not found", username)
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

            tasks = [_has_commits_by_user(client, repo, username) for repo in all_repos]
            results = await asyncio.gather(*tasks)
            
            return [repo for repo, has_commits in zip(all_repos, results) if has_commits]
    except Exception as e:
        logger.error("Failed to fetch GitHub repos: %s", e)

    return []


async def run_profile_intelligence(user_id: str):
    logger.info("Starting Profile Intelligence Agent for user_id=%s", user_id)
    profile_data = get_profile_data(user_id)
    if not profile_data:
        logger.error("No profile data found for user_id=%s", user_id)
        return

    original_resume_data = profile_data.get("original_resume")
    if not original_resume_data:
        logger.error("No parsed resume found in profile data for user_id=%s", user_id)
        return

    parsed_resume = ParsedResume(**original_resume_data)

    new_github_projects = []

    github_url = parsed_resume.personal_info.github if parsed_resume.personal_info else None
    
    # Fallback to regex if LLM failed to extract a valid GitHub URL
    if not github_url or github_url.strip().strip('/').lower() in ["https://github.com", "github.com"]:
        if parsed_resume.raw_text:
            match = re.search(r'github\.com/([a-zA-Z0-9-]+)', parsed_resume.raw_text, re.IGNORECASE)
            if match:
                github_url = f"https://github.com/{match.group(1)}"

    repos = await _fetch_github_repos(github_url)

    if repos:
        existing_urls = {p.url.lower().rstrip('/') for p in parsed_resume.projects if p.url}
        raw_text_lower = parsed_resume.raw_text.lower() if parsed_resume.raw_text else ""

        for repo in repos:
            repo_name = repo.get("name", "")
            repo_url = repo.get("html_url", "")
            
            # 1. Skip if the repository URL is mentioned anywhere in the resume text or in project URLs
            if repo_url and repo_url.lower() in raw_text_lower:
                continue
            if repo_url and repo_url.lower().rstrip('/') in existing_urls:
                continue

            # 2. Check for name duplicates using robust matching
            is_duplicate = False
            for p in parsed_resume.projects:
                if not p.name:
                    continue
                epn = p.name.lower()
                norm_repo = re.sub(r'[^a-z0-9]', '', repo_name.lower())
                norm_epn = re.sub(r'[^a-z0-9]', '', epn)
                
                # Exact or substring match for reasonably long names
                if norm_repo == norm_epn:
                    is_duplicate = True
                    break
                if len(norm_repo) > 5 and (norm_repo in norm_epn or norm_epn in norm_repo):
                    is_duplicate = True
                    break
                    
                # Word overlap match
                repo_words = set(re.findall(r'[a-z0-9]+', repo_name.lower()))
                epn_words = set(re.findall(r'[a-z0-9]+', epn))
                
                stop_words = {'and', 'the', 'for', 'app', 'system', 'project', 'based', 'using', 'with'}
                repo_words_meaningful = repo_words - stop_words
                epn_words_meaningful = epn_words - stop_words
                
                if repo_words_meaningful:
                    common = repo_words_meaningful.intersection(epn_words_meaningful)
                    if len(common) == len(repo_words_meaningful) or len(common) >= 2:
                        is_duplicate = True
                        break

            if is_duplicate:
                continue

            new_github_projects.append({
                "name": repo_name,
                "description": repo.get("description", ""),
                "url": repo_url,
                "language": repo.get("language", ""),
                "created_at": repo.get("created_at", ""),
                "updated_at": repo.get("updated_at", "")
            })

    # Build a summary of the resume for the LLM (exclude raw_text to save tokens)
    resume_dict = parsed_resume.model_dump()
    resume_dict.pop("raw_text", None)
    resume_json = json.dumps(resume_dict, indent=2)
    resume_projects_json = json.dumps([p.model_dump() for p in parsed_resume.projects], indent=2)
    github_projects_json = json.dumps(new_github_projects, indent=2)

    max_points = 3
    if parsed_resume.projects:
        points_counts = [len(p.description) for p in parsed_resume.projects if isinstance(p.description, list)]
        if points_counts:
            max_points = max(points_counts) or 3

    # Run LLM
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.nvidia_api_key,
        timeout=120.0,
        max_retries=1,
    )

    prompt = PROFILE_INTELLIGENCE_PROMPT.format(
        max_points=max_points,
        resume_json=resume_json,
        resume_projects=resume_projects_json,
        github_projects=github_projects_json,
    )

    def _call_llm():
        completion = client.chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a Profile Intelligence Agent. Always respond with valid JSON only, no markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        return completion.choices[0].message.content or ""

    response_text = await asyncio.to_thread(_call_llm)

    try:
        cleaned = response_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
    except Exception as e:
        logger.error("Failed to parse LLM response: %s", e)
        return

    # Extract fields from LLM response
    summaries = data.get("github_project_summaries", {})

    # Append github projects to resume projects
    for repo in new_github_projects:
        repo_name = repo["name"]
        summary = summaries.get(repo_name)
        if not summary or not isinstance(summary, list):
            summary = [repo.get("description", "")] if repo.get("description") else []

        project = Project(
            name=repo_name,
            description=summary,
            url=repo["url"],
            technologies=[repo["language"]] if repo.get("language") else [],
            start_date=repo["created_at"],
            end_date=repo["updated_at"]
        )
        parsed_resume.projects.append(project)

    # Build the simplified ProfileIntelligence object
    preferred_roles = [
        InferredJobRole(**r) for r in data.get("preferred_job_roles", [])
    ]

    profile_intelligence = ProfileIntelligence(
        original_resume=parsed_resume,
        preferred_job_roles=preferred_roles,
        strengths=data.get("strengths", []),
    )

    update_profile_intelligence(user_id, profile_intelligence)
    logger.info("Profile Intelligence Agent completed for user_id=%s", user_id)
