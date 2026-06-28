import styles from "./FeaturesSection.module.css";

const features = [
  {
    id: "profile-intelligence",
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <circle cx="14" cy="10" r="5" stroke="currentColor" strokeWidth="1.75" />
        <path d="M5 24c0-4.97 4.03-9 9-9s9 4.03 9 9" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M20 8l1.5 1.5L24 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    color: "#6366f1",
    bg: "rgba(99, 102, 241, 0.1)",
    border: "rgba(99, 102, 241, 0.2)",
    title: "Profile Intelligence Agent",
    description:
      "Analyzes your resume to infer suitable job roles, career level, skill categories, and profile completeness. Builds the enriched profile that powers all AI features.",
    tags: ["Career Level Detection", "Skill Categorization", "Profile Scoring"],
  },
  {
    id: "job-matching",
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <rect x="3" y="7" width="22" height="16" rx="3" stroke="currentColor" strokeWidth="1.75" />
        <path d="M9 5v2M19 5v2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M3 12h22" stroke="currentColor" strokeWidth="1.5" />
        <path d="M8 17h4M16 17h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    color: "#06b6d4",
    bg: "rgba(6, 182, 212, 0.1)",
    border: "rgba(6, 182, 212, 0.2)",
    title: "Job Matching Agent",
    description:
      "Compares your enriched profile with live job listings to surface the most compatible opportunities, explains the match, and highlights gaps to close.",
    tags: ["Compatibility Ranking", "Skill Gap Analysis", "Match Explanation"],
  },
  {
    id: "resume-optimizer",
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <rect x="5" y="3" width="18" height="22" rx="3" stroke="currentColor" strokeWidth="1.75" />
        <path d="M9 9h10M9 13h10M9 17h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="21" cy="21" r="5" fill="currentColor" fillOpacity="0.1" stroke="currentColor" strokeWidth="1.5" />
        <path d="M19.5 21h3M21 19.5v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    color: "#f59e0b",
    bg: "rgba(245, 158, 11, 0.1)",
    border: "rgba(245, 158, 11, 0.2)",
    title: "Resume Optimization Agent",
    description:
      "Generates a tailored, ATS-optimized resume for each job description — adjusting the summary, highlighting relevant skills, and inserting the right keywords.",
    tags: ["ATS Optimization", "Keyword Tailoring", "JD-Aligned Summary"],
  },
  {
    id: "resume-parsing",
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <path d="M6 4h11l5 5v15a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2z" stroke="currentColor" strokeWidth="1.75" />
        <path d="M17 4v5h5" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
        <path d="M10 13l2 2 4-4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    color: "#10b981",
    bg: "rgba(16, 185, 129, 0.1)",
    border: "rgba(16, 185, 129, 0.2)",
    title: "Resume Parsing Service",
    description:
      "Extracts structured information from your PDF or DOCX resume — education, experience, projects, skills, and certifications — into a clean JSON format.",
    tags: ["PDF & DOCX Support", "Structured JSON Output", "Section Detection"],
  },
  {
    id: "auth",
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <rect x="6" y="12" width="16" height="12" rx="3" stroke="currentColor" strokeWidth="1.75" />
        <path d="M10 12V9a4 4 0 018 0v3" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
        <circle cx="14" cy="18" r="2" fill="currentColor" />
      </svg>
    ),
    color: "#8b5cf6",
    bg: "rgba(139, 92, 246, 0.1)",
    border: "rgba(139, 92, 246, 0.2)",
    title: "Secure Authentication",
    description:
      "Enterprise-grade session management powered by Supabase. Your data stays yours — isolated, encrypted, and accessible only by you.",
    tags: ["Supabase Auth", "Session Management", "Data Isolation"],
  },
  {
    id: "job-service",
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
        <circle cx="14" cy="14" r="10" stroke="currentColor" strokeWidth="1.75" />
        <path d="M14 4v10l6 3" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    color: "#f43f5e",
    bg: "rgba(244, 63, 94, 0.1)",
    border: "rgba(244, 63, 94, 0.2)",
    title: "Real-time Job Service",
    description:
      "Integrates with external job providers to retrieve, normalize, and cache job postings. Always fresh listings with smart filtering.",
    tags: ["Live Job Feeds", "Smart Caching", "Normalized Data"],
  },
];

export default function FeaturesSection() {
  return (
    <section className={styles.section} id="features">
      <div className="container">
        <div className={styles.header}>
          <div className="badge badge-primary">Features</div>
          <h2 className={styles.title}>
            Everything your career
            <br />
            <span className="gradient-text">needs to thrive</span>
          </h2>
          <p className={styles.subtitle}>
            From intelligent profile analysis to ATS-optimized resumes — CareerOS gives you
            the AI edge at every step of your job search.
          </p>
        </div>

        <div className={styles.grid}>
          {features.map((f, i) => (
            <div
              key={f.id}
              className={styles.card}
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <div
                className={styles.iconWrap}
                style={{ background: f.bg, border: `1px solid ${f.border}`, color: f.color }}
              >
                {f.icon}
              </div>
              <h3 className={styles.cardTitle}>{f.title}</h3>
              <p className={styles.cardDesc}>{f.description}</p>
              <div className={styles.tags}>
                {f.tags.map((tag) => (
                  <span key={tag} className={styles.tag} style={{ color: f.color, background: f.bg, borderColor: f.border }}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
