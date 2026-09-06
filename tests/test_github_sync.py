"""Covers the manual "Sync now" reconcile.

Enrichment on resume upload only ever added projects. Sync also has to remove
what has gone - which makes wrongly deleting a user's own resume content the
main risk, so most of these tests are about what sync must NOT touch.
"""

import asyncio

import pytest

from backend.services import github_enrichment as ge
from backend.services.github_enrichment import (
    _is_scan_shaped,
    github_username,
    merge_repos_into_projects,
    sync_github_projects,
)

OWNER = "vyshnav-182005"


def repo(name, repo_id=1, description=None, language=None, owner=OWNER):
    return {
        "id": repo_id,
        "name": name,
        "description": description,
        "language": language,
        "html_url": f"https://github.com/{owner}/{name}",
        "owner": {"login": owner},
    }


def scanned_project(name, repo_id=1, owner=OWNER):
    """A project exactly as the GitHub scan would have written it."""
    return {
        "name": name,
        "description": [],
        "technologies": [],
        "url": f"https://github.com/{owner}/{name}",
        "source": "github",
        "github_id": repo_id,
    }


class TestUsername:
    def test_extracts_account_from_profile_url(self):
        assert github_username("https://github.com/vyshnav-182005") == OWNER
        assert github_username("https://github.com/vyshnav-182005/") == OWNER

    def test_rejects_urls_with_no_account(self):
        assert github_username(None) is None
        assert github_username("") is None
        assert github_username("https://github.com") is None


class TestPruning:
    def test_removes_a_scanned_project_whose_repo_is_gone(self):
        projects = [scanned_project("Sem4_UMS", repo_id=11)]

        merged = merge_repos_into_projects(projects, [], prune_owner=OWNER)

        assert merged == []

    def test_keeps_a_resume_project_but_drops_its_dead_link(self):
        projects = [
            {
                "name": "Career-OS",
                "description": ["Built the matching engine.", "Shipped the dashboard."],
                "technologies": ["FastAPI"],
                "url": f"https://github.com/{OWNER}/Career-OS",
                "github_id": 7,
            }
        ]

        merged = merge_repos_into_projects(projects, [], prune_owner=OWNER)

        assert len(merged) == 1
        assert merged[0]["url"] is None
        assert merged[0]["github_id"] is None
        # The words the user wrote are untouched.
        assert merged[0]["description"] == [
            "Built the matching engine.",
            "Shipped the dashboard.",
        ]
        assert merged[0]["technologies"] == ["FastAPI"]

    def test_never_touches_another_accounts_repo(self):
        """Someone else's repo is absent from the scan for a harmless reason."""
        projects = [
            {
                "name": "MitreMapper",
                "description": ["Mapped detections to ATT&CK."],
                "technologies": [],
                "url": "https://github.com/Dineshkriss/MitreMapper",
            }
        ]

        merged = merge_repos_into_projects(projects, [], prune_owner=OWNER)

        assert merged == projects

    def test_never_touches_a_project_with_no_github_link(self):
        projects = [
            {"name": "Robotics Club Rover", "description": ["Won a prize."], "technologies": [], "url": None}
        ]

        merged = merge_repos_into_projects(projects, [], prune_owner=OWNER)

        assert merged == projects

    def test_keeps_repos_that_are_still_there(self):
        projects = [scanned_project("Career-OS", repo_id=7)]

        merged = merge_repos_into_projects(
            projects, [repo("Career-OS", repo_id=7)], prune_owner=OWNER
        )

        assert len(merged) == 1
        assert merged[0]["url"] == f"https://github.com/{OWNER}/Career-OS"

    def test_a_new_repo_is_added_and_marked_as_ours(self):
        merged = merge_repos_into_projects([], [repo("brand-new", repo_id=99)], prune_owner=OWNER)

        assert len(merged) == 1
        assert merged[0]["name"] == "brand-new"
        assert merged[0]["source"] == "github"
        assert merged[0]["github_id"] == 99

    def test_a_rename_follows_the_repo_instead_of_duplicating_it(self):
        """The numeric id is stable across a rename; the URL is not."""
        projects = [scanned_project("old-name", repo_id=42)]

        merged = merge_repos_into_projects(
            projects, [repo("new-name", repo_id=42)], prune_owner=OWNER
        )

        assert len(merged) == 1
        assert merged[0]["name"] == "new-name"
        assert merged[0]["url"] == f"https://github.com/{OWNER}/new-name"

    def test_a_rename_keeps_the_resume_detail_attached(self):
        projects = [
            {
                "name": "old-name",
                "description": ["Wrote the parser."],
                "technologies": ["Python"],
                "url": f"https://github.com/{OWNER}/old-name",
                "github_id": 42,
            }
        ]

        merged = merge_repos_into_projects(
            projects, [repo("new-name", repo_id=42)], prune_owner=OWNER
        )

        assert len(merged) == 1
        assert merged[0]["name"] == "new-name"
        assert merged[0]["description"] == ["Wrote the parser."]

    def test_without_prune_owner_nothing_is_ever_removed(self):
        projects = [scanned_project("Sem4_UMS", repo_id=11)]

        assert len(merge_repos_into_projects(projects, [])) == 1


