"use client";

import { useState } from "react";
import { optimizeResume } from "@/lib/api/resumeOptimizer";
import styles from "./ResumeOptimizer.module.css";

export default function ResumeOptimizer() {
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pdfContent, setPdfContent] = useState<string | null>(null);

  async function handleOptimize(e: React.FormEvent) {
    e.preventDefault();
    if (!jobTitle || !jobDescription) return;

    setError(null);
    setLoading(true);
    setStatusMessage(null);
    setPdfContent(null);

    try {
      const result = await optimizeResume(jobTitle, jobDescription, (status) => {
        setStatusMessage(status.message);
      });
      const pdf = result.data?.pdf_content;
      if (result.success && pdf) {
        setPdfContent(pdf);
        setStatusMessage(result.message);
      } else {
        throw new Error(result.message || "Optimization failed.");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.formContainer}>
        <h2 className={styles.title}>Tailor Your Resume</h2>
        <p className={styles.subtitle}>
          Paste the Job Title and Job Description to get an ATS-optimized PDF resume.
        </p>

        <form onSubmit={handleOptimize} className={styles.form}>
          <div className={styles.inputGroup}>
            <label htmlFor="jobTitle">Target Job Title</label>
            <input
              id="jobTitle"
              type="text"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="e.g. Senior Software Engineer"
              required
              disabled={loading}
              className={styles.input}
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="jobDescription">Job Description</label>
            <textarea
              id="jobDescription"
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              placeholder="Paste the full job description here..."
              required
              disabled={loading}
              className={styles.textarea}
              rows={8}
            />
          </div>

          <button type="submit" disabled={loading || !jobTitle || !jobDescription} className={styles.button}>
            {loading ? (
              <>
                <span className={styles.spinner} aria-hidden="true" />
                Optimizing...
              </>
            ) : (
              "Generate Optimized Resume"
            )}
          </button>
        </form>

        {statusMessage && !error && <div className={styles.statusAlert}>{statusMessage}</div>}
        {error && <div className={styles.errorAlert}>{error}</div>}
      </div>

      {pdfContent && (
        <div className={styles.resultContainer}>
          <div className={styles.resultHeader}>
            <h3>Generated PDF Resume</h3>
            <a 
              href={`data:application/pdf;base64,${pdfContent}`} 
              download="Optimized_Resume.pdf"
              className={styles.copyButton}
              style={{ textDecoration: 'none' }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Download PDF
            </a>
          </div>
          <div style={{ height: '600px', width: '100%', marginTop: '1rem' }}>
            <object
              data={`data:application/pdf;base64,${pdfContent}`}
              type="application/pdf"
              width="100%"
              height="100%"
            >
              <p>Your browser does not support PDFs. <a href={`data:application/pdf;base64,${pdfContent}`} download="Optimized_Resume.pdf">Download the PDF</a>.</p>
            </object>
          </div>
        </div>
      )}
    </div>
  );
}
