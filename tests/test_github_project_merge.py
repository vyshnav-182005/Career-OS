"""Covers the resume-vs-GitHub-scan project duplication.

Resume parsing stores a project under the resume's own heading and the clone
URL (".git"); the later GitHub scan stores the same repo under its real name
and the html_url. Comparing URLs verbatim missed that, so one repo produced two
project cards.
"""

from backend.services.github_enrichment import (
    _repo_key,
    merge_repos_into_projects,
)


def repo(name, description=None, language=None, owner="vyshnav-182005"):
    return {
        "name": name,
        "description": description,
        "language": language,
        "html_url": f"https://github.com/{owner}/{name}",
    }


class TestRepoKey:
    def test_clone_url_and_html_url_share_a_key(self):
        assert _repo_key("https://github.com/vyshnav-182005/Career-OS.git") == _repo_key(
            "https://github.com/vyshnav-182005/Career-OS"
        )

    def test_normalizes_case_www_ssh_slash_and_fragments(self):
        expected = "owner/repo"
        for url in [
            "https://github.com/Owner/Repo",
            "http://www.github.com/owner/repo/",
            "git@github.com:owner/repo.git",
            "https://github.com/owner/repo#readme",
            "https://github.com/owner/repo?tab=readme",
        ]:
            assert _repo_key(url) == expected, url

    def test_ignores_non_repo_urls(self):
        assert _repo_key(None) is None
        assert _repo_key("") is None
        assert _repo_key("https://gitlab.com/owner/repo") is None
        assert _repo_key("https://example.com/projects") is None
        assert _repo_key("https://gist.github.com/owner/abc123") is None
        assert _repo_key("https://github.com/owner") is None

    def test_reads_the_repo_from_a_deep_link(self):
        assert _repo_key("https://github.com/owner/repo/tree/main/src") == "owner/repo"

    def test_distinguishes_owners(self):
        assert _repo_key("https://github.com/a/mapper") != _repo_key(
            "https://github.com/b/mapper"
        )


