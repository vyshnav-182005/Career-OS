"use client";

import { useRef, useState, DragEvent, ChangeEvent } from "react";
import { parseResume } from "@/lib/api/resumeParser";
import type { ParsedResume, ProfileIntelligence } from "@/lib/types/resume";
import styles from "./ResumeUploader.module.css";

interface ResumeUploaderProps {
  onParsed: (resume: ParsedResume, filename: string, intelligence: ProfileIntelligence | null) => void;
}

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
];
const MAX_MB = 10;

export default function ResumeUploader({ onParsed }: ResumeUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string>("");

  function validateFile(file: File): string | null {
    if (!ACCEPTED_TYPES.includes(file.type) && !file.name.match(/\.(pdf|docx|doc)$/i)) {
      return "Only PDF and DOCX files are supported.";
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      return `File must be under ${MAX_MB} MB.`;
    }
    return null;
  }

  async function handleFile(file: File) {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setLoading(true);
    setProgress("Uploading resume…");

    try {
      setProgress("Parsing with Gemini AI…");
      const result = await parseResume(file);

      if (!result.success || !result.parsed_resume) {
        throw new Error(result.error ?? "Parsing failed. Please try again.");
      }

      onParsed(result.parsed_resume, file.name, result.profile_intelligence);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
      setError(
        msg.includes("fetch")
          ? "Could not reach the resume parser service. Make sure the backend is running on port 8000."
          : msg
      );
    } finally {
      setLoading(false);
      setProgress("");
    }
  }

  function onDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(true);
  }

  function onDragLeave() {
    setDragging(false);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  }

  return (
    <div className={styles.wrapper}>
      <div
        className={`${styles.dropzone} ${dragging ? styles.dragging : ""} ${loading ? styles.uploading : ""}`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !loading && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload resume — click or drag and drop"
        onKeyDown={(e) => e.key === "Enter" && !loading && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className={styles.hiddenInput}
          onChange={onFileChange}
          disabled={loading}
          aria-hidden="true"
        />

        {loading ? (
          <div className={styles.loadingState}>
            <div className={styles.spinner} aria-hidden="true" />
            <p className={styles.loadingText}>{progress}</p>
            <p className={styles.loadingSubtext}>This may take 60–90 seconds for deep analysis…</p>
          </div>
        ) : (
          <div className={styles.idleState}>
            <div className={styles.uploadIcon} aria-hidden="true">
              <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
                <rect width="36" height="36" rx="10" fill="url(#upload-grad)" />
                <path
                  d="M18 23V13M18 13L14 17M18 13L22 17"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M12 26h12"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <defs>
                  <linearGradient id="upload-grad" x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#6366f1" />
                    <stop offset="1" stopColor="#06b6d4" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <p className={styles.dropText}>
              {dragging ? "Drop your resume here" : "Drag & drop your resume"}
            </p>
            <p className={styles.dropSubtext}>or click to browse files</p>
            <p className={styles.dropHint}>PDF or DOCX · Max {MAX_MB} MB</p>
          </div>
        )}
      </div>

      {error && (
        <div className={styles.errorAlert} role="alert">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="7" stroke="#f87171" strokeWidth="1.5" />
            <path d="M8 5v4M8 11v.5" stroke="#f87171" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          {error}
        </div>
      )}
    </div>
  );
}
