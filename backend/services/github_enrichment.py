import asyncio
import hashlib
import httpx
import logging
import re
from datetime import datetime, timezone

from backend.config import settings
from backend.services.llm_client import NO_THINKING, build_async_client
from backend.db.supabase_client import (
    _compute_profile_version,
    get_profile_data,
    get_supabase_client,
)
from backend.services.workflow_orchestrator import trigger_profile_intelligence_workflow
from backend.models.resume import Project
from backend.models.schemas import GithubSyncResult

logger = logging.getLogger(__name__)

async def _fetch_github_repos(github_url: str) -> list[dict] | None:
    """The account's public repos, or None if GitHub could not be asked.

    None and [] must stay distinguishable: a sync deletes the projects it
    created for repos that have disappeared, so an outage or a bad username
    returning "no repos" would wipe the user's whole GitHub-sourced list.
    Only an answer GitHub actually gave is allowed to drive a deletion.
    """
    if not github_url:
        return None

    username = github_url.rstrip('/').split('/')[-1]
    if not username or username.lower() in ["github", "github.com", "http", "https"]:
        logger.info("Invalid or generic GitHub username extracted: %s", username)
        return None

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
                # Could be a renamed or deleted account, or a rate limit. Not
                # evidence that the user has no repos.
                logger.info("GitHub user not reachable: %s (%s)", username, user_response.status_code)
                return None

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

    return None

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
    client = build_async_client(timeout=60.0)
    
    try:
        completion = await client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
            extra_body=NO_THINKING,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"Error generating github summary: {e}")
        return "Candidate has several public GitHub repositories."

# Matches any spelling of a GitHub repo link: https/http, ssh (git@github.com:o/r),
# with or without "www.", a ".git" suffix, a trailing slash, or a query/fragment.
# The host is anchored so sibling hosts (gist.github.com) are not read as repos.
_GITHUB_REPO_RE = re.compile(
    r"(?:^|//|@)(?:www\.)?github\.com[:/]+(?P<owner>[^/\s]+)/(?P<repo>[^/\s#?]+)",
    re.IGNORECASE,
)


def _repo_name_from_url(url: str | None) -> str | None:
    """The repo segment of a GitHub URL, in its original casing.

    Lets a stored project be labelled with its repo name without a scan — the
    URL already carries it, whether it came from the resume or the API.
    """
    if not url:
        return None
    match = _GITHUB_REPO_RE.search(url.strip())
    if not match:
        return None
    repo = match.group("repo")
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    return repo or None


def _repo_key(url: str | None) -> str | None:
    """Canonical "owner/repo" for a GitHub URL, or None if it is not one.

    A resume link and the GitHub API's html_url point at the same repo while
    differing as strings (the resume usually carries the clone URL, ending in
    ".git"), so they have to be compared on this key rather than verbatim.
    """
    if not url:
        return None
    match = _GITHUB_REPO_RE.search(url.strip())
    if not match:
        return None
    repo = match.group("repo")
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if not repo:
        return None
    return f"{match.group('owner').lower()}/{repo.lower()}"


def _repo_owner(url: str | None) -> str | None:
    """The account a repo URL belongs to, lowercased."""
    key = _repo_key(url)
    return key.split("/", 1)[0] if key else None


def _normalize_name(name: str | None) -> str:
    return "".join(c.lower() for c in (name or "") if c.isalnum())


def _scanned_fields(repo: dict) -> dict:
    """Exactly what the scan stores for a repo, and nothing more."""
    return {
        "name": repo.get("name") or "Unknown Repository",
        "description": [repo["description"]] if repo.get("description") else [],
        "technologies": [repo["language"]] if repo.get("language") else [],
        "url": repo.get("html_url"),
    }


def _is_scan_shaped(project: dict, repo: dict) -> bool:
    """True when a stored entry holds only what a scan would have written.

    Recovers provenance for projects saved before `source` existed. If the
    description and technologies are precisely the repo's own blurb and
    language, with no dates, the user never wrote anything here — so the sync
    may treat it as its own and remove it when the repo goes away.

    A resume project reduced to a bare name and link matches this too, but such
    an entry carries no user-written content to lose. Anything the user
    actually typed fails the check and is kept.
    """
    scanned = _scanned_fields(repo)
    return (
        (project.get("description") or []) == scanned["description"]
        and (project.get("technologies") or []) == scanned["technologies"]
        and not project.get("start_date")
        and not project.get("end_date")
    )


