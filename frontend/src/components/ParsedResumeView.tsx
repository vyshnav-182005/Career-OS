"use client";

import type { ParsedResume } from "@/lib/types/resume";
import styles from "./ParsedResumeView.module.css";

interface ParsedResumeViewProps {
  resume: ParsedResume;
  filename: string;
  onReset: () => void;
}

export default function ParsedResumeView({ resume, filename, onReset }: ParsedResumeViewProps) {
  const { personal_info, experience, education, projects, certifications, skills, languages } = resume;

  return (
    <div className={styles.wrapper}>
      {/* Header bar */}
      <div className={styles.topBar}>
        <div className={styles.topBarLeft}>
          <div className={styles.successDot} aria-hidden="true" />
          <div>
            <p className={styles.topBarTitle}>Resume parsed successfully</p>
            <p className={styles.topBarFile}>{filename}</p>
          </div>
        </div>
        <button className={styles.resetBtn} onClick={onReset} aria-label="Upload a different resume">
          Upload another
        </button>
      </div>

      <div className={styles.content}>
        {/* Personal Info */}
        {personal_info && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>👤</span>
              <h2 className={styles.sectionTitle}>Personal Info</h2>
            </div>
            <div className={styles.infoGrid}>
              {personal_info.name && <InfoItem label="Name" value={personal_info.name} />}
              {personal_info.email && <InfoItem label="Email" value={personal_info.email} />}
              {personal_info.phone && <InfoItem label="Phone" value={personal_info.phone} />}
              {personal_info.location && <InfoItem label="Location" value={personal_info.location} />}
              {personal_info.linkedin && (
                <InfoItem label="LinkedIn" value={personal_info.linkedin} href={personal_info.linkedin} />
              )}
              {personal_info.github && (
                <InfoItem label="GitHub" value={personal_info.github} href={personal_info.github} />
              )}
              {personal_info.website && (
                <InfoItem label="Website" value={personal_info.website} href={personal_info.website} />
              )}
            </div>
            {personal_info.summary && (
              <p className={styles.summary}>{personal_info.summary}</p>
            )}
          </section>
        )}

        {/* Skills */}
        {skills.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>⚡</span>
              <h2 className={styles.sectionTitle}>Skills</h2>
            </div>
            <div className={styles.skillsGrid}>
              {skills.map((cat) => (
                <div key={cat.category} className={styles.skillCategory}>
                  <p className={styles.skillCategoryLabel}>{cat.category}</p>
                  <div className={styles.pillRow}>
                    {cat.skills.map((s) => (
                      <span key={s} className={styles.pill}>{s}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {languages.length > 0 && (
              <div className={styles.skillCategory} style={{ marginTop: "1rem" }}>
                <p className={styles.skillCategoryLabel}>Languages</p>
                <div className={styles.pillRow}>
                  {languages.map((l) => (
                    <span key={l} className={`${styles.pill} ${styles.pillAlt}`}>{l}</span>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* Experience */}
        {experience.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>💼</span>
              <h2 className={styles.sectionTitle}>Experience</h2>
            </div>
            <div className={styles.timeline}>
              {experience.map((exp, i) => (
                <div key={i} className={styles.timelineItem}>
                  <div className={styles.timelineDot} aria-hidden="true" />
                  <div className={styles.timelineContent}>
                    <div className={styles.timelineHeader}>
                      <div>
                        <p className={styles.timelineTitle}>{exp.title}</p>
                        <p className={styles.timelineOrg}>{exp.company}{exp.location ? ` · ${exp.location}` : ""}</p>
                      </div>
                      <span className={styles.timelineDates}>
                        {exp.start_date ?? ""}
                        {exp.end_date ? ` – ${exp.end_date}` : exp.is_current ? " – Present" : ""}
                      </span>
                    </div>
                    {exp.responsibilities.length > 0 && (
                      <ul className={styles.bullets}>
                        {exp.responsibilities.map((r, j) => (
                          <li key={j}>{r}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Education */}
        {education.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>🎓</span>
              <h2 className={styles.sectionTitle}>Education</h2>
            </div>
            <div className={styles.timeline}>
              {education.map((edu, i) => (
                <div key={i} className={styles.timelineItem}>
                  <div className={styles.timelineDot} aria-hidden="true" />
                  <div className={styles.timelineContent}>
                    <div className={styles.timelineHeader}>
                      <div>
                        <p className={styles.timelineTitle}>{edu.institution}</p>
                        <p className={styles.timelineOrg}>
                          {[edu.degree, edu.field_of_study].filter(Boolean).join(" · ")}
                          {edu.gpa ? ` · GPA: ${edu.gpa}` : ""}
                        </p>
                      </div>
                      <span className={styles.timelineDates}>
                        {edu.start_date ?? ""}
                        {edu.end_date ? ` – ${edu.end_date}` : ""}
                      </span>
                    </div>
                    {edu.description && <p className={styles.timelineDesc}>{edu.description}</p>}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Projects */}
        {projects.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>🚀</span>
              <h2 className={styles.sectionTitle}>Projects</h2>
            </div>
            <div className={styles.projectsGrid}>
              {projects.map((proj, i) => (
                <div key={i} className={styles.projectCard}>
                  <div className={styles.projectHeader}>
                    <p className={styles.projectName}>{proj.name}</p>
                    {proj.url && (
                      <a href={proj.url} target="_blank" rel="noopener noreferrer" className={styles.projectLink} aria-label={`Visit ${proj.name}`}>
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M5 2H2a1 1 0 00-1 1v9a1 1 0 001 1h9a1 1 0 001-1V9M8 1h5m0 0v5m0-5L6 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </a>
                    )}
                  </div>
                  {proj.description && <p className={styles.projectDesc}>{proj.description}</p>}
                  {proj.technologies.length > 0 && (
                    <div className={styles.pillRow} style={{ marginTop: "0.5rem" }}>
                      {proj.technologies.map((t) => (
                        <span key={t} className={`${styles.pill} ${styles.pillSm}`}>{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Certifications */}
        {certifications.length > 0 && (
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>🏅</span>
              <h2 className={styles.sectionTitle}>Certifications</h2>
            </div>
            <div className={styles.certList}>
              {certifications.map((cert, i) => (
                <div key={i} className={styles.certItem}>
                  <p className={styles.certName}>{cert.name}</p>
                  <p className={styles.certMeta}>
                    {[cert.issuer, cert.date].filter(Boolean).join(" · ")}
                    {cert.credential_id ? ` · ID: ${cert.credential_id}` : ""}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function InfoItem({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className={styles.infoItem}>
      <span className={styles.infoLabel}>{label}</span>
      {href ? (
        <a href={href.startsWith("http") ? href : `https://${href}`} target="_blank" rel="noopener noreferrer" className={styles.infoLink}>
          {value}
        </a>
      ) : (
        <span className={styles.infoValue}>{value}</span>
      )}
    </div>
  );
}
