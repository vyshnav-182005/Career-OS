import type { ProfileIntelligence } from "@/lib/types/resume";
import styles from "./ProfileIntelligenceView.module.css";

interface Props {
  intelligence: ProfileIntelligence;
}

export default function ProfileIntelligenceView({ intelligence }: Props) {
  const {
    career_level,
    total_years_experience,
    profile_completeness,
    professional_summary,
    inferred_job_roles,
    skill_categories,
    key_strengths,
    industry_domains,
  } = intelligence;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.iconWrapper}>
            <span role="img" aria-label="sparkle">✨</span>
          </div>
          <h2 className={styles.title}>Profile Intelligence</h2>
        </div>
        <div className={styles.badge}>
          <span className={styles.badgeDot} />
          {career_level} Level
        </div>
      </div>

      <div className={styles.grid}>
        {/* Left Column */}
        <div className={styles.leftCol}>
          {/* Score Card */}
          <div className={styles.scoreCard}>
            <div className={styles.scoreGauge}>
              <svg viewBox="0 0 36 36" className={styles.circularChart}>
                <path
                  className={styles.circleBg}
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <path
                  className={styles.circle}
                  strokeDasharray={`${profile_completeness.overall_score}, 100`}
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <text x="18" y="20.35" className={styles.percentage}>
                  {profile_completeness.overall_score}%
                </text>
              </svg>
            </div>
            <div className={styles.scoreInfo}>
              <h3>Profile Completeness</h3>
              <p>Based on industry standards</p>
              <div className={styles.scoreStats}>
                <span>{total_years_experience} Years Exp.</span>
              </div>
            </div>
          </div>

          {/* Key Strengths */}
          <div className={styles.card}>
            <h3 className={styles.cardTitle}>Key Strengths</h3>
            <ul className={styles.strengthsList}>
              {key_strengths.map((strength, idx) => (
                <li key={idx}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="8" fill="#10b981" fillOpacity="0.2" />
                    <path d="M4.5 8L7 10.5L11.5 5.5" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {strength}
                </li>
              ))}
            </ul>
          </div>

          {/* Industry Domains */}
          <div className={styles.card}>
            <h3 className={styles.cardTitle}>Industry Domains</h3>
            <div className={styles.tagList}>
              {industry_domains.map((domain, idx) => (
                <span key={idx} className={styles.tag}>{domain}</span>
              ))}
            </div>
          </div>

          {/* Improvement Suggestions */}
          {profile_completeness.improvement_suggestions.length > 0 && (
            <div className={`${styles.card} ${styles.improvementsCard}`}>
              <h3 className={styles.cardTitle}>Suggestions to Improve</h3>
              <ul className={styles.improvementsList}>
                {profile_completeness.improvement_suggestions.map((suggestion, idx) => (
                  <li key={idx}>
                    <span className={styles.bullet}>•</span>
                    {suggestion}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Right Column */}
        <div className={styles.rightCol}>
          {/* Summary */}
          {professional_summary && (
            <div className={styles.summaryCard}>
              <h3 className={styles.cardTitle}>Professional Summary</h3>
              <p className={styles.summaryText}>{professional_summary}</p>
            </div>
          )}

          {/* Inferred Roles */}
          <div className={styles.card}>
            <h3 className={styles.cardTitle}>Inferred Job Roles</h3>
            <div className={styles.rolesList}>
              {inferred_job_roles.map((role, idx) => (
                <div key={idx} className={styles.roleItem}>
                  <div className={styles.roleHeader}>
                    <h4>{role.title}</h4>
                    <span className={`${styles.confidence} ${styles[role.confidence.toLowerCase()]}`}>
                      {role.confidence} Match
                    </span>
                  </div>
                  <p>{role.reasoning}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Skill Categories */}
          <div className={styles.card}>
            <h3 className={styles.cardTitle}>Skill Analysis</h3>
            <div className={styles.skillsGrid}>
              {skill_categories.map((cat, idx) => (
                <div key={idx} className={styles.skillCategory}>
                  <div className={styles.skillCatHeader}>
                    <h4>{cat.category}</h4>
                    <span className={styles.proficiency}>{cat.proficiency_level}</span>
                  </div>
                  <div className={styles.tagList}>
                    {cat.skills.map((skill, sIdx) => (
                      <span key={sIdx} className={styles.skillTag}>{skill}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
