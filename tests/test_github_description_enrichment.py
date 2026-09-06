"""Covers turning scan-written repo blurbs into README-grounded resume bullets.

The pass writes over project descriptions, so the risk it has to be held to is
overwriting something the user wrote, or spending a README read and an LLM call
on repos that gain nothing from either. Most of these tests are about what it
must leave alone and what it must not fetch twice.
"""

import asyncio
import base64

import pytest

from backend.services import github_enrichment as ge
from backend.services.github_enrichment import (
    _enrichment_candidates,
    _fetch_repo_languages,
    _fetch_repo_readme,
    _has_only_scan_description,
    _language_breakdown,
    _readme_signature,
    enrich_project_descriptions,
)

OWNER = "vyshnav-182005"

README = """
# Sem4_UMS

A university management system built with Django and PostgreSQL. Students
enroll in courses, staff record grades, and the admin dashboard reports on
attendance.
"""


def repo(name, repo_id=1, description=None, language=None, pushed_at="2026-01-01T00:00:00Z"):
    return {
        "id": repo_id,
        "name": name,
        "description": description,
        "language": language,
        "html_url": f"https://github.com/{OWNER}/{name}",
        "owner": {"login": OWNER},
        "pushed_at": pushed_at,
    }


def scanned_project(name, repo_id=1, description=None, **extra):
    project = {
        "name": name,
        "description": description or [],
        "technologies": [],
        "url": f"https://github.com/{OWNER}/{name}",
        "source": "github",
        "github_id": repo_id,
    }
    project.update(extra)
    return project


def profile_with(projects, github_sync=None):
    data = {"original_resume": {"projects": projects}}
    if github_sync is not None:
        data["github_sync"] = github_sync
    return data


@pytest.fixture
def github(monkeypatch):
    """Records what the pass asked GitHub and the LLM for."""

    class Recorder:
        def __init__(self):
            self.readme_calls = []
            self.language_calls = []
            self.generated_for = []
            self.readme = README
            self.bullets = {
                "sem4ums": ["Built a Django course-enrollment system", "Backed it with PostgreSQL"]
            }

    recorder = Recorder()

    async def fetch_readme(client, owner, name):
        recorder.readme_calls.append(name)
        return recorder.readme

    async def fetch_languages(client, owner, name):
        recorder.language_calls.append(name)
        return {"Python": 900, "HTML": 100}

    async def generate(repos_context):
        recorder.generated_for.extend(name for name, _readme, _languages in repos_context)
        return recorder.bullets

    monkeypatch.setattr(ge, "_fetch_repo_readme", fetch_readme)
    monkeypatch.setattr(ge, "_fetch_repo_languages", fetch_languages)
    monkeypatch.setattr(ge, "_generate_project_bullets", generate)
    return recorder


class TestCandidateSelection:
    def test_an_empty_description_is_a_candidate(self):
        repos = [repo("Sem4_UMS", repo_id=11)]
        projects = [scanned_project("Sem4_UMS", repo_id=11)]

        assert len(_enrichment_candidates(projects, repos)) == 1

    def test_the_raw_repo_blurb_is_a_candidate(self):
        repos = [repo("Sem4_UMS", repo_id=11, description="A UMS")]
        projects = [scanned_project("Sem4_UMS", repo_id=11, description=["A UMS"])]

        assert len(_enrichment_candidates(projects, repos)) == 1

    def test_text_the_user_wrote_is_left_alone(self):
        """The whole point of description_source: never overwrite the user."""
        repos = [repo("Sem4_UMS", repo_id=11, description="A UMS")]
        projects = [
            scanned_project(
                "Sem4_UMS",
                repo_id=11,
                description=["A UMS"],
                description_source="user",
            )
        ]

        assert _enrichment_candidates(projects, repos) == []

    def test_a_description_saying_more_than_the_blurb_is_left_alone(self):
        repos = [repo("Sem4_UMS", repo_id=11, description="A UMS")]
        projects = [
            scanned_project(
                "Sem4_UMS",
                repo_id=11,
                description=["Built enrollment and grading for 400 students"],
            )
        ]

        assert _enrichment_candidates(projects, repos) == []

    def test_a_resume_written_project_is_never_a_candidate(self):
        repos = [repo("Sem4_UMS", repo_id=11)]
        projects = [dict(scanned_project("Sem4_UMS", repo_id=11), source=None)]

        assert _enrichment_candidates(projects, repos) == []

    def test_a_project_with_no_matching_repo_is_skipped(self):
        repos = [repo("Career-OS", repo_id=7)]
        projects = [scanned_project("Sem4_UMS", repo_id=11)]

        assert _enrichment_candidates(projects, repos) == []

    def test_scan_description_check_tolerates_a_blank_bullet(self):
        assert _has_only_scan_description({"description": ["  "]}, repo("X")) is True