def _merge_project(target: dict, source: dict) -> None:
    """Fold `source` into `target`, keeping the richer value for each field."""
    if not target.get("url") and source.get("url"):
        target["url"] = source["url"]

    # Resume bullets are a list of sentences; a repo blurb is a single line.
    # Whichever says more about the project wins.
    if len(source.get("description") or []) > len(target.get("description") or []):
        target["description"] = list(source["description"])

    technologies = list(target.get("technologies") or [])
    seen = {t.lower() for t in technologies if isinstance(t, str)}
    for tech in source.get("technologies") or []:
        if isinstance(tech, str) and tech.lower() not in seen:
            seen.add(tech.lower())
            technologies.append(tech)
    target["technologies"] = technologies

    for field in ("start_date", "end_date"):
        if not target.get(field) and source.get(field):
            target[field] = source[field]


def merge_repos_into_projects(
    projects: list[dict],
    repos: list[dict],
    prune_owner: str | None = None,
) -> list[dict]:
    """Returns one project entry per repo, named after the repo.

    Resume parsing stores a project under whatever heading the resume used
    ("CareerOS: AI-Powered Career Intelligence Platform"); the GitHub scan then
    stores the same repo under its real name ("Career-OS"). Matching on the
    canonical owner/repo key collapses those into a single entry that keeps the
    resume's richer detail but shows the repo name.

    `prune_owner` turns this into a sync: repos of that account which are no
    longer in `repos` have gone (deleted, or made private), so a project the
    scan created for one is removed and a resume-written one keeps its text but
    loses its dead link. Only that account's repos are considered, so a link to
    somebody else's repo is never touched. Pass it only with a repo list GitHub
    actually returned — see `_fetch_github_repos`.
    """
    merged: list[dict] = []
    by_repo_key: dict[str, dict] = {}
    by_repo_id: dict[int, dict] = {}
    by_name: dict[str, dict] = {}

    def index(project: dict) -> None:
        key = _repo_key(project.get("url"))
        if key:
            by_repo_key.setdefault(key, project)
        repo_id = project.get("github_id")
        if repo_id is not None:
            by_repo_id.setdefault(repo_id, project)
        name_key = _normalize_name(project.get("name"))
        if name_key:
            by_name.setdefault(name_key, project)

    def find(url: str | None, name: str | None, repo_id: int | None = None) -> dict | None:
        # The numeric id survives a rename, where the URL does not, so it is
        # the strongest signal when we have it.
        if repo_id is not None and repo_id in by_repo_id:
            return by_repo_id[repo_id]

        key = _repo_key(url)
        if key and key in by_repo_key:
            return by_repo_key[key]

        name_key = _normalize_name(name)
        candidate = by_name.get(name_key) if name_key else None
        if candidate is None:
            return None

        # The name fallback exists for projects whose link the resume omitted.
        # Two links pointing at different repos are different projects however
        # alike their names, so never let a name collapse them.
        candidate_key = _repo_key(candidate.get("url"))
        if key and candidate_key and key != candidate_key:
            return None
        return candidate

    # Pass 1 — carry over stored projects, collapsing any duplicates already
    # persisted by an earlier run that compared URLs verbatim.
    for project in projects:
        if not isinstance(project, dict):
            continue
        project = dict(project)

        # Label it with the repo name before matching, so the resume heading and
        # the scan's entry collapse onto the same name key even when one of the
        # two is missing its link.
        repo_name = _repo_name_from_url(project.get("url"))
        if repo_name:
            project["name"] = repo_name

        existing = find(project.get("url"), project.get("name"))
        if existing is not None:
            _merge_project(existing, project)
            index(existing)
            continue
        merged.append(project)
        index(project)

    # Pass 2 — fold in the scan, renaming matched entries to the repo name.
    for repo in repos:
        scanned = _scanned_fields(repo)
        name = scanned["name"]
        repo_url = scanned["url"]
        repo_id = repo.get("id")

        existing = find(repo_url, name, repo_id)
        if existing is not None:
            # Decide provenance before merging, while the entry still holds
            # only what was stored.
            if not existing.get("source") and _is_scan_shaped(existing, repo):
                existing["source"] = "github"

            _merge_project(existing, scanned)
            existing["name"] = name
            if repo_url:
                existing["url"] = repo_url
            if repo_id is not None:
                existing["github_id"] = repo_id
            index(existing)
            continue

        project = Project(**scanned, source="github", github_id=repo_id).model_dump()
        merged.append(project)
        index(project)

    if prune_owner is None:
        return merged

    return _prune_missing_repos(merged, repos, prune_owner.lower())


