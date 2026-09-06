"""Covers the profile editor's save path and what a re-parse must not delete.

Certifications and publications are maintained by hand between resume uploads,
and `original_resume` used to be replaced wholesale on every parse - so the
merge tested here is the one place in this feature where getting it wrong loses
the user's own data rather than merely annoying them.
"""

import pytest
from pydantic import ValidationError

from backend.db import supabase_client
from backend.models.resume import ParsedResume
from backend.models.schemas import ProfileEditRequest, ProjectDescriptionEdit
from backend.services import profile_editing
from backend.services.profile_editing import ProfileNotFoundError, save_profile_edit
from backend.services.profile_sections import (
    apply_project_description_edits,
    merge_reparsed_sections,
)


def cert(name, issuer=None, date=None, credential_id=None):
    return {"name": name, "issuer": issuer, "date": date, "credential_id": credential_id}


def pub(title, publisher=None, date=None, url=None):
    return {"title": title, "publisher": publisher, "date": date, "url": url}


class TestReparseMerge:
    def test_a_hand_added_certification_survives_a_re_parse(self):
        """The whole point: the resume that gets re-uploaded predates it."""
        existing = {"certifications": [cert("AWS Solutions Architect", "Amazon")]}
        parsed = {"certifications": [cert("Google Data Analytics", "Google")]}

        merged = merge_reparsed_sections(existing, parsed)

        assert [c["name"] for c in merged["certifications"]] == [
            "AWS Solutions Architect",
            "Google Data Analytics",
        ]

    def test_the_same_certification_is_not_duplicated(self):
        existing = {"certifications": [cert("AWS Solutions Architect", "Amazon")]}
        parsed = {"certifications": [cert("  aws solutions architect ", "AMAZON")]}

        merged = merge_reparsed_sections(existing, parsed)

        assert len(merged["certifications"]) == 1
        assert merged["certifications"][0]["name"] == "AWS Solutions Architect"

    def test_a_matched_entry_keeps_its_edits_but_gains_missing_fields(self):
        existing = {"certifications": [cert("CKA", "CNCF", date="March 2026")]}
        parsed = {"certifications": [cert("CKA", "CNCF", date="2026", credential_id="LF-99")]}

        merged = merge_reparsed_sections(existing, parsed)

        entry = merged["certifications"][0]
        # The hand-corrected date stands; the id the resume carried is added.
        assert entry["date"] == "March 2026"
        assert entry["credential_id"] == "LF-99"

    def test_publications_merge_on_title_and_publisher(self):
        existing = {"publications": [pub("A Study of Things", "IEEE")]}
        parsed = {
            "publications": [
                pub("A Study of Things", "IEEE", url="https://example.com"),
                pub("A Study of Things", "ACM"),
            ]
        }

        merged = merge_reparsed_sections(existing, parsed)

        assert len(merged["publications"]) == 2
        assert merged["publications"][0]["url"] == "https://example.com"
        assert merged["publications"][1]["publisher"] == "ACM"

    def test_everything_else_still_comes_from_the_new_resume(self):
        existing = {
            "certifications": [cert("CKA", "CNCF")],
            "experience": [{"company": "Old Corp", "title": "Intern"}],
        }
        parsed = {
            "certifications": [],
            "experience": [{"company": "New Corp", "title": "Engineer"}],
        }

        merged = merge_reparsed_sections(existing, parsed)

        assert merged["experience"] == [{"company": "New Corp", "title": "Engineer"}]
        assert len(merged["certifications"]) == 1

    def test_an_empty_stored_profile_is_just_the_parse(self):
        parsed = {"certifications": [cert("CKA", "CNCF")], "publications": []}

        assert merge_reparsed_sections({}, parsed)["certifications"] == parsed["certifications"]


class TestUpsertPreservesHandKeptData:
    """The merge has to be wired into the save path, not just available to it."""

    @pytest.fixture
    def stored(self, monkeypatch):
        state = {"row": None}

        class FakeStorage:
            def upload(self, **kwargs):
                return None

            def get_public_url(self, path):
                return f"https://storage.test/{path}"

        class FakeTable:
            def upsert(self, row, on_conflict=None):
                state["row"] = row
                return self

            def execute(self):
                return None

        class FakeClient:
            storage = type("S", (), {"from_": staticmethod(lambda bucket: FakeStorage())})()

            def table(self, name):
                return FakeTable()

        monkeypatch.setattr(supabase_client, "get_supabase_client", lambda: FakeClient())
        monkeypatch.setattr(
            supabase_client,
            "get_profile_data",
            lambda user_id: {
                "original_resume": {
                    "certifications": [cert("AWS Solutions Architect", "Amazon")],
                    "publications": [pub("A Study of Things", "IEEE")],
                },
                "github_summary": "existing summary",
                "github_sync": {"username": "someone", "readme_signatures": {"a/b": {}}},
                "strengths": ["stale"],
            },
        )
        return state

    def test_a_re_parse_keeps_hand_added_entries_and_github_state(self, stored):
        supabase_client.upsert_parsed_resume(
            "u1", ParsedResume(), b"pdf-bytes", "application/pdf", "resume.pdf"
        )

        profile_data = stored["row"]["profile_data"]
        resume = profile_data["original_resume"]

        assert [c["name"] for c in resume["certifications"]] == ["AWS Solutions Architect"]
        assert [p["title"] for p in resume["publications"]] == ["A Study of Things"]
        # The README cache describes the GitHub account, not this file.
        assert profile_data["github_summary"] == "existing summary"
        assert profile_data["github_sync"]["readme_signatures"] == {"a/b": {}}
        # These two are re-derived by the workflow that runs next.
        assert profile_data["strengths"] == []