class TestEnrichment:
    def test_writes_bullets_and_marks_them_generated(self, github):
        repos = [repo("Sem4_UMS", repo_id=11)]
        profile_data = profile_with([scanned_project("Sem4_UMS", repo_id=11)])

        outcome = asyncio.run(enrich_project_descriptions(profile_data, repos))

        project = profile_data["original_resume"]["projects"][0]
        assert outcome == {"described": 1, "changed": True}
        assert project["description"] == [
            "Built a Django course-enrollment system",
            "Backed it with PostgreSQL",
        ]
        assert project["description_source"] == "ai_generated"
        assert github.readme_calls == ["Sem4_UMS"]
        assert github.language_calls == ["Sem4_UMS"]

    def test_nothing_to_enrich_costs_no_requests(self, github):
        repos = [repo("Sem4_UMS", repo_id=11, description="A UMS")]
        projects = [
            scanned_project("Sem4_UMS", repo_id=11, description=["Wrote this myself"])
        ]

        outcome = asyncio.run(enrich_project_descriptions(profile_with(projects), repos))

        assert outcome == {"described": 0, "changed": False}
        assert github.readme_calls == []
        assert github.generated_for == []

    def test_a_repo_without_a_readme_is_skipped_not_invented(self, github):
        github.readme = None
        repos = [repo("Sem4_UMS", repo_id=11)]
        profile_data = profile_with([scanned_project("Sem4_UMS", repo_id=11)])

        outcome = asyncio.run(enrich_project_descriptions(profile_data, repos))

        project = profile_data["original_resume"]["projects"][0]
        assert project["description"] == []
        assert "description_source" not in project
        assert github.generated_for == []
        # Worth saving (the fingerprint), but no text moved -- so the caller
        # must not treat it as a changed profile.
        assert outcome == {"described": 0, "changed": True}

    def test_an_unchanged_repo_is_not_fetched_again(self, github):
        """The cache exists so a second sync doesn't re-read every README."""
        repos = [repo("Sem4_UMS", repo_id=11)]
        profile_data = profile_with([scanned_project("Sem4_UMS", repo_id=11)])

        asyncio.run(enrich_project_descriptions(profile_data, repos))

        # The pass wrote bullets, so re-running only finds a candidate again if
        # the description is cleared -- which is what a user deleting it does.
        profile_data["original_resume"]["projects"][0]["description"] = []
        github.readme_calls.clear()
        github.generated_for.clear()

        outcome = asyncio.run(enrich_project_descriptions(profile_data, repos))

        assert outcome == {"described": 0, "changed": False}
        assert github.readme_calls == []
        assert github.generated_for == []

    def test_a_new_push_makes_the_repo_eligible_again(self, github):
        profile_data = profile_with([scanned_project("Sem4_UMS", repo_id=11)])

        asyncio.run(
            enrich_project_descriptions(
                profile_data, [repo("Sem4_UMS", repo_id=11, pushed_at="2026-01-01T00:00:00Z")]
            )
        )

        profile_data["original_resume"]["projects"][0]["description"] = []
        github.readme_calls.clear()
        github.readme = README + "\nNow also exports attendance as CSV."

        asyncio.run(
            enrich_project_descriptions(
                profile_data, [repo("Sem4_UMS", repo_id=11, pushed_at="2026-06-01T00:00:00Z")]
            )
        )

        assert github.readme_calls == ["Sem4_UMS"]

    def test_a_readme_that_never_yields_bullets_is_not_retried_forever(self, github):
        github.bullets = {}
        repos = [repo("Sem4_UMS", repo_id=11)]
        profile_data = profile_with([scanned_project("Sem4_UMS", repo_id=11)])

        asyncio.run(enrich_project_descriptions(profile_data, repos))
        github.readme_calls.clear()
        github.generated_for.clear()

        asyncio.run(enrich_project_descriptions(profile_data, repos))

        assert github.readme_calls == []
        assert github.generated_for == []

    def test_only_a_bounded_batch_goes_into_one_llm_call(self, github):
        repos = [repo(f"repo-{i}", repo_id=i) for i in range(ge.MAX_ENRICHMENT_REPOS + 4)]
        projects = [scanned_project(f"repo-{i}", repo_id=i) for i in range(len(repos))]

        asyncio.run(enrich_project_descriptions(profile_with(projects), repos))

        assert len(github.readme_calls) == ge.MAX_ENRICHMENT_REPOS
        assert len(github.generated_for) == ge.MAX_ENRICHMENT_REPOS

    def test_the_cache_lives_in_the_existing_github_sync_dict(self, github):
        repos = [repo("Sem4_UMS", repo_id=11)]
        profile_data = profile_with(
            [scanned_project("Sem4_UMS", repo_id=11)],
            github_sync={"username": OWNER, "repo_count": 1},
        )

        asyncio.run(enrich_project_descriptions(profile_data, repos))

        sync_state = profile_data["github_sync"]
        assert sync_state["username"] == OWNER
        cached = sync_state["readme_signatures"][f"{OWNER}/sem4_ums"]
        assert cached["signature"] == _readme_signature(README, {"Python": 900, "HTML": 100})
        assert cached["pushed_at"] == "2026-01-01T00:00:00Z"


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    """Answers whatever the test queued, keyed by URL suffix."""

    def __init__(self, responses):
        self._responses = responses

    async def get(self, url, **kwargs):
        for suffix, response in self._responses.items():
            if url.endswith(suffix):
                if isinstance(response, Exception):
                    raise response
                return response
        return FakeResponse(404)


