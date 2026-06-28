# CareerOS

> An AI-powered multi-agent career guidance platform. Analyze your resume, discover matched jobs, and generate ATS-optimized applications.

## Project Structure

```
Career-OS/
├── package.json                     # Root — `npm run dev` starts everything
├── venv/                            # Python virtual environment (project root)
├── supabase_migration.sql           # Run in Supabase SQL Editor
│
├── frontend/                        # Next.js 16 App Router (TypeScript)
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx             # Landing page
│   │   │   ├── layout.tsx           # Root layout (SEO, fonts)
│   │   │   ├── globals.css          # Design system (dark theme)
│   │   │   ├── api/
│   │   │   │   └── parse-resume/
│   │   │   │       └── route.ts     # API route → spawns Python pipeline
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx
│   │   │   │   └── register/page.tsx
│   │   │   ├── dashboard/page.tsx
│   │   │   └── auth/signout/route.ts
│   │   ├── components/
│   │   │   ├── Navbar.tsx / .module.css
│   │   │   ├── HeroSection.tsx / .module.css
│   │   │   ├── FeaturesSection.tsx / .module.css
│   │   │   ├── HowItWorksSection.tsx / .module.css
│   │   │   ├── Footer.tsx / .module.css
│   │   │   ├── ResumeUploader.tsx / .module.css
│   │   │   ├── ParsedResumeView.tsx / .module.css
│   │   │   └── ProfileIntelligenceView.tsx / .module.css
│   │   ├── lib/
│   │   │   ├── api/resumeParser.ts  # Calls /api/parse-resume
│   │   │   ├── types/resume.ts      # TS types (ParsedResume, ProfileIntelligence)
│   │   │   └── supabase/
│   │   │       ├── client.ts        # Browser Supabase client
│   │   │       └── server.ts        # Server Supabase client
│   │   └── proxy.ts                 # Route protection (Next.js 16)
│   └── .env                         # Supabase keys + server-only secrets
│
└── services/
    └── resume-parser/               # Python 3.11 parsing + intelligence
        ├── run_pipeline.py          # CLI entry point (subprocess)
        ├── app/
        │   ├── main.py              # FastAPI app (legacy, kept for reference)
        │   ├── parser.py            # PDF/DOCX extraction + NVIDIA NIM
        │   ├── models.py            # Pydantic: ParsedResume schemas
        │   ├── profile_models.py    # Pydantic: ProfileIntelligence schemas
        │   ├── profile_agent.py     # Profile Intelligence Agent
        │   ├── supabase_client.py   # Supabase JSONB persistence
        │   └── config.py            # Settings from env vars
        └── requirements.txt
```

## Getting Started

### 1. Prerequisites

- **Node.js** (v18+)
- **Python 3.11+**
- A **Supabase** project (free tier works)
- An **NVIDIA NIM** API key

### 2. Fill in environment variables

Edit `frontend/.env`:
```env
# Public (browser)
NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Server-only (API routes only — never sent to browser)
NVIDIA_API_KEY=<your-nvidia-nim-key>
SUPABASE_SERVICE_KEY=<your-service-role-key>
```

### 3. Run the Supabase migration

Go to your Supabase Dashboard → **SQL Editor** → paste the contents of `supabase_migration.sql` → Run.

This creates the `profiles` table with a `profile_data JSONB` column for storing enriched profile data.

### 4. One-time setup

```bash
cd Career-OS
npm run setup
```

This installs frontend npm packages, creates a Python venv at the project root, and installs Python dependencies.

### 5. Start development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — that's it. No separate backend commands needed.

## Architecture

```
Browser → Next.js API Route (/api/parse-resume) → Python subprocess
                                                     ├── Resume Parser        → ParsedResume (Pydantic)
                                                     ├── Profile Intelligence → ProfileIntelligence (Pydantic)
                                                     ├── Supabase upsert      → profiles.profile_data (JSONB)
                                                     └── stdout JSON          → API route → Browser
```

- **Single server**: Next.js on `:3000` handles both frontend and API
- **No CORS**: frontend and API share the same origin
- **Python as subprocess**: parsing/intelligence runs on-demand, not as a persistent server

## Pipeline Flow

1. User uploads resume (PDF/DOCX) in the dashboard
2. Next.js API route validates the file and authenticates the user
3. Python subprocess extracts text (PyMuPDF / python-docx) and calls NVIDIA NIM
4. **Resume Parser** produces a validated `ParsedResume` Pydantic model
5. `ParsedResume` is automatically passed to the **Profile Intelligence Agent**
6. Agent infers: suitable job roles, career level, skill categories, profile completeness
7. Agent produces a validated `ProfileIntelligence` Pydantic model
8. `ProfileIntelligence` is serialized to JSON and persisted in Supabase `profiles.profile_data` JSONB column
9. Complete result is returned to the browser and displayed in the dashboard

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router, TypeScript) |
| Auth | Supabase Auth |
| Database | Supabase (PostgreSQL, JSONB) |
| Resume Parsing | Python 3.11 + PyMuPDF + python-docx |
| AI Extraction | NVIDIA NIM (Llama 3.1 70B Instruct) |
| Profile Intelligence | Python 3.11 + NVIDIA NIM |
| Persistence | supabase-py (service role) |

## Phase 1 Status

- [x] Landing page (Hero, Features, How It Works, Footer)
- [x] Authentication (Login, Register, Protected Dashboard)
- [x] Resume Parsing Service (PDF/DOCX → structured JSON via NVIDIA NIM)
- [x] Profile Intelligence Agent (enriched career profile with JSONB persistence)
- [x] Unified dev command (`npm run dev` from root)
- [ ] Resume Management Service
- [ ] User Profile Service
- [ ] Job Service
- [ ] Job Matching Agent
- [ ] Resume Optimization Agent