class TestProjectDescriptionEdits:
    def test_an_edit_marks_the_description_as_the_users(self):
        projects = [{"name": "Career-OS", "description": ["Old line"], "url": None}]

        updated, unmatched = apply_project_description_edits(
            projects, [ProjectDescriptionEdit(name="Career-OS", description=["New line"])]
        )

        assert (updated, unmatched) == (1, [])
        assert projects[0]["description"] == ["New line"]
        assert projects[0]["description_source"] == "user"

    def test_saving_untouched_text_does_not_claim_it(self):
        """Otherwise opening a modal would freeze generated bullets forever."""
        projects = [
            {
                "name": "Career-OS",
                "description": ["Generated line"],
                "description_source": "ai_generated",
                "url": None,
            }
        ]

        updated, _ = apply_project_description_edits(
            projects, [ProjectDescriptionEdit(name="Career-OS", description=["Generated line"])]
        )

        assert updated == 0
        assert projects[0]["description_source"] == "ai_generated"

    def test_the_link_identifies_the_project_over_its_name(self):
        projects = [
            {"name": "Renamed locally", "description": ["Old"], "url": "https://github.com/o/r"},
            {"name": "Career-OS", "description": ["Other"], "url": "https://github.com/o/other"},
        ]

        apply_project_description_edits(
            projects,
            [
                ProjectDescriptionEdit(
                    name="Career-OS", url="https://github.com/o/r/", description=["New"]
                )
            ],
        )

        assert projects[0]["description"] == ["New"]
        assert projects[1]["description"] == ["Other"]

    def test_an_edit_matching_nothing_is_reported_not_swallowed(self):
        updated, unmatched = apply_project_description_edits(
            [], [ProjectDescriptionEdit(name="Ghost", description=["Line"])]
        )

        assert (updated, unmatched) == (0, ["Ghost"])

    def test_an_empty_description_is_refused_at_the_boundary(self):
        with pytest.raises(ValidationError) as err:
            ProjectDescriptionEdit(name="Career-OS", description=["   ", ""])

        assert "at least one line" in str(err.value)


class TestSaveProfileEdit:
    @pytest.fixture
    def profile(self, monkeypatch):
        state = {
            "data": {
                "original_resume": {
                    "certifications": [cert("CKA", "CNCF")],
                    "publications": [],
                    "projects": [{"name": "Career-OS", "description": ["Old"], "url": None}],
                }
            },
            "saved": None,
        }

        monkeypatch.setattr(profile_editing, "get_profile_data", lambda user_id: state["data"])

        def save(user_id, profile_data, bump_version=True):
            state["saved"] = (profile_data, bump_version)
            return True

        monkeypatch.setattr(profile_editing, "save_profile_data", save)
        return state

    def test_saving_only_publications_leaves_certifications_alone(self, profile):
        """A section absent from the request must not read as "emptied"."""
        result = save_profile_edit(
            ProfileEditRequest(user_id="u1", publications=[pub("New paper", "IEEE")])
        )

        resume = profile["saved"][0]["original_resume"]
        assert result.success is True
        assert [c["name"] for c in resume["certifications"]] == ["CKA"]
        assert [p["title"] for p in resume["publications"]] == ["New paper"]

    def test_removing_a_certification_persists_the_shorter_list(self, profile):
        """The editor sends the whole list back, so a present section replaces."""
        save_profile_edit(ProfileEditRequest(user_id="u1", certifications=[]))

        assert profile["saved"][0]["original_resume"]["certifications"] == []

    def test_editing_bullets_bumps_the_profile_version(self, profile):
        result = save_profile_edit(
            ProfileEditRequest(
                user_id="u1",
                project_descriptions=[
                    ProjectDescriptionEdit(name="Career-OS", description=["New line"])
                ],
            )
        )

        profile_data, bump_version = profile["saved"]
        assert result.projects_updated == 1
        # Changed profile text has to re-key the cached job matches.
        assert bump_version is True
        assert profile_data["original_resume"]["projects"][0]["description_source"] == "user"

    def test_a_no_op_save_writes_nothing(self, profile):
        result = save_profile_edit(
            ProfileEditRequest(
                user_id="u1",
                project_descriptions=[
                    ProjectDescriptionEdit(name="Career-OS", description=["Old"])
                ],
            )
        )

        assert result.success is True
        assert result.message == "No changes to save."
        assert profile["saved"] is None

    def test_a_profile_that_was_never_parsed_says_so(self, monkeypatch):
        monkeypatch.setattr(profile_editing, "get_profile_data", lambda user_id: None)

        with pytest.raises(ProfileNotFoundError):
            save_profile_edit(ProfileEditRequest(user_id="u1", certifications=[]))