class TestFetchHelpers:
    def test_readme_is_base64_decoded(self):
        encoded = base64.b64encode(README.encode("utf-8")).decode("ascii")
        # GitHub wraps its base64 payload at 60 characters.
        wrapped = "\n".join(encoded[i : i + 60] for i in range(0, len(encoded), 60))
        client = FakeClient(
            {"/readme": FakeResponse(200, {"content": wrapped, "encoding": "base64"})}
        )

        assert asyncio.run(_fetch_repo_readme(client, OWNER, "Sem4_UMS")) == README

    def test_a_repo_without_a_readme_returns_none(self):
        client = FakeClient({"/readme": FakeResponse(404)})

        assert asyncio.run(_fetch_repo_readme(client, OWNER, "Sem4_UMS")) is None

    def test_an_unexpected_encoding_returns_none(self):
        """Files over 1MB come back with encoding "none" and no content."""
        client = FakeClient({"/readme": FakeResponse(200, {"content": "", "encoding": "none"})})

        assert asyncio.run(_fetch_repo_readme(client, OWNER, "Sem4_UMS")) is None

    def test_a_transport_failure_returns_none(self):
        client = FakeClient({"/readme": RuntimeError("connection reset")})

        assert asyncio.run(_fetch_repo_readme(client, OWNER, "Sem4_UMS")) is None

    def test_languages_come_back_as_the_byte_map(self):
        client = FakeClient({"/languages": FakeResponse(200, {"Python": 900, "HTML": 100})})

        languages = asyncio.run(_fetch_repo_languages(client, OWNER, "Sem4_UMS"))

        assert languages == {"Python": 900, "HTML": 100}

    def test_unavailable_languages_read_as_empty(self):
        client = FakeClient({"/languages": FakeResponse(403)})

        assert asyncio.run(_fetch_repo_languages(client, OWNER, "Sem4_UMS")) == {}


class TestLanguageBreakdown:
    def test_renders_percentages_largest_first(self):
        assert _language_breakdown({"HTML": 100, "Python": 900}) == "Python 90%, HTML 10%"

    def test_no_languages_reads_as_unknown(self):
        assert _language_breakdown({}) == "unknown"
