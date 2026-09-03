# CareerOS: Comprehensive Project Documentation

## 1. Introduction

**CareerOS** is an intelligent, multi-agent career guidance platform. Its primary goal is to provide end-to-end assistance for job seekers by analyzing their profiles, finding jobs aligned with their skills and experience, and optimizing their resumes to match specific Job Descriptions (JDs) and their comprehensive user profile.

The system is highly modular, split between deterministic **Services** (handling file management, database interactions, API integrations, and parsing) and AI-driven **Agents** (handling reasoning tasks using Large Language Models to produce intelligent outputs).

## 2. System Architecture

The architecture is built around a modern microservices-style approach orchestrated by a central workflow manager.

### 2.1 High-Level Flow
1. **Frontend**: Next.js Dashboard interacts with users.
2. **Gateway**: A FastAPI backend acts as the gateway and orchestrates the services.
3. **Core Services**: Include Authentication, Resume Management, and Application Tracking.
4. **AI Workflow**: Resume Parsing feeds into the Verification Engine, which builds a User Profile. The Workflow Orchestrator then coordinates various AI Agents (Profile Intelligence, Job Matching, Resume Optimization).

### 2.2 Core Services

- **Authentication Service**: Handles user registration, login, and session validation using NextAuth v5 (Auth.js).
- **Resume Management Service**: Manages the upload, storage, versioning, and retrieval of both original and optimized resume versions.
- **Resume Parsing Service**: Utilizes `PyMuPDF` and `python-docx` to extract structured information from resumes and converts it into a strictly validated `ResumeSchema`.
- **User Profile Service**: Stores and manages the "canonical" user profile. This includes the parsed `ResumeSchema` and the AI-generated Career Profile.
- **Job Service**: Integrates with external providers (like Jooble) to fetch job listings, normalizes and classifies them into a fixed role-family taxonomy, deduplicates via content hashing, and exposes search/filter/recommendation endpoints.
- **Application Service**: Tracks the entire lifecycle of job applications, including interview stages, offers, and historical application data.

### 2.3 AI Agents

The "brain" of CareerOS consists of several specialized AI agents powered by NVIDIA NIM (Llama 3.1) and OpenAI SDKs.

- **Profile Intelligence Agent**: Analyzes the `ResumeSchema` to infer career levels, preferred roles, strengths, weaknesses, domains, and a career summary. It also fetches and analyzes GitHub links from the resume to gather deeper insights into the user's projects.
- **Job Matching Agent**: Recommendation is a two-stage pipeline. First, `backend/services/job_matching.py` runs hybrid retrieval - `Sentence-Transformers` vector similarity, Postgres full-text search, and direct role-family lookup, fused with Reciprocal Rank Fusion - hard-gated by a fixed role-family taxonomy (`backend/services/taxonomy.py`) so an out-of-family job is structurally unreachable regardless of embedding similarity. Second, `backend/agents/job_matching_agent.py` sends the top candidates to the LLM in a single batched call to catch near-misses (right family, wrong seniority or a missing core skill), returning a verdict, score, one-line reason, and matched/missing skills per job. Results are cached per `(user, job, profile_version)` so only genuinely new candidates hit the LLM; a failed or slow LLM call falls back to the Phase 2 feature ranking rather than breaking the endpoint.
- **Resume Optimization Agent**: Automatically generates a job-specific, ATS-optimized resume tailored to a specific Job Description, while strictly preserving the factual correctness of the user's background.

### 2.4 Verification Engine

To ensure data integrity and prevent AI hallucinations, the **Verification Engine** sits between every parsing step and AI agent output. It performs:
- Schema validation (via Pydantic).
- Rule validation and cross-validation.
- Optional LLM-based verification before persisting data to the database.

### 2.5 Workflow Orchestrator

The **Workflow Orchestrator** decouples agent execution. Instead of agents calling each other directly, the orchestrator determines which agent to run based on user actions. It manages retries, tracks progress, and logs execution. This allows agents to be highly reusable across different workflows (e.g., initial resume upload vs. a manual job refresh).

## 3. Technology Stack

CareerOS employs a robust, modern tech stack designed for scalability and AI integration.

- **Frontend**: Next.js 16 (App Router, React 19, TypeScript)
- **Authentication**: NextAuth v5
- **Database**: Supabase (PostgreSQL with JSONB support for flexible schema storage)
- **Backend**: FastAPI (Python 3.11) running on Uvicorn
- **Data Processing**: PyMuPDF, python-docx, Pydantic, Playwright (for web scraping if necessary)
- **AI & ML**: NVIDIA NIM (Llama 3.1), OpenAI SDK, Sentence-Transformers
- **Task Management**: Concurrently (Node.js), APScheduler (Python)

## 4. Conclusion

CareerOS represents a next-generation approach to career management. By combining deterministic traditional web services with advanced, orchestrated AI agents and a strict Verification Engine, it provides highly personalized, accurate, and actionable career guidance, from initial profile creation to final job application.
