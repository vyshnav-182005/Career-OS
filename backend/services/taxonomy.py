"""
Deterministic role-family and skill taxonomy for job matching.

No LLM calls and no network access anywhere in this module — classification at
ingest time has to run over thousands of jobs cheaply and predictably. Everything
here is plain pattern matching over static tables.
"""

import re

# The fixed set of role families every job and every profile search_intent is
# classified into. Downstream phases treat this list as closed — the LLM prompt
# in profile_intelligence_agent.py is instructed to pick only from these slugs,
# and server-side validation drops anything else.
ROLE_FAMILIES: list[str] = [
    "frontend",
    "backend",
    "fullstack",
    "mobile",
    "data-engineering",
    "data-science",
    "ml-engineering",
    "devops-sre",
    "cloud-infra",
    "qa-testing",
    "security",
    "embedded",
    "product-design",
    "technical-writing",
]

# Case-insensitive regex patterns matched against a job title. Checked in
# ROLE_FAMILIES order, first match wins, so more specific families should list
# more specific patterns rather than relying on ordering tricks. A title that
# matches nothing returns None from classify_title rather than a guess.
FAMILY_TITLE_PATTERNS: dict[str, list[str]] = {
    "frontend": [
        r"front[\s-]?end",
        r"\bui\s+(?:developer|engineer)\b",
        r"\breact\s+developer\b",
        r"\bangular\s+developer\b",
        r"\bvue\s+developer\b",
        r"\bweb\s+developer\b",
    ],
    "backend": [
        r"back[\s-]?end",
        r"\bapi\s+(?:developer|engineer)\b",
        r"\bserver[\s-]?side\b",
        r"\bjava\s+developer\b",
        r"\bpython\s+developer\b",
        r"\bnode(?:\.js)?\s+developer\b",
    ],
    "fullstack": [
        r"full[\s-]?stack",
    ],
    "mobile": [
        r"\bmobile\s+(?:developer|engineer)\b",
        r"\bios\s+(?:developer|engineer)\b",
        r"\bandroid\s+(?:developer|engineer)\b",
        r"react\s+native",
        r"\bflutter\s+(?:developer|engineer)\b",
    ],
    "data-engineering": [
        r"data\s+engineer",
        r"\betl\s+(?:developer|engineer)\b",
        r"data\s+pipeline\s+engineer",
        r"big\s+data\s+engineer",
    ],
    "data-science": [
        r"data\s+scientist",
        r"\bdata\s+science\b",
        r"\bdata\s+analyst\b",
    ],
    "ml-engineering": [
        r"machine\s+learning\s+engineer",
        r"\bml\s+engineer\b",
        r"\bai\s+engineer\b",
        r"deep\s+learning\s+engineer",
        r"nlp\s+engineer",
        r"computer\s+vision\s+engineer",
        r"mlops\s+engineer",
    ],
    "devops-sre": [
        r"\bdevops\b",
        r"site\s+reliability",
        r"\bsre\b",
        r"platform\s+engineer",
        r"infrastructure\s+engineer",
        r"build\s+engineer",
        r"release\s+engineer",
    ],
    "cloud-infra": [
        r"cloud\s+engineer",
        r"cloud\s+architect",
        r"cloud\s+infrastructure",
        r"\baws\s+engineer\b",
        r"\bazure\s+engineer\b",
        r"\bgcp\s+engineer\b",
    ],
    "qa-testing": [
        r"\bqa\s+engineer\b",
        r"quality\s+assurance\s+engineer",
        r"\btest\s+engineer\b",
        r"\bsdet\b",
        r"test\s+automation\s+engineer",
    ],
    "security": [
        r"security\s+engineer",
        r"cybersecurity\s+engineer",
        r"\bappsec\b",
        r"penetration\s+test(?:er|ing)",
        r"\binfosec\b",
        r"security\s+analyst",
    ],
    "embedded": [
        r"embedded\s+(?:systems\s+)?(?:engineer|developer|software)",
        r"firmware\s+engineer",
    ],
    "product-design": [
        r"product\s+designer",
        r"ux\s+designer",
        r"ui/?ux\s+designer",
        r"visual\s+designer",
        r"interaction\s+designer",
    ],
    "technical-writing": [
        r"technical\s+writer",
        r"documentation\s+engineer",
        r"content\s+engineer",
    ],
}

