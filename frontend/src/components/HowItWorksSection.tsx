import styles from "./HowItWorksSection.module.css";

const steps = [
  {
    number: "01",
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path d="M8 4h11l7 7v17a2 2 0 01-2 2H8a2 2 0 01-2-2V6a2 2 0 012-2z" stroke="currentColor" strokeWidth="1.75" />
        <path d="M19 4v7h7" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
        <path d="M11 16h10M11 21h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    title: "Upload Your Resume",
    description:
      "Upload your existing resume in PDF or DOCX format. Our parser extracts every detail — education, experience, projects, and skills — into a clean, structured format.",
  },
  {
    number: "02",
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="1.75" />
        <path d="M16 10v6l4 2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M7 7l2 2M23 7l-2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    title: "AI Profile Analysis",
    description:
      "The Profile Intelligence Agent analyzes your resume to infer your career level, ideal roles, skill strengths, and completeness score — building your enriched career profile.",
  },
  {
    number: "03",
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <rect x="4" y="8" width="24" height="18" rx="3" stroke="currentColor" strokeWidth="1.75" />
        <path d="M4 14h24" stroke="currentColor" strokeWidth="1.5" />
        <path d="M10 21h4M18 21h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M13 4l3 4 3-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    title: "Discover Matched Jobs",
    description:
      "The Job Matching Agent scans live listings and ranks the most compatible opportunities for you — complete with match percentage, reasoning, and skill gap insights.",
  },
  {
    number: "04",
    icon: (
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <rect x="6" y="4" width="20" height="24" rx="3" stroke="currentColor" strokeWidth="1.75" />
        <path d="M11 10h10M11 15h10M11 20h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="24" cy="24" r="6" fill="var(--color-bg)" stroke="currentColor" strokeWidth="1.5" />
        <path d="M22 24h4M24 22v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
    title: "Generate Tailored Resume",
    description:
      "Pick a job and let the Resume Optimization Agent craft an ATS-friendly, keyword-optimized version of your resume perfectly tailored to that specific role.",
  },
];

export default function HowItWorksSection() {
  return (
    <section className={styles.section} id="how-it-works">
      <div className="container">
        <div className={styles.header}>
          <div className="badge badge-primary">How it works</div>
          <h2 className={styles.title}>
            From resume to
            <br />
            <span className="gradient-text">dream offer in 4 steps</span>
          </h2>
          <p className={styles.subtitle}>
            CareerOS streamlines your entire job search into a simple, intelligent workflow
            powered by specialized AI agents.
          </p>
        </div>

        <div className={styles.steps}>
          {steps.map((step, i) => (
            <div key={step.number} className={styles.step}>
              {/* Connector line */}
              {i < steps.length - 1 && (
                <div className={styles.connector} aria-hidden="true" />
              )}

              <div className={styles.stepLeft}>
                <div className={styles.iconWrap} aria-hidden="true">
                  {step.icon}
                  <div className={styles.stepNumber}>{step.number}</div>
                </div>
              </div>

              <div className={styles.stepContent}>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepDesc}>{step.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
