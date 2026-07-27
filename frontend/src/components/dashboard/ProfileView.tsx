"use client";

import { useState } from "react";

import type { ParsedResume, ProfileIntelligence } from "@/lib/types/resume";
import styles from "./ProfileView.module.css";

interface ProfileViewProps {
  resume: ParsedResume;
  filename: string;
  intelligence: ProfileIntelligence | null;
  onReset: () => void;
}

export default function ProfileView({ resume, filename, intelligence, onReset }: ProfileViewProps) {
  const [selectedProjectIndex, setSelectedProjectIndex] = useState<number | null>(null);

  const {
    personal_info,
    experience,
    education,
    projects,
    certifications,
    skills,
    languages,
    publications = [],
    custom_sections = [],
  } = resume;

  const strengths = intelligence?.strengths ?? [];
  const preferred_job_roles = intelligence?.preferred_job_roles ?? [];

  return (
    <div className={styles.wrapper}>
      {/* Success banner */}
      <div className={styles.banner}>
        <div className={styles.bannerLeft}>
          <div className={styles.successDot} aria-hidden="true" />
          <div>
            <p className={styles.bannerTitle}>Resume parsed successfully</p>
            <p className={styles.bannerFile}>{filename}</p>
          </div>
        </div>
        <button className={styles.resetBtn} onClick={onReset}>
          Upload another
        </button>
      </div>

      <div className={styles.content}>
        {/* Personal Info */}
        {personal_info && (
          <section className={styles.section}>
            <div className={styles.personalHeader}>
              {personal_info.name && (
                <h1 className={styles.personName}>{personal_info.name}</h1>
              )}
              {personal_info.summary && (
                <p className={styles.personSummary}>{personal_info.summary}</p>
              )}
              <div className={styles.contactRow}>
                {personal_info.email && (
                  <a href={`mailto:${personal_info.email}`} className={styles.contactLink}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                    {personal_info.email}
                  </a>
                )}
                {personal_info.phone && (
                  <span className={styles.contactItem}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                    {personal_info.phone}
                  </span>
                )}
                {personal_info.location && (
                  <span className={styles.contactItem}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
                    {personal_info.location}
                  </span>
                )}
                {personal_info.linkedin && (
                  <a href={personal_info.linkedin.startsWith("http") ? personal_info.linkedin : `https://${personal_info.linkedin}`} target="_blank" rel="noopener noreferrer" className={styles.contactLink}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/></svg>
                    LinkedIn
                  </a>
                )}
                {personal_info.github && (
                  <a href={personal_info.github.startsWith("http") ? personal_info.github : `https://${personal_info.github}`} target="_blank" rel="noopener noreferrer" className={styles.contactLink}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/></svg>
                    GitHub
                  </a>
                )}
                {personal_info.website && (
                  <a href={personal_info.website.startsWith("http") ? personal_info.website : `https://${personal_info.website}`} target="_blank" rel="noopener noreferrer" className={styles.contactLink}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    Website
                  </a>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Strengths */}
        {strengths.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Strengths</h2>
            <div className={styles.pillRow}>
              {strengths.map((s, i) => (
                <span key={i} className={styles.strengthPill}>{s}</span>
              ))}
            </div>
          </section>
        )}

        {/* Preferred Job Roles */}
        {preferred_job_roles.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Recommended Roles</h2>
            <div className={styles.rolesGrid}>
              {preferred_job_roles.map((role, i) => (
                <div key={i} className={styles.roleCard}>
                  <div className={styles.roleHeader}>
                    <h3 className={styles.roleTitle}>{role.title}</h3>
                    <span className={`${styles.confidenceBadge} ${
                      role.confidence.toLowerCase() === "high" ? styles.confidenceHigh :
                      role.confidence.toLowerCase() === "low" ? styles.confidenceLow :
                      styles.confidenceMedium
                    }`}>
                      {role.confidence}
                    </span>
                  </div>
                  <p className={styles.roleReasoning}>{role.reasoning}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Skills — Category Placards */}
        {skills.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Skills</h2>
            <div className={styles.skillsGrid}>
              {skills.map((cat) => (
                <div key={cat.category} className={styles.skillPlacard}>
                  <h3 className={styles.skillPlacardTitle}>{cat.category}</h3>
                  <div className={styles.pillRow}>
                    {cat.skills.map((s) => (
                      <span key={s} className={styles.skillPill}>{s}</span>
                    ))}
                  </div>
                </div>
              ))}
              {languages.length > 0 && (
                <div className={styles.skillPlacard}>
                  <h3 className={styles.skillPlacardTitle}>Languages</h3>
                  <div className={styles.pillRow}>
                    {languages.map((l) => (
                      <span key={l} className={styles.skillPill}>{l}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Experience */}
        {experience && experience.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Experience</h2>
            <div className={styles.entryList}>
              {experience.map((exp, i) => (
                <div key={i} className={styles.entry}>
                  <div className={styles.entryHeader}>
                    <div>
                      <p className={styles.entryTitle}>{exp.title}</p>
                      <p className={styles.entryOrg}>
                        {exp.company}{exp.location ? ` · ${exp.location}` : ""}
                      </p>
                    </div>
                    <span className={styles.entryDate}>
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
              ))}
            </div>
          </section>
        )}

        {/* Education */}
        {education.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Education</h2>
            <div className={styles.entryList}>
              {education.map((edu, i) => (
                <div key={i} className={styles.entry}>
                  <div className={styles.entryHeader}>
                    <div>
                      <p className={styles.entryTitle}>{edu.institution}</p>
                      <p className={styles.entryOrg}>
                        {[edu.degree, edu.field_of_study].filter(Boolean).join(" · ")}
                        {edu.gpa ? ` · GPA: ${edu.gpa}` : ""}
                      </p>
                    </div>
                    <span className={styles.entryDate}>
                      {edu.start_date ?? ""}
                      {edu.end_date ? ` – ${edu.end_date}` : ""}
                    </span>
                  </div>
                  {edu.description && <p className={styles.entryDesc}>{edu.description}</p>}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Projects */}
        {projects.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Projects</h2>
            <div className={styles.projectsGrid}>
              {projects.map((proj, i) => (
                <div key={i} className={styles.projectCard} onClick={() => setSelectedProjectIndex(i)} style={{ cursor: "pointer" }}>
                  <div className={styles.projectHeader}>
                    <p className={styles.projectName}>{proj.name}</p>
                    {proj.url && (
                      <a href={proj.url} target="_blank" rel="noopener noreferrer" className={styles.externalLink} aria-label={`Visit ${proj.name}`} onClick={(e) => e.stopPropagation()}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </a>
                    )}
                  </div>
                  {/* Preview text if we want, otherwise leave just title for cleaner look */}
                </div>
              ))}
            </div>
            
            {/* Project Modal Overlay */}
            {selectedProjectIndex !== null && projects[selectedProjectIndex] && (
              <div className={styles.modalOverlay} onClick={() => setSelectedProjectIndex(null)}>
                <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
                  <button className={styles.closeButton} onClick={() => setSelectedProjectIndex(null)} aria-label="Close modal">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                  
                  <div className={styles.projectHeader} style={{ paddingRight: '2rem', alignItems: 'flex-start' }}>
                    <h2 className={styles.sectionTitle} style={{ margin: 0, paddingRight: '1rem' }}>{projects[selectedProjectIndex].name}</h2>
                    {projects[selectedProjectIndex].url && (
                      <a href={projects[selectedProjectIndex].url} target="_blank" rel="noopener noreferrer" className={styles.externalLink} style={{ fontSize: '0.875rem', whiteSpace: 'nowrap', flexShrink: 0, marginTop: '0.25rem' }}>
                        View Project
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </a>
                    )}
                  </div>

                  {projects[selectedProjectIndex].description && projects[selectedProjectIndex].description.length > 0 && (
                    <ul className={styles.bullets} style={{ marginTop: '0.5rem', marginBottom: '0.5rem' }}>
                      {projects[selectedProjectIndex].description.map((desc, j) => (
                        <li key={j} className={styles.projectDesc} style={{ fontSize: '0.9375rem' }}>{desc}</li>
                      ))}
                    </ul>
                  )}
                  
                  {projects[selectedProjectIndex].technologies && projects[selectedProjectIndex].technologies.length > 0 && (
                    <div style={{ marginTop: '0.5rem' }}>
                      <p style={{ fontSize: '0.8125rem', color: 'var(--color-text-tertiary)', marginBottom: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tech Stack</p>
                      <div className={styles.pillRow}>
                        {projects[selectedProjectIndex].technologies.map((t) => (
                          <span key={t} className={styles.techPill} style={{ fontSize: '0.8125rem', padding: '0.3rem 0.6rem' }}>{t}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        )}

        {/* Certifications */}
        {certifications.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Certifications</h2>
            <div className={styles.entryList}>
              {certifications.map((cert, i) => (
                <div key={i} className={styles.entry}>
                  {(() => {
                    let displayName = cert.name;
                    let displayIssuer = cert.issuer;
                    
                    if (displayIssuer) {
                      if (displayName.endsWith(` - ${displayIssuer}`)) displayName = displayName.slice(0, -(` - ${displayIssuer}`.length));
                      else if (displayName.endsWith(` – ${displayIssuer}`)) displayName = displayName.slice(0, -(` – ${displayIssuer}`.length));
                      else if (displayName.endsWith(` — ${displayIssuer}`)) displayName = displayName.slice(0, -(` — ${displayIssuer}`.length));
                    } else {
                      // Fallback: Try to extract issuer from the title if missing
                      const match = displayName.match(/^(.*?)\s+[-–—]\s+(.+)$/);
                      if (match) {
                        displayName = match[1];
                        displayIssuer = match[2];
                      }
                    }

                    return (
                      <>
                        <p className={styles.entryTitle}>{displayName}</p>
                        <p className={styles.entryOrg}>
                          {[displayIssuer, cert.date].filter(Boolean).join(" · ")}
                          {cert.credential_id ? ` · ID: ${cert.credential_id}` : ""}
                        </p>
                      </>
                    );
                  })()}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Publications */}
        {publications.length > 0 && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Publications</h2>
            <div className={styles.entryList}>
              {publications.map((pub, i) => (
                <div key={i} className={styles.entry}>
                  <div className={styles.entryHeader}>
                    <div>
                      <p className={styles.entryTitle}>{pub.title}</p>
                      {pub.publisher && <p className={styles.entryOrg}>{pub.publisher}</p>}
                    </div>
                    {pub.date && <span className={styles.entryDate}>{pub.date}</span>}
                  </div>
                  {pub.url && (
                    <a href={pub.url} target="_blank" rel="noopener noreferrer" className={styles.externalLink} style={{ marginTop: 4 }}>
                      View Publication
                    </a>
                  )}
                  {pub.description && <p className={styles.entryDesc}>{pub.description}</p>}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Custom Sections */}
        {custom_sections.map((section, idx) => (
          <section key={idx} className={styles.section}>
            <h2 className={styles.sectionTitle}>{section.section_title}</h2>
            <div className={styles.entryList}>
              {section.items.map((item, i) => (
                <div key={i} className={styles.entry}>
                  <div className={styles.entryHeader}>
                    <div>
                      {item.title && <p className={styles.entryTitle}>{item.title}</p>}
                      {item.subtitle && <p className={styles.entryOrg}>{item.subtitle}</p>}
                    </div>
                    {item.date && <span className={styles.entryDate}>{item.date}</span>}
                  </div>
                  {item.description && <p className={styles.entryDesc}>{item.description}</p>}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
