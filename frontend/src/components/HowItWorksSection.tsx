"use client";

import styles from "./HowItWorksSection.module.css";

export default function HowItWorksSection() {
  const steps = [
    {
      num: "01",
      title: "Upload your resume",
      desc: "Drop your PDF or DOCX file and our AI extracts all the structured data."
    },
    {
      num: "02",
      title: "Get AI insights",
      desc: "We analyze your skills, experience, and projects to build your career profile."
    },
    {
      num: "03",
      title: "Land your dream job",
      desc: "Match with relevant opportunities and generate tailored applications."
    }
  ];

  return (
    <section id="how-it-works" className={styles.section}>
      <div className="container">
        <h2 className={styles.title}>How it works</h2>
        <div className={styles.steps}>
          {steps.map((step, i) => (
            <div key={i} className={styles.step}>
              <span className={styles.stepNumber}>{step.num}</span>
              <h3 className={styles.stepTitle}>{step.title}</h3>
              <p className={styles.stepDesc}>{step.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