def _prune_missing_repos(
    projects: list[dict], repos: list[dict], owner: str
) -> list[dict]:
    """Drops or unlinks projects for `owner` repos the scan no longer sees."""
    live_keys = {key for key in (_repo_key(r.get("html_url")) for r in repos) if key}
    live_ids = {r["id"] for r in repos if r.get("id") is not None}

    kept: list[dict] = []
    for project in projects:
        repo_id = project.get("github_id")
        key = _repo_key(project.get("url"))

        # Not this account's repo — a resume-only project, or a link to
        # somebody else's work. Never ours to remove.
        if _repo_owner(project.get("url")) != owner and repo_id not in live_ids:
            kept.append(project)
            continue

        if (repo_id is not None and repo_id in live_ids) or (key and key in live_keys):
            kept.append(project)
            continue

        if project.get("source") == "github":
            logger.info("Repo gone, dropping scanned project %r", project.get("name"))
            continue

        # Written by the user: the words stay, only the dead link goes.
        logger.info("Repo gone, unlinking resume project %r", project.get("name"))
        project["url"] = None
        project["github_id"] = None
        kept.append(project)

    return kept


def github_username(github_url: str | None) -> str | None:
    """The account name in a GitHub profile URL."""
    if not github_url:
        return None
    username = github_url.rstrip("/").split("/")[-1].strip()
    if not username or username.lower() in ["github", "github.com", "http", "https"]:
        return None
    return username


def _repos_signature(repos: list[dict]) -> str:
    """Fingerprint of what the summary is written from.

    The summary costs an LLM call, so it is only rewritten when the repos it
    describes actually changed - otherwise pressing "Sync now" twice burns a
    completion to produce the same three sentences.
    """
    payload = sorted(
        f"{r.get('id')}|{r.get('name')}|{r.get('language')}|{r.get('description')}"
        for r in repos
    )
    return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()


def _identity_keys(project: dict) -> list[tuple]:
    """Handles a project may be recognised by, strongest first.

    A sync fills in fields as it goes - it stamps `github_id` on entries that
    had none, and a rename moves both the URL and the name. So a project is
    "the same project" if it still shares any one of these, not if the whole
    tuple matches; otherwise every first-time sync reads as a full turnover.
    """
    keys: list[tuple] = []
    repo_id = project.get("github_id")
    if repo_id is not None:
        keys.append(("id", repo_id))
    key = _repo_key(project.get("url"))
    if key:
        keys.append(("repo", key))
    name = _normalize_name(project.get("name"))
    if name:
        keys.append(("name", name))
    return keys


def _diff_projects(before: list[dict], after: list[dict]) -> dict[str, int]:
    """Counts what one sync did, for the button to report back."""
    index: dict[tuple, dict] = {}
    for project in before:
        for key in _identity_keys(project):
            index.setdefault(key, project)

    matched: set[int] = set()
    added = renamed = unlinked = 0

    for project in after:
        previous = next(
            (index[key] for key in _identity_keys(project) if key in index), None
        )
        if previous is None:
            added += 1
            continue

        matched.add(id(previous))
        if previous.get("name") != project.get("name"):
            renamed += 1
        if previous.get("url") and not project.get("url"):
            unlinked += 1

    removed = sum(1 for project in before if id(project) not in matched)
    return {"added": added, "removed": removed, "unlinked": unlinked, "renamed": renamed}


