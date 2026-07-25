import asyncio
import httpx

async def _fetch_github_repos(github_url: str) -> list[dict]:
    if not github_url:
        return []

    username = github_url.rstrip('/').split('/')[-1]
    if not username:
        return []

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Career-OS-Agent",
    }

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
            user_response = await client.get(f"https://api.github.com/users/{username}")
            if user_response.status_code != 200:
                print("GitHub user not found")
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
        print("Failed to fetch GitHub repos:", e)

    return []

async def main():
    repos = await _fetch_github_repos("vyshnav-182005")
    print(f"Found {len(repos)} repos")
    for r in repos:
        print("-", r['name'])

if __name__ == "__main__":
    asyncio.run(main())
