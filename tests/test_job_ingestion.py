import unittest
from unittest.mock import patch

from backend.models.job import NormalizedJob
from backend.services import job_ingestion
from backend.services.job_ingestion import JobIngestionWorkflow
from backend.services.job_providers.base import BaseJobProvider


def _job(provider_job_id: str, title: str = "Backend Engineer") -> NormalizedJob:
    return NormalizedJob(
        provider="jooble",
        provider_job_id=provider_job_id,
        title=title,
        company="Acme",
        description="Build things.",
        skills=["Python"],
    )


class FakeProvider(BaseJobProvider):
    def __init__(self, jobs):
        self._jobs = jobs

    @property
    def provider_name(self) -> str:
        return "jooble"

    def fetch_jobs(self, query=None):
        return self._jobs


class JobIngestionEmbeddingTests(unittest.TestCase):
    def _run(self, jobs, embedding_side_effect, existing_hashes=None):
        """
        Runs the workflow with embedding generation stubbed.

        `embedding_side_effect` is still written per job - (title, desc, skills)
        -> embedding, or an exception to raise - and is adapted here to the
        batched generate_job_embeddings the workflow actually calls, so each
        test still reads as a statement about one job's outcome.
        """
        provider = FakeProvider(jobs)
        workflow = JobIngestionWorkflow(providers=[provider])

        if existing_hashes is None:
            existing_hashes = {"existing-1": "stale-hash"}

        def batched(job_tuples):
            if isinstance(embedding_side_effect, BaseException):
                raise embedding_side_effect
            return [embedding_side_effect(*job_tuple) for job_tuple in job_tuples]

        with patch.object(job_ingestion, "generate_job_embeddings", side_effect=batched) as mock_embed, \
             patch.object(job_ingestion, "get_active_provider_job_hashes", return_value=existing_hashes), \
             patch.object(job_ingestion, "upsert_jobs") as mock_upsert, \
             patch.object(job_ingestion, "delete_expired_jobs"):
            stats = workflow.run(query="Backend Engineer")

        return stats, mock_upsert, mock_embed

    def test_embedding_generated_for_both_new_and_already_active_jobs(self):
        jobs = [_job("existing-1"), _job("new-1")]

        stats, mock_upsert, mock_embed = self._run(
            jobs, embedding_side_effect=lambda title, desc, skills: [0.1, 0.2]
        )

        self.assertEqual(stats.updated, 1)
        self.assertEqual(stats.inserted, 1)
        self.assertEqual(stats.skipped, 0)

        upserted = mock_upsert.call_args[0][0]
        self.assertEqual(len(upserted), 2)
        self.assertTrue(all(job_dict.get("embedding") == [0.1, 0.2] for job_dict in upserted))
        # Both jobs go out in a single encode call rather than one call each.
        mock_embed.assert_called_once()
        self.assertEqual(len(mock_embed.call_args[0][0]), 2)

    def test_job_skipped_and_not_upserted_when_embedding_is_none(self):
        jobs = [_job("existing-1"), _job("new-1")]

        stats, mock_upsert, _ = self._run(jobs, embedding_side_effect=lambda title, desc, skills: None)

        self.assertEqual(stats.skipped, 2)
        upserted = mock_upsert.call_args[0][0]
        self.assertEqual(upserted, [])

    def test_job_skipped_when_embedding_generation_raises(self):
        jobs = [_job("new-1")]

        stats, mock_upsert, _ = self._run(
            jobs, embedding_side_effect=RuntimeError("model unavailable")
        )

        self.assertEqual(stats.skipped, 1)
        upserted = mock_upsert.call_args[0][0]
        self.assertEqual(upserted, [])

    def test_unchanged_job_skips_reembedding_and_omits_embedding_key(self):
        job = _job("existing-1")
        unchanged_hash = job_ingestion.compute_content_hash(
            job.title, job.company, job.description, job.skills
        )

        stats, mock_upsert, mock_embed = self._run(
            [job],
            embedding_side_effect=lambda title, desc, skills: [0.1, 0.2],
            existing_hashes={"existing-1": unchanged_hash},
        )

        self.assertEqual(stats.updated, 1)
        self.assertEqual(stats.skipped, 0)
        mock_embed.assert_not_called()

        upserted = mock_upsert.call_args[0][0]
        self.assertEqual(len(upserted), 1)
        self.assertNotIn("embedding", upserted[0])

    def test_changed_job_is_reembedded(self):
        job = _job("existing-1")

        stats, mock_upsert, mock_embed = self._run(
            [job],
            embedding_side_effect=lambda title, desc, skills: [0.3, 0.4],
            existing_hashes={"existing-1": "some-other-hash"},
        )

        self.assertEqual(stats.skipped, 0)
        # One batched call covering the job, not one call per job.
        mock_embed.assert_called_once()
        self.assertEqual(len(mock_embed.call_args[0][0]), 1)

        upserted = mock_upsert.call_args[0][0]
        self.assertEqual(upserted[0].get("embedding"), [0.3, 0.4])

    def test_role_family_and_content_hash_set_on_upsert(self):
        job = _job("new-1", title="DevOps Engineer")

        stats, mock_upsert, _ = self._run([job], embedding_side_effect=lambda title, desc, skills: [0.1, 0.2])

        upserted = mock_upsert.call_args[0][0]
        self.assertEqual(upserted[0].get("role_family"), "devops-sre")
        self.assertTrue(upserted[0].get("content_hash"))
        self.assertTrue(upserted[0].get("last_seen_at"))


if __name__ == "__main__":
    unittest.main()