# Reasonable sideways moves for a candidate whose profile targets the key
# family. devops-sre and cloud-infra are deliberately isolated from every
# application-development family — that pairing is exactly the contamination
# this taxonomy exists to prevent.
ADJACENT_FAMILIES: dict[str, list[str]] = {
    "frontend": ["fullstack"],
    "backend": ["fullstack", "data-engineering"],
    "fullstack": ["frontend", "backend"],
    "mobile": ["frontend"],
    "data-engineering": ["backend", "data-science"],
    "data-science": ["ml-engineering", "data-engineering"],
    "ml-engineering": ["data-science"],
    "devops-sre": ["cloud-infra"],
    "cloud-infra": ["devops-sre", "security"],
    "qa-testing": [],
    "security": ["cloud-infra"],
    "embedded": [],
    "product-design": [],
    "technical-writing": [],
}

# Canonical skill -> list of aliases (including the canonical spelling itself
# is not required; lookups are case-insensitive). Covers the stacks most
# commonly seen across the role families above.
SKILL_ALIASES: dict[str, list[str]] = {
    # Languages
    "JavaScript": ["javascript", "js", "es6", "ecmascript"],
    "TypeScript": ["typescript", "ts"],
    "Python": ["python", "python3", "py"],
    "Java": ["java"],
    "C++": ["c++", "cpp", "c plus plus"],
    "C#": ["c#", "csharp", "c sharp"],
    "C": ["c programming", "ansi c"],
    "Go": ["go", "golang"],
    "Rust": ["rust"],
    "Ruby": ["ruby"],
    "PHP": ["php"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "Scala": ["scala"],
    "R": ["r language", "r programming"],
    "SQL": ["sql", "structured query language"],
    "Bash": ["bash", "shell scripting", "shell"],
    "MATLAB": ["matlab"],
    "Dart": ["dart"],
    "Objective-C": ["objective-c", "objective c", "objc"],

    # Frontend
    "React": ["react", "reactjs", "react.js"],
    "Vue.js": ["vue", "vuejs", "vue.js"],
    "Angular": ["angular", "angularjs", "angular.js"],
    "Next.js": ["next.js", "nextjs", "next"],
    "Svelte": ["svelte", "sveltejs"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Sass": ["sass", "scss"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Redux": ["redux", "redux toolkit"],
    "jQuery": ["jquery"],

    # Backend / frameworks
    "Node.js": ["node", "nodejs", "node.js"],
    "Express.js": ["express", "expressjs", "express.js"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring Boot": ["spring boot", "spring", "springboot"],
    "Ruby on Rails": ["rails", "ruby on rails", "ror"],
    ".NET": [".net", "dotnet", "asp.net", "asp.net core"],
    "GraphQL": ["graphql"],
    "REST": ["rest", "restful", "rest api", "restful api"],
    "gRPC": ["grpc"],

    # Cloud / infra / devops
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Docker": ["docker", "containerization"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform", "iac", "infrastructure as code"],
    "Ansible": ["ansible"],
    "Jenkins": ["jenkins"],
    "GitHub Actions": ["github actions"],
    "GitLab CI": ["gitlab ci", "gitlab ci/cd"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous deployment"],
    "Linux": ["linux", "unix"],
    "Nginx": ["nginx"],
    "Prometheus": ["prometheus"],
    "Grafana": ["grafana"],

    # Databases
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    "SQLite": ["sqlite"],
    "DynamoDB": ["dynamodb"],
    "Cassandra": ["cassandra"],

    # Data / ML
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "TensorFlow": ["tensorflow", "tf"],
    "PyTorch": ["pytorch", "torch"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Apache Spark": ["spark", "apache spark", "pyspark"],
    "Kafka": ["kafka", "apache kafka"],
    "Airflow": ["airflow", "apache airflow"],
    "Jupyter": ["jupyter", "jupyter notebook"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],

    # Testing
    "Jest": ["jest"],
    "PyTest": ["pytest", "py.test"],
    "Selenium": ["selenium"],
    "Cypress": ["cypress"],
    "JUnit": ["junit"],
    "Playwright": ["playwright"],

    # Mobile
    "React Native": ["react native", "reactnative"],
    "Flutter": ["flutter"],
    "SwiftUI": ["swiftui"],
    "Jetpack Compose": ["jetpack compose"],

    # Tools / other
    "Git": ["git", "version control"],
    "Figma": ["figma"],
    "Jira": ["jira"],
    "RabbitMQ": ["rabbitmq"],
}

_TITLE_PATTERN_CACHE: dict[str, list[re.Pattern]] = {
    family: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for family, patterns in FAMILY_TITLE_PATTERNS.items()
}


def _build_skill_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in SKILL_ALIASES.items():
        lookup[canonical.lower()] = canonical
        for alias in aliases:
            lookup[alias.lower()] = canonical
    return lookup


_SKILL_LOOKUP = _build_skill_lookup()


def classify_title(title: str) -> str | None:
    """
    Matches a job title against FAMILY_TITLE_PATTERNS, in ROLE_FAMILIES order.
    Returns None (never a guess) when nothing matches confidently.
    """
    if not title:
        return None
    for family in ROLE_FAMILIES:
        for pattern in _TITLE_PATTERN_CACHE[family]:
            if pattern.search(title):
                return family
    return None


def canonicalize_skills(raw: list[str]) -> list[str]:
    """
    Normalizes a list of raw skill strings to their canonical form via
    SKILL_ALIASES. Skills with no known alias pass through trimmed and
    title-cased rather than being dropped. De-duplicates while preserving
    first-seen order.
    """
    seen: set[str] = set()
    result: list[str] = []
    for skill in raw:
        if not skill or not skill.strip():
            continue
        cleaned = skill.strip()
        canonical = _SKILL_LOOKUP.get(cleaned.lower())
        if canonical is None:
            canonical = cleaned if cleaned.isupper() else cleaned.title()
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


# --- Skill extraction from free text -----------------------------------------
#
# ATS boards (Greenhouse, Lever, ...) return the full job description, unlike
# the truncated snippets keyword aggregators give us. That makes it worth
# mining the description for known skills at ingest time so `jobs.skills` is
# populated for filtering and for the job embedding.
#
# Precision matters more than recall here: a wrong skill on a job silently
# corrupts matching for every user, while a missed one only costs a little
# ranking signal. So very short aliases ("js", "ts", "py", "go", "r", "c") are
# deliberately not matched in prose — they collide with ordinary English far
# too often. Their longer aliases ("javascript", "golang") still catch the
# real mentions.

# Aliases that are ordinary words in job-description boilerplate and would fire
# constantly on unrelated text. Deliberately short: every entry here costs real
# recall, so only aliases that genuinely collide with JD prose belong.
# ("spark innovation", "shell company"/"shell script" as a generic noun.)
# The canonical skills stay reachable through their other aliases -
# "apache spark", "bash", "shell scripting".
_AMBIGUOUS_SKILL_ALIASES: set[str] = {
    "shell",
    "spark",
}


def _is_matchable_alias(alias: str) -> bool:
    """
    An alias is safe to match in prose if it is long enough to be unambiguous,
    or short but punctuated (`c++`, `c#`, `.net`) so it can't be a stray word.
    """
    if not alias:
        return False
    if alias in _AMBIGUOUS_SKILL_ALIASES:
        return False
    if not alias.isalnum():
        return True
    return len(alias) >= 3


# Longest-first so "objective-c" wins over "c", "node.js" over "node".
_MATCHABLE_ALIASES = sorted(
    (alias for alias in _SKILL_LOOKUP if _is_matchable_alias(alias)),
    key=len,
    reverse=True,
)

# Custom boundaries rather than \b: \b treats "+" and "#" as word separators, so
# r"\bc\+\+\b" can never match "c++".
#
# The dot needs care in both directions. It must block "node" from matching
# inside "node.js" (that's a different skill), but must NOT block "Docker" in
# "we use Docker." - so a dot only forms a boundary when an alphanumeric is on
# its far side, rather than being excluded outright.
_SKILL_EXTRACTION_RE = (
    re.compile(
        r"(?<![A-Za-z0-9+#])(?<![A-Za-z0-9]\.)(?:"
        + "|".join(re.escape(alias) for alias in _MATCHABLE_ALIASES)
        + r")(?![A-Za-z0-9+#])(?!\.[A-Za-z0-9])",
        re.IGNORECASE,
    )
    if _MATCHABLE_ALIASES
    else None
)


def extract_skills(text: str | None, limit: int = 25) -> list[str]:
    """
    Pulls canonical skill names out of free text (a job description) by matching
    known aliases on word boundaries. Returns at most `limit` skills, ordered by
    first appearance so the most prominent ones survive truncation.

    Never guesses: a token that isn't a known alias is not a skill.
    """
    if not text or _SKILL_EXTRACTION_RE is None:
        return []

    seen: set[str] = set()
    result: list[str] = []
    for match in _SKILL_EXTRACTION_RE.finditer(text):
        canonical = _SKILL_LOOKUP.get(match.group(0).lower())
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
        if len(result) >= limit:
            break
    return result