class TestProvenanceInference:
    def test_an_entry_holding_only_scan_output_is_claimed(self):
        """Projects stored before `source` existed still have to be classified."""
        stored = {
            "name": "awesome-guide",
            "description": ["A curated list"],
            "technologies": ["Python"],
            "url": f"https://github.com/{OWNER}/awesome-guide",
        }
        live = repo("awesome-guide", repo_id=5, description="A curated list", language="Python")

        assert _is_scan_shaped(stored, live)

        merged = merge_repos_into_projects([stored], [live], prune_owner=OWNER)
        assert merged[0]["source"] == "github"

    def test_an_entry_with_resume_writing_is_not_claimed(self):
        stored = {
            "name": "Career-OS",
            "description": ["Built the matching engine.", "Shipped the dashboard."],
            "technologies": ["FastAPI", "Next.js"],
            "url": f"https://github.com/{OWNER}/Career-OS",
        }
        live = repo("Career-OS", repo_id=7, description="Career platform", language="Python")

        assert not _is_scan_shaped(stored, live)

        merged = merge_repos_into_projects([stored], [live], prune_owner=OWNER)
        assert merged[0].get("source") is None

    def test_a_claimed_entry_is_then_deletable(self):
        """Inference on one sync, deletion on the next."""
        stored = {
            "name": "awesome-guide",
            "description": [],
            "technologies": [],
            "url": f"https://github.com/{OWNER}/awesome-guide",
        }
        live = repo("awesome-guide", repo_id=5)

        claimed = merge_repos_into_projects([stored], [live], prune_owner=OWNER)
        assert claimed[0]["source"] == "github"

        gone = merge_repos_into_projects(claimed, [], prune_owner=OWNER)
        assert gone == []


class FakeProfile:
    """Stands in for the profiles row across a sync."""

    def __init__(self, projects, github="https://github.com/" + OWNER):
        self.saved = None
        self.data = {
            "original_resume": {
                "personal_info": {"github": github},
                "projects": projects,
            },
            "github_summary": "existing summary",
        }


@pytest.fixture
def profile(monkeypatch):
    fake = FakeProfile(projects=[scanned_project("Sem4_UMS", repo_id=11)])
    monkeypatch.setattr(ge, "get_profile_data", lambda user_id: fake.data)

    def save(user_id, profile_data, bump_version=True):
        fake.saved = (profile_data, bump_version)
        return True

    monkeypatch.setattr(ge, "_save_profile_data", save)

    async def summary(repos):
        return "regenerated summary"

    monkeypatch.setattr(ge, "_generate_github_summary", summary)
    return fake


def run_sync(user_id="u1"):
    return asyncio.run(sync_github_projects(user_id))


