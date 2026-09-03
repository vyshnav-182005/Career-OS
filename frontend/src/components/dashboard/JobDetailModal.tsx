"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Job } from "@/lib/types/job";
import { generateResumeForJob, type WorkflowStatusResponse } from "@/lib/api/resumeOptimizer";
import { analyzeJobFit, type JobFitAnalysis } from "@/lib/api/jobFitAnalysis";
import { toDescriptionBlocks } from "@/lib/utils/jobText";
import styles from "./JobDetailModal.module.css";

interface JobDetailModalProps {
  job: Job;
  hasProfile: boolean;
  onClose: () => void;
  /**
   * Start generating the optimized resume as soon as the modal opens. Set when
   * the user pressed "Optimize Resume" on the job card — that click is the
   * request, so making them press Generate again here would be a dead step.
   */
  autoGenerate?: boolean;
}

function scoreTier(score: number): "good" | "fair" | "poor" {
  if (score >= 75) return "good";
  if (score >= 50) return "fair";
  return "poor";
}

export default function JobDetailModal({ job, hasProfile, onClose, autoGenerate = false }: JobDetailModalProps) {
  const [generating, setGenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pdfContent, setPdfContent] = useState<string | null>(null);

  const [analysis, setAnalysis] = useState<JobFitAnalysis | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());
  // Guards the auto-start against React StrictMode's double effect invocation
  // in development, which would otherwise fire two generation workflows.
  const autoGenerateFired = useRef(false);

  const applyUrl = job.url || job.raw_payload?.redirect_url || job.raw_payload?.url || job.raw_payload?.link;

  // Provider descriptions are HTML fragments; this strips the markup and
  // rebuilds real paragraphs and bullet lists so the posting is readable.
  const descriptionBlocks = useMemo(() => toDescriptionBlocks(job.description), [job.description]);

  async function runAnalysis(forceRefresh = false) {
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const result = await analyzeJobFit(job.id, forceRefresh);
      setAnalysis(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to analyze job fit.";
      setAnalysisError(msg);
    } finally {
      setAnalysisLoading(false);
    }
  }

  useEffect(() => {
    if (hasProfile) {
      runAnalysis();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, hasProfile]);

  useEffect(() => {
    if (!autoGenerate || !hasProfile || autoGenerateFired.current) return;
    autoGenerateFired.current = true;
    handleGenerate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoGenerate, hasProfile]);

  function toggleProject(name: string) {
    setExpandedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  async function handleGenerate() {
    if (generating) return;

    setGenerating(true);
    setError(null);
    setStatusMessage(null);
    setPdfContent(null);

    try {
      const result = await generateResumeForJob(job.id, (status: WorkflowStatusResponse) => {
        setStatusMessage(status.message);
      });
      const pdf = result.data?.pdf_content;
      if (result.success && pdf) {
        setPdfContent(pdf);
        setStatusMessage(result.message);
      } else {
        throw new Error(result.message || "Resume generation failed.");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
      setError(msg);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        <button className={styles.closeButton} onClick={onClose} aria-label="Close job details">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <div className={styles.header}>
          <h2 className={styles.title}>{job.title}</h2>
          <p className={styles.company}>
            {job.company} • {job.location || "Remote"}
          </p>
          <div className={styles.tags}>
            <span className={styles.tag}>{job.employment_type || "Full-time"}</span>
            {job.salary && <span className={styles.tagSalary}>{job.salary}</span>}
            {job.provider && <span className={styles.tagProvider}>via {job.provider}</span>}
          </div>
        </div>

        {job.skills && job.skills.length > 0 && (
          <div className={styles.skills}>
            {job.skills.map((skill) => (
              <span key={skill} className={styles.skillChip}>{skill}</span>
            ))}
          </div>
        )}

        {descriptionBlocks.length > 0 && (
          <section className={styles.descriptionSection}>
            <h4 className={styles.descriptionHeading}>Job Description</h4>
            <div className={styles.description}>
              {descriptionBlocks.map((block, i) =>
                block.type === "list" ? (
                  <ul key={`d-${i}`} className={styles.descriptionList}>
                    {block.items.map((item, j) => (
                      <li key={`d-${i}-${j}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p key={`d-${i}`} className={styles.descriptionParagraph}>
                    {block.text}
                  </p>
                )
              )}
            </div>
          </section>
        )}

        {hasProfile && (
          <div className={styles.fitSection}>
            {analysisLoading ? (
              <div className={styles.fitLoading}>
                <span className={styles.spinner} aria-hidden="true" />
                Analyzing fit against this job...
              </div>
            ) : analysisError ? (
              <div className={styles.errorAlert}>
                {analysisError}{" "}
                <button type="button" className={styles.retryLink} onClick={() => runAnalysis()}>
                  Retry
                </button>
              </div>
            ) : analysis?.ats_score ? (
              <>
                <div className={styles.scoreCard}>
                  <div className={`${styles.scoreCircle} ${styles[scoreTier(analysis.ats_score.overall_score)]}`}>
                    <span className={styles.scoreNumber}>{analysis.ats_score.overall_score}</span>
                    <span className={styles.scoreLabel}>ATS Fit</span>
                  </div>
                  <div className={styles.scoreBreakdown}>
                    {[
                      { label: "Skill match", value: analysis.ats_score.skill_match_pct },
                      { label: "Project relevance", value: analysis.ats_score.project_relevance_score },
                      { label: "Experience relevance", value: analysis.ats_score.experience_relevance_score },
                      { label: "Education match", value: analysis.ats_score.education_match_score },
                    ].map((row) => (
                      <div key={row.label} className={styles.scoreRow}>
                        <span className={styles.scoreRowLabel}>{row.label}</span>
                        <div className={styles.scoreBarTrack}>
                          <div
                            className={`${styles.scoreBarFill} ${styles[scoreTier(row.value)]}`}
                            style={{ width: `${Math.max(0, Math.min(100, row.value))}%` }}
                          />
                        </div>
                        <span className={styles.scoreRowValue}>{row.value}</span>
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    className={styles.reanalyzeBtn}
                    onClick={() => runAnalysis(true)}
                    disabled={analysisLoading}
                  >
                    Re-analyze
                  </button>
                </div>

                {analysis.ats_score.missing_keywords.length > 0 && (
                  <div className={styles.missingKeywords}>
                    <h4>Missing keywords</h4>
                    <div className={styles.keywordChips}>
                      {analysis.ats_score.missing_keywords.map((kw) => (
                        <span key={kw} className={styles.keywordChip}>{kw}</span>
                      ))}
                    </div>
                  </div>
                )}

                {analysis.ats_score.suggestions.length > 0 && (
                  <div className={styles.suggestions}>
                    <h4>Suggestions</h4>
                    <ul>
                      {analysis.ats_score.suggestions.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {analysis.optimized_projects.length > 0 && (
                  <div className={styles.optimizedProjects}>
                    <h4>Optimized project bullets</h4>
                    {analysis.optimized_projects.map((project) => {
                      const expanded = expandedProjects.has(project.project_name);
                      return (
                        <div key={project.project_name} className={styles.projectCard}>
                          <div className={styles.projectCardHeader}>
                            <strong>{project.project_name}</strong>
                            {project.technologies.length > 0 && (
                              <div className={styles.projectTech}>
                                {project.technologies.map((t) => (
                                  <span key={t} className={styles.skillChip}>{t}</span>
                                ))}
                              </div>
                            )}
                          </div>
                          <ul className={styles.bulletList}>
                            {project.optimized_bullets.map((bullet, i) => (
                              <li key={i}>{bullet}</li>
                            ))}
                          </ul>
                          <button
                            type="button"
                            className={styles.toggleOriginalBtn}
                            onClick={() => toggleProject(project.project_name)}
                          >
                            {expanded ? "Hide original bullets" : "Show original bullets"}
                          </button>
                          {expanded && (
                            <ul className={`${styles.bulletList} ${styles.originalBulletList}`}>
                              {project.original_bullets.map((bullet, i) => (
                                <li key={i}>{bullet}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            ) : null}
          </div>
        )}

        {job.feature_scores && (
          <details className={styles.whyMatch}>
            <summary>Why this match?</summary>
            <div className={styles.featureScoreGrid}>
              {[
                { label: "Semantic similarity", value: job.feature_scores.semantic },
                { label: "Skill overlap", value: job.feature_scores.skill_overlap },
                { label: "Family fit", value: job.feature_scores.family_fit },
                { label: "Seniority fit", value: job.feature_scores.seniority_fit },
                { label: "Recency", value: job.feature_scores.recency },
              ].map((row) => (
                <div key={row.label} className={styles.featureScoreRow}>
                  <span>{row.label}</span>
                  <span>{row.value.toFixed(2)}</span>
                </div>
              ))}
              {job.score !== undefined && (
                <div className={`${styles.featureScoreRow} ${styles.featureScoreTotal}`}>
                  <span>Agent score</span>
                  <span>{job.score}</span>
                </div>
              )}
            </div>
          </details>
        )}

        <div className={styles.actions}>
          {applyUrl && (
            <a href={applyUrl} target="_blank" rel="noopener noreferrer" className={styles.applyBtn}>
              Apply Now
            </a>
          )}
          <button
            type="button"
            className={styles.generateBtn}
            onClick={handleGenerate}
            disabled={generating || !hasProfile}
            title={!hasProfile ? "Upload your resume in the Overview tab first" : undefined}
          >
            {generating ? (
              <>
                <span className={styles.spinner} aria-hidden="true" />
                Generating...
              </>
            ) : (
              "Generate Optimized Resume"
            )}
          </button>
        </div>

        {!hasProfile && (
          <p className={styles.hint}>Upload and parse your resume in the Overview tab to enable this.</p>
        )}

        {statusMessage && !error && <div className={styles.statusAlert}>{statusMessage}</div>}
        {error && <div className={styles.errorAlert}>{error}</div>}

        {pdfContent && (
          <div className={styles.resultContainer}>
            <div className={styles.resultHeader}>
              <h3>Optimized Resume</h3>
              <a
                href={`data:application/pdf;base64,${pdfContent}`}
                download="Optimized_Resume.pdf"
                className={styles.downloadBtn}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download PDF
              </a>
            </div>
            <object
              data={`data:application/pdf;base64,${pdfContent}`}
              type="application/pdf"
              className={styles.pdfPreview}
            >
              <p>Your browser does not support PDFs. <a href={`data:application/pdf;base64,${pdfContent}`} download="Optimized_Resume.pdf">Download the PDF</a>.</p>
            </object>
          </div>
        )}
      </div>
    </div>
  );
}