class TestMergeReposIntoProjects:
    def test_clone_url_suffix_no_longer_duplicates(self):
        projects = [
            {
                "name": "CareerOS: AI-Powered Career Intelligence Platform",
                "description": ["Built the matching engine.", "Shipped the dashboard."],
                "technologies": ["FastAPI", "Next.js"],
                "url": "https://github.com/vyshnav-182005/Career-OS.git",
            }
        ]

        merged = merge_repos_into_projects(projects, [repo("Career-OS", language="Python")])

        assert len(merged) == 1
        assert merged[0]["name"] == "Career-OS"
        assert merged[0]["url"] == "https://github.com/vyshnav-182005/Career-OS"

    def test_keeps_resume_detail_while_showing_repo_name(self):
        projects = [
            {
                "name": "SwiftShield: AI-Powered Parametric Insurance Platform",
                "description": ["Automated payouts.", "Cut claim latency 40%."],
                "technologies": ["Solidity"],
                "url": "https://github.com/vyshnav-182005/SwiftShield.git",
                "start_date": "2025-01",
            }
        ]

        merged = merge_repos_into_projects(
            projects, [repo("SwiftShield", description="Parametric insurance", language="Python")]
        )

        assert len(merged) == 1
        project = merged[0]
        assert project["name"] == "SwiftShield"
        # The two-bullet resume text beats the one-line repo blurb.
        assert project["description"] == ["Automated payouts.", "Cut claim latency 40%."]
        assert project["technologies"] == ["Solidity", "Python"]
        assert project["start_date"] == "2025-01"

    def test_collapses_duplicates_already_stored(self):
        """Profiles written before the fix already hold both copies."""
        projects = [
            {
                "name": "Sentinel Turret Rover: Attention-Based Face Recognition",
                "description": ["Tracked intruders in real time."],
                "technologies": ["OpenCV"],
                "url": "https://github.com/vyshnav-182005/Sentinel-Turret-Rover.git",
            },
            {
                "name": "Sentinel-Turret-Rover",
                "description": [],
                "technologies": ["Python"],
                "url": "https://github.com/vyshnav-182005/Sentinel-Turret-Rover",
            },
        ]

        merged = merge_repos_into_projects(projects, [])

        assert len(merged) == 1
        assert merged[0]["description"] == ["Tracked intruders in real time."]
        assert merged[0]["technologies"] == ["OpenCV", "Python"]

    def test_matches_by_name_when_resume_omits_the_link(self):
        projects = [
            {
                "name": "Prerequisite Course Planning Assistant",
                "description": ["Planned course order."],
                "technologies": [],
                "url": None,
            }
        ]

        merged = merge_repos_into_projects(
            projects, [repo("Prerequisite-Course-Planning-Assistant", language="Python")]
        )

        assert len(merged) == 1
        assert merged[0]["name"] == "Prerequisite-Course-Planning-Assistant"
        assert merged[0]["url"] == (
            "https://github.com/vyshnav-182005/Prerequisite-Course-Planning-Assistant"
        )

    def test_unmatched_repos_are_appended_after_resume_projects(self):
        projects = [{"name": "Career-OS", "description": [], "technologies": [], "url": None}]

        merged = merge_repos_into_projects(
            projects, [repo("Career-OS"), repo("Sem4_UMS", language="Java")]
        )

        assert [p["name"] for p in merged] == ["Career-OS", "Sem4_UMS"]
        assert merged[1]["technologies"] == ["Java"]

    def test_third_party_repo_is_renamed_but_never_merged(self):
        """Another owner's repo is a separate project, but still shows its repo name."""
        projects = [
            {
                "name": "MITRE Mapper",
                "description": ["Mapped detections to ATT&CK."],
                "technologies": [],
                "url": "https://github.com/Dineshkriss/MitreMapper",
            }
        ]

        merged = merge_repos_into_projects(
            projects, [repo("guardgraph-ai", owner="rohit-sundar")]
        )

        assert [p["name"] for p in merged] == ["MitreMapper", "guardgraph-ai"]
        assert merged[0]["description"] == ["Mapped detections to ATT&CK."]

    def test_same_repo_name_under_two_owners_stays_separate(self):
        projects = [
            {"name": "Mapper", "description": [], "technologies": [], "url": "https://github.com/a/mapper"},
            {"name": "Mapper", "description": [], "technologies": [], "url": "https://github.com/b/mapper"},
        ]

        merged = merge_repos_into_projects(projects, [])

        assert len(merged) == 2
        assert [p["url"] for p in merged] == [
            "https://github.com/a/mapper",
            "https://github.com/b/mapper",
        ]

    def test_non_repo_links_keep_their_resume_name(self):
        """A gist or a bare profile link is not a repo, so the heading stands."""
        projects = [
            {
                "name": "Snippet Collection",
                "description": [],
                "technologies": [],
                "url": "https://gist.github.com/vyshnav-182005/abc123",
            },
            {
                "name": "Portfolio Site",
                "description": [],
                "technologies": [],
                "url": "https://example.com/portfolio",
            },
        ]

        merged = merge_repos_into_projects(projects, [])

        assert [p["name"] for p in merged] == ["Snippet Collection", "Portfolio Site"]

    def test_is_idempotent(self):
        projects = [
            {
                "name": "CVD detection app",
                "description": ["Corrected colour vision."],
                "technologies": [],
                "url": "https://github.com/vyshnav-182005/CVD-detection-and-correction.git",
            }
        ]
        repos = [repo("CVD-detection-and-correction", language="Python")]

        once = merge_repos_into_projects(projects, repos)
        twice = merge_repos_into_projects(once, repos)

        assert once == twice
        assert len(twice) == 1

    def test_no_repos_leaves_projects_untouched(self):
        projects = [
            {"name": "Solo project", "description": ["Did a thing."], "technologies": ["C"], "url": None}
        ]

        assert merge_repos_into_projects(projects, []) == projects