async def sync_github_projects(user_id: str, github_url: str | None = None) -> GithubSyncResult:
    """Re-scans the linked GitHub account and reconciles the project list.

    Unlike the enrichment that runs on resume upload, this removes what has
    gone: a repo the scan created a project for and can no longer see was
    deleted or made private, so its project goes too. A project the user wrote
    in their resume is kept either way and only loses its dead link.
    """
    profile_data = get_profile_data(user_id)
    if not profile_data or "original_resume" not in profile_data:
        return GithubSyncResult(
            success=False, message="Parse a resume first - there is no profile to sync into."
        )

    resume = profile_data["original_resume"]
    github_url = github_url or (resume.get("personal_info") or {}).get("github")
    username = github_username(github_url)
    if not username:
        return GithubSyncResult(
            success=False,
            message="No GitHub account is linked to this profile. Add the link to your resume and re-parse it.",
        )

    repos = await _fetch_github_repos(github_url)
    if repos is None:
        # Never prune on an answer GitHub did not give.
        return GithubSyncResult(
            success=False,
            message=f"Could not reach GitHub for '{username}'. Nothing was changed - try again shortly.",
        )

    before = list(resume.get("projects") or [])
    merged = merge_repos_into_projects(before, repos, prune_owner=username)
    counts = _diff_projects(before, merged)

    resume["projects"] = merged

    signature = _repos_signature(repos)
    sync_state = profile_data.get("github_sync") or {}
    summary_is_stale = (
        sync_state.get("repo_signature") != signature or not profile_data.get("github_summary")
    )

    if summary_is_stale:
        profile_data["github_summary"] = (
            await _generate_github_summary(repos)
            if repos
            else "No public GitHub repositories."
        )

    synced_at = datetime.now(timezone.utc).isoformat()
    profile_data["github_sync"] = {
        "synced_at": synced_at,
        "repo_signature": signature,
        "repo_count": len(repos),
        "username": username,
    }

    changed = bool(any(counts.values()) or summary_is_stale)
    if not _save_profile_data(user_id, profile_data, bump_version=changed):
        return GithubSyncResult(
            success=False, message="Synced with GitHub but could not save the result."
        )

    return GithubSyncResult(
        success=True,
        message=_sync_message(counts, len(repos)),
        repo_count=len(repos),
        total_projects=len(merged),
        changed=changed,
        synced_at=synced_at,
        **counts,
    )


def _sync_message(counts: dict[str, int], repo_count: int) -> str:
    parts = [f"{value} {label}" for label, value in counts.items() if value]
    if not parts:
        return f"Already up to date with {repo_count} repos."
    return f"Synced {repo_count} repos: " + ", ".join(parts) + "."


def _save_profile_data(user_id: str, profile_data: dict, bump_version: bool = True) -> bool:
    """Persists profile_data, re-keying the job-match cache when it changed."""
    row: dict = {"profile_data": profile_data}
    if bump_version:
        # job_matches is cached against this hash. A changed project list is a
        # changed profile, so stale LLM verdicts have to fall out with it.
        row["profile_version"] = _compute_profile_version(profile_data)

    client = get_supabase_client()
    try:
        client.table("profiles").update(row).eq("user_id", user_id).execute()
        return True
    except Exception:
        logger.exception("Failed to save profile_data for user_id=%s", user_id)
        return False


async def enrich_profile_with_github_projects(user_id: str, github_url: str):
    logger.info("Starting GitHub enrichment for user_id=%s, github_url=%s", user_id, github_url)

    repos = await _fetch_github_repos(github_url)

    profile_data = get_profile_data(user_id)
    if not profile_data or "original_resume" not in profile_data:
        logger.error("Profile data not found for user_id=%s to update with GitHub repos", user_id)
        return

    if not repos:
        # Enrichment runs on resume upload, before anything of ours is stored,
        # so there is nothing to prune and a failed fetch costs only a summary.
        logger.info("No GitHub repos available for user_id=%s", user_id)
        profile_data["github_summary"] = "No public GitHub repositories."
    else:
        logger.info("Found %d repos for user_id=%s", len(repos), user_id)

        projects = profile_data["original_resume"].get("projects") or []
        merged = merge_repos_into_projects(projects, repos)
        if len(merged) != len(projects):
            logger.info(
                "Merged projects for user_id=%s: %d stored + %d repos -> %d",
                user_id, len(projects), len(repos), len(merged),
            )

        profile_data["original_resume"]["projects"] = merged

        profile_data["github_summary"] = await _generate_github_summary(repos)
        profile_data["github_sync"] = {
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "repo_signature": _repos_signature(repos),
            "repo_count": len(repos),
            "username": github_username(github_url),
        }

    # The profile intelligence workflow runs straight after and recomputes the
    # version itself, so this write does not need to.
    if _save_profile_data(user_id, profile_data, bump_version=False):
        logger.info("Successfully updated GitHub projects for user_id=%s", user_id)


async def enrich_and_trigger_workflow(user_id: str, github_url: str):
    try:
        await enrich_profile_with_github_projects(user_id, github_url)
    except Exception as e:
        logger.error("Error during GitHub enrichment for user_id=%s: %s", user_id, e)
    
    await trigger_profile_intelligence_workflow(user_id)