class TestSyncService:
    def test_an_unreachable_github_changes_nothing(self, monkeypatch, profile):
        """A fetch failure must never read as 'the account has no repos'."""

        async def fetch(url):
            return None

        monkeypatch.setattr(ge, "_fetch_github_repos", fetch)

        result = run_sync()

        assert result.success is False
        assert "Could not reach GitHub" in result.message
        assert profile.saved is None
        assert len(profile.data["original_resume"]["projects"]) == 1

    def test_an_account_emptied_on_purpose_does_prune(self, monkeypatch, profile):
        async def fetch(url):
            return []

        monkeypatch.setattr(ge, "_fetch_github_repos", fetch)

        result = run_sync()

        assert result.success is True
        assert result.removed == 1
        assert result.repo_count == 0
        assert profile.data["original_resume"]["projects"] == []

    def test_reports_what_changed(self, monkeypatch, profile):
        async def fetch(url):
            return [repo("Career-OS", repo_id=7), repo("Sem4_UMS", repo_id=11)]

        monkeypatch.setattr(ge, "_fetch_github_repos", fetch)

        result = run_sync()

        assert result.success is True
        assert result.added == 1
        assert result.removed == 0
        assert result.total_projects == 2
        assert "1 added" in result.message

    def test_an_unchanged_account_skips_the_llm_summary(self, monkeypatch, profile):
        repos = [repo("Sem4_UMS", repo_id=11)]

        async def fetch(url):
            return repos

        monkeypatch.setattr(ge, "_fetch_github_repos", fetch)

        calls = []

        async def summary(rs):
            calls.append(rs)
            return "regenerated summary"

        monkeypatch.setattr(ge, "_generate_github_summary", summary)

        first = run_sync()
        assert calls, "first sync has no stored signature, so it must write a summary"

        calls.clear()
        second = run_sync()

        assert second.success is True
        assert calls == [], "an unchanged repo set must not cost another completion"
        assert second.changed is False
        assert "Already up to date" in second.message

    def test_the_job_match_cache_is_re_keyed_only_when_something_changed(
        self, monkeypatch, profile
    ):
        repos = [repo("Sem4_UMS", repo_id=11)]

        async def fetch(url):
            return repos

        monkeypatch.setattr(ge, "_fetch_github_repos", fetch)

        run_sync()
        assert profile.saved[1] is True, "first sync changes the profile"

        run_sync()
        assert profile.saved[1] is False, "a no-op sync must not invalidate cached matches"

    def test_the_first_sync_over_legacy_projects_is_not_a_turnover(self, monkeypatch):
        """Projects stored before syncing existed carry no id and no source.

        The sync stamps both as it goes, so a diff keyed on those fields sees
        every project replaced and reports "10 added, 10 removed" for a profile
        that did not change at all.
        """
        legacy = [
            {
                "name": "Career-OS",
                "description": ["Built the matching engine."],
                "technologies": ["FastAPI"],
                "url": f"https://github.com/{OWNER}/Career-OS.git",
            },
            {
                "name": "Sem4_UMS",
                "description": [],
                "technologies": [],
                "url": f"https://github.com/{OWNER}/Sem4_UMS",
            },
        ]
        fake = FakeProfile(projects=legacy)
        monkeypatch.setattr(ge, "get_profile_data", lambda user_id: fake.data)
        monkeypatch.setattr(ge, "_save_profile_data", lambda *a, **k: True)

        async def summary(repos):
            return "s"

        monkeypatch.setattr(ge, "_generate_github_summary", summary)

        async def fetch(url):
            return [repo("Career-OS", repo_id=7), repo("Sem4_UMS", repo_id=11)]

        monkeypatch.setattr(ge, "_fetch_github_repos", fetch)

        result = run_sync()

        assert result.added == 0
        assert result.removed == 0
        assert result.renamed == 0
        assert result.total_projects == 2
        assert "Already up to date" in result.message

    def test_one_new_repo_among_legacy_projects_counts_as_one(self, monkeypatch):
        legacy = [
            {
                "name": "Career-OS",
                "description": ["Built the matching engine."],
                "technologies": ["FastAPI"],
                "url": f"https://github.com/{OWNER}/Career-OS.git",
            }
        ]
        fake = FakeProfile(projects=legacy)
        monkeypatch.setattr(ge, "get_profile_data", lambda user_id: fake.data)
        monkeypatch.setattr(ge, "_save_profile_data", lambda *a, **k: True)

        async def summary(repos):
            return "s"

        monkeypatch.setattr(ge, "_generate_github_summary", summary)

        async def fetch(url):
            return [repo("Career-OS", repo_id=7), repo("mandate-rescue", repo_id=99)]

        monkeypatch.setattr(ge, "_fetch_github_repos", fetch)

        result = run_sync()

        assert result.added == 1
        assert result.removed == 0
        assert result.total_projects == 2
        assert result.message == "Synced 2 repos: 1 added."

    def test_a_profile_without_a_github_link_says_so(self, monkeypatch):
        fake = FakeProfile(projects=[], github=None)
        monkeypatch.setattr(ge, "get_profile_data", lambda user_id: fake.data)

        result = run_sync()

        assert result.success is False
        assert "No GitHub account is linked" in result.message

    def test_a_profile_that_was_never_parsed_says_so(self, monkeypatch):
        monkeypatch.setattr(ge, "get_profile_data", lambda user_id: None)

        result = run_sync()

        assert result.success is False
        assert "Parse a resume first" in result.message
