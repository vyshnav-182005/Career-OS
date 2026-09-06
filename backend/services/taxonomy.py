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
# Order is load-bearing: classify_title walks this list and takes the first
# family whose pattern matches, so specific families must precede general ones.
# Two consequences worth knowing before reordering:
#   - the hardware/physical-engineering families sit ahead of "qa-testing" so
#     "RF Test Engineer" and "Flight Test Engineer" classify by their domain
#     rather than being captured by qa-testing's generic "test engineer".
#   - "software-general" is deliberately last. It is the catch-all for titles
#     that are plainly software but name no specialism ("Software Engineer",
#     "SDE II"), which every more specific family gets to claim first.
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
    "security",
    "embedded",
    "hardware-electronics",
    "robotics-controls",
    "aerospace",
    "mechanical",
    "civil-structural",
    "chemical-materials",
    "biomedical",
    "qa-testing",
    "product-design",
    "technical-writing",
    "software-general",
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
    "hardware-electronics": [
        r"\belectrical\s+engineer",
        r"\belectronics?\s+engineer",
        r"\bhardware\s+(?:engineer|design|development|developer)",
        r"\bvlsi\b",
        r"\basic\b",
        r"\bfpga\b",
        r"\brtl\s+(?:design|engineer)",
        r"\brf\b",
        r"radio\s+frequency",
        r"analog\s+(?:design|engineer|ic)",
        r"mixed[\s-]?signal",
        r"\bsemiconductor\b",
        r"\bsilicon\b",
        r"\bpcb\b",
        r"signal\s+integrity",
        r"power\s+electronics",
        r"circuit\s+design",
        r"chip\s+design",
        r"\bphotonic",
        r"\bantenna\b",
        r"\bvalidation\s+engineer\b",
        r"\bcharacterization\s+engineer\b",
        r"\btelecom(?:munications)?\s+engineer",
    ],
    "robotics-controls": [
        r"\brobotic",
        r"controls?\s+engineer",
        r"control\s+systems?\b",
        # Industrial automation, not "Test/QA Automation Engineer" - those are
        # QA, and this family is checked first, so it excludes them here.
        # Separate lookbehinds because Python requires each to be fixed-width.
        r"(?<!test\s)(?<!qa\s)\bautomation\s+engineer",
        r"\bplc\b",
        r"motion\s+control",
        r"\bmechatronic",
        r"\bautonomy\b",
        r"guidance.{0,12}navigation",
    ],
    "aerospace": [
        r"\baerospace\b",
        r"\bavionics?\b",
        r"\bpropulsion\b",
        r"\bspacecraft\b",
        r"\bsatellite\b",
        r"flight\s+(?:test|control|dynamics)",
        r"\baerodynamic",
    ],
    "mechanical": [
        r"\bmechanical\s+engineer",
        r"\bthermal\s+engineer",
        r"\bhvac\b",
        r"manufacturing\s+engineer",
        r"\bcad\s+engineer\b",
        r"\btooling\s+engineer\b",
        r"\bfluid\s+(?:dynamics|engineer)",
        r"stress\s+analysis",
        r"\bsolidworks\b",
        r"\bautomotive\s+engineer",
        r"\bvehicle\s+engineer",
    ],
    "civil-structural": [
        r"\bcivil\s+engineer",
        r"\bstructural\s+engineer",
        r"\bgeotechnical\b",
        r"transportation\s+engineer",
        r"construction\s+engineer",
        r"\bsurveying\b",
        r"environmental\s+engineer",
    ],
    "chemical-materials": [
        r"\bchemical\s+engineer",
        r"\bmaterials?\s+engineer",
        r"\bmetallurg",
        r"\bpolymer\b",
        # "process engineer" is genuinely ambiguous - a semiconductor process
        # engineer is hardware. hardware-electronics is checked first, so this
        # only catches the ones no hardware pattern claimed.
        r"\bprocess\s+engineer",
    ],
    "biomedical": [
        r"\bbiomedical\b",
        r"\bbioengineer",
        r"\bbioprocess\b",
        r"medical\s+device",
        r"\bclinical\s+engineer",
    ],
    "qa-testing": [
        r"\bqa\s+engineer\b",
        r"quality\s+assurance\s+engineer",
        # Still generic, but this family now sits after the hardware/aerospace
        # families in ROLE_FAMILIES, so "RF Test Engineer" and "Flight Test
        # Engineer" are claimed by their own domain before reaching here.
        r"\btest\s+engineer\b",
        r"\bsdet\b",
        r"test\s+automation\s+engineer",
        r"\bqa\s+automation\b",
        r"\bsoftware\s+test\b",
    ],
    "security": [
        # Broad on purpose: "security"/"cyber" in an engineering title is a
        # reliable signal, and the previous narrow list matched none of the
        # commonest postings ("Security Researcher", "SOC Analyst") - which is
        # why only 115 of the 311 real security jobs were reachable at all.
        r"\bcyber\s*security\b",
        r"\bcyber\b",
        r"\binformation\s+security\b",
        r"\bnetwork\s+security\b",
        r"\bapplication\s+security\b",
        r"\bcloud\s+security\b",
        r"\bproduct\s+security\b",
        r"\boffensive\s+security\b",
        r"\bappsec\b",
        r"\binfosec\b",
        # "security" alone is not enough - it is also guards, physical site
        # security and social security casework, none of which belong in a
        # cybersecurity candidate's results. Require a technical head noun,
        # and exclude the qualifiers that mark the non-cyber senses.
        # Each lookbehind is separate because Python needs them fixed-width.
        r"(?<!physical\s)(?<!social\s)(?<!food\s)security\s+"
        r"(?:engineer|engineering|analyst|architect|research(?:er)?|operations|"
        r"developer|administrator|specialist|consultant|compliance|software)",
        r"penetration\s+test(?:er|ing)",
        r"\bpen\s*test(?:er|ing)\b",
        r"\bred\s+team",
        r"\bblue\s+team",
        r"\bsoc\s+analyst\b",
        r"threat\s+(?:intelligence|research|detection|hunting|response|analyst)",
        r"\bmalware\b",
        r"vulnerabilit(?:y|ies)",
        r"incident\s+response",
        r"\bgrc\b",
        r"cryptograph(?:y|er|ic)",
        r"digital\s+forensic",
        r"exploit\s+develop",
    ],
    "embedded": [
        r"\bembedded\b",
        r"\bfirmware\b",
        r"device\s+driver",
        r"bare[\s-]?metal",
        r"\bmicrocontroller\b",
        r"\brtos\b",
        r"board\s+bring[\s-]?up",
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
    "software-general": [
        # Deliberately last: a title that names any specialism is claimed by
        # that family above. This exists because ~900 plainly-software jobs
        # ("Software Engineer", "Software Engineer II", "SDE") matched nothing
        # at all and so were invisible to every candidate.
        r"software\s+(?:engineer|developer|dev\b)",
        r"software\s+development\s+engineer",
        r"\bsde\s*(?:i{1,3}|[123])?\b",
        r"\bswe\b",
        r"\bprogrammer\b",
        r"member\s+of\s+technical\s+staff",
        r"\bsoftware\s+architect\b",
    ],
}

# Reasonable sideways moves for a candidate whose profile targets the key
# family. devops-sre and cloud-infra are deliberately isolated from every
# application-development family — that pairing is exactly the contamination
# this taxonomy exists to prevent.
ADJACENT_FAMILIES: dict[str, list[str]] = {
    # Software. Every software family lists "software-general" so that the
    # unspecialised "Software Engineer" postings score 0.6 (adjacent) for any
    # software candidate rather than being unreachable - and, going the other
    # way, a candidate whose resume reads as generic software still reaches the
    # specialised roles.
    "frontend": ["fullstack", "software-general"],
    "backend": ["fullstack", "data-engineering", "software-general"],
    "fullstack": ["frontend", "backend", "software-general"],
    "mobile": ["frontend", "software-general"],
    "data-engineering": ["backend", "data-science", "software-general"],
    "data-science": ["ml-engineering", "data-engineering"],
    "ml-engineering": ["data-science", "software-general"],
    "devops-sre": ["cloud-infra"],
    "cloud-infra": ["devops-sre", "security"],
    "qa-testing": ["software-general"],
    "security": ["cloud-infra"],
    "software-general": ["frontend", "backend", "fullstack", "mobile", "ml-engineering"],

    # Physical / hardware engineering. Embedded is the hinge between software
    # and hardware, so it reaches both directions; an ECE candidate targeting
    # "embedded" should still see RF, VLSI and hardware-validation work, which
    # is exactly what was missing.
    "embedded": ["hardware-electronics", "robotics-controls", "software-general"],
    "hardware-electronics": ["embedded", "robotics-controls", "aerospace"],
    "robotics-controls": ["embedded", "hardware-electronics", "mechanical"],
    "aerospace": ["hardware-electronics", "mechanical", "robotics-controls"],
    "mechanical": ["robotics-controls", "aerospace", "civil-structural"],
    "civil-structural": ["mechanical"],
    "chemical-materials": ["biomedical", "mechanical"],
    "biomedical": ["chemical-materials"],

    "product-design": [],
    "technical-writing": [],
}

# Standing ingestion queries, one small set per family.
#
# Ingestion is otherwise demand-driven: the scheduler only fetches the roles
# that existing profiles already asked for. That works once a domain has users
# and fails completely before it does - the first mechanical or civil candidate
# to sign up searches a table that contains almost nothing for them, and the
# background fetch that would fix it only runs *after* their empty page has
# already rendered. These queries give every family a floor of inventory
# regardless of who has signed up.
#
# Kept to 2-3 per family on purpose: each one is a live provider request per
# scheduled run, and the ATS providers cache their fan-out per vendor, so the
# real cost is the aggregator calls.
DOMAIN_SEED_QUERIES: dict[str, list[str]] = {
    "frontend": ["Frontend Engineer", "React Developer"],
    "backend": ["Backend Engineer", "API Engineer"],
    "fullstack": ["Full Stack Developer"],
    "mobile": ["Mobile Engineer", "Android Developer", "iOS Engineer"],
    "data-engineering": ["Data Engineer", "ETL Developer"],
    "data-science": ["Data Scientist", "Data Analyst"],
    "ml-engineering": ["Machine Learning Engineer", "AI Engineer"],
    "devops-sre": ["DevOps Engineer", "Site Reliability Engineer"],
    "cloud-infra": ["Cloud Engineer", "Cloud Architect"],
    "security": ["Security Engineer", "Penetration Tester", "SOC Analyst"],
    "embedded": ["Embedded Systems Engineer", "Firmware Engineer"],
    "hardware-electronics": ["Electronics Engineer", "VLSI Design Engineer", "RF Engineer"],
    "robotics-controls": ["Robotics Engineer", "Control Systems Engineer"],
    "aerospace": ["Aerospace Engineer", "Avionics Engineer"],
    "mechanical": ["Mechanical Engineer", "Design Engineer", "Manufacturing Engineer"],
    "civil-structural": ["Civil Engineer", "Structural Engineer"],
    "chemical-materials": ["Chemical Engineer", "Process Engineer"],
    "biomedical": ["Biomedical Engineer", "Medical Device Engineer"],
    "qa-testing": ["QA Engineer", "Test Automation Engineer"],
    "product-design": ["Product Designer", "UX Designer"],
    "technical-writing": ["Technical Writer"],
    "software-general": ["Software Engineer", "Software Developer"],
}


def all_seed_queries() -> list[str]:
    """Every DOMAIN_SEED_QUERIES entry, de-duplicated, in family order."""
    seen: set[str] = set()
    out: list[str] = []
    for queries in DOMAIN_SEED_QUERIES.values():
        for query in queries:
            key = query.lower()
            if key not in seen:
                seen.add(key)
                out.append(query)
    return out

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

    # --- Security -----------------------------------------------------------
    # Everything below this line exists because the vocabulary was software-only:
    # a security or hardware job description mined 0 skills, which zeroed the
    # skill_overlap feature (a fifth of the match score) and left the lexical
    # retrieval arm with nothing to query on.
    "Burp Suite": ["burp suite", "burpsuite", "burp"],
    "Metasploit": ["metasploit", "msfconsole"],
    "Wireshark": ["wireshark"],
    "Nmap": ["nmap"],
    "Nessus": ["nessus"],
    "Ghidra": ["ghidra"],
    "IDA Pro": ["ida pro"],
    "Kali Linux": ["kali linux", "kali"],
    "SIEM": ["siem", "security information and event management"],
    "Splunk": ["splunk"],
    "EDR": ["edr", "endpoint detection and response"],
    "OWASP": ["owasp", "owasp top 10"],
    "MITRE ATT&CK": ["mitre att&ck", "mitre attack", "att&ck"],
    "Penetration Testing": ["penetration testing", "pentesting", "pen testing", "ethical hacking"],
    "Red Teaming": ["red teaming", "red team"],
    "Threat Modeling": ["threat modeling", "threat modelling"],
    "Vulnerability Assessment": ["vulnerability assessment", "vulnerability management"],
    "Incident Response": ["incident response"],
    "Digital Forensics": ["digital forensics", "forensics"],
    "Reverse Engineering": ["reverse engineering"],
    "Malware Analysis": ["malware analysis"],
    "Cryptography": ["cryptography", "cryptographic"],
    "YARA": ["yara"],
    "SAST": ["sast", "static application security testing"],
    "DAST": ["dast", "dynamic application security testing"],
    "ISO 27001": ["iso 27001", "iso27001"],
    "SOC 2": ["soc 2", "soc2"],
    "NIST": ["nist", "nist csf"],
    "x86 Assembly": ["x86 assembly", "assembly language"],

    # --- Electronics / ECE / hardware ---------------------------------------
    "Verilog": ["verilog"],
    "VHDL": ["vhdl"],
    "SystemVerilog": ["systemverilog", "system verilog"],
    "UVM": ["uvm", "universal verification methodology"],
    "RTL Design": ["rtl design", "rtl coding"],
    "FPGA": ["fpga"],
    "ASIC": ["asic"],
    "VLSI": ["vlsi"],
    "Cadence": ["cadence", "cadence virtuoso", "virtuoso"],
    "Synopsys": ["synopsys", "design compiler"],
    "Xilinx Vivado": ["vivado", "xilinx vivado", "xilinx"],
    "Altium Designer": ["altium", "altium designer"],
    "LTspice": ["ltspice", "lt spice"],
    "SPICE": ["spice simulation", "pspice", "hspice"],
    "ANSYS HFSS": ["ansys hfss", "hfss"],
    "Keil uVision": ["keil", "keil uvision", "uvision"],
    "PCB Design": ["pcb design", "pcb layout", "printed circuit board"],
    "Embedded C": ["embedded c"],
    "ARM Cortex": ["arm cortex", "cortex-m", "arm architecture"],
    "STM32": ["stm32"],
    "Arduino": ["arduino"],
    "Raspberry Pi": ["raspberry pi"],
    "I2C": ["i2c"],
    "SPI": ["spi protocol"],
    "UART": ["uart"],
    "CAN Bus": ["can bus", "canbus", "controller area network"],
    "JTAG": ["jtag"],
    "Oscilloscope": ["oscilloscope"],
    "Signal Processing": ["signal processing", "dsp", "digital signal processing"],
    "RTOS": ["rtos", "freertos", "real-time operating system"],
    "LabVIEW": ["labview"],
    "Simulink": ["simulink"],
    "5G": ["5g", "lte", "wireless communication"],

    # --- Mechanical / manufacturing -----------------------------------------
    "SolidWorks": ["solidworks", "solid works"],
    "AutoCAD": ["autocad", "auto cad"],
    "CATIA": ["catia"],
    "ANSYS": ["ansys"],
    "Abaqus": ["abaqus"],
    "Creo": ["creo", "ptc creo"],
    "Fusion 360": ["fusion 360"],
    "GD&T": ["gd&t", "geometric dimensioning and tolerancing"],
    "Finite Element Analysis": ["finite element analysis", "fea"],
    "CFD": ["cfd", "computational fluid dynamics"],
    "Thermodynamics": ["thermodynamics"],
    "CNC Machining": ["cnc", "cnc machining"],

    # --- Civil / structural --------------------------------------------------
    "STAAD Pro": ["staad", "staad pro"],
    "ETABS": ["etabs"],
    "Revit": ["revit"],
    "SAP2000": ["sap2000"],
    "Primavera": ["primavera", "primavera p6"],
    "Structural Analysis": ["structural analysis"],

    # --- Chemical / materials / biomedical ----------------------------------
    "Aspen Plus": ["aspen plus", "aspen hysys", "hysys"],
    "HPLC": ["hplc"],
    "GC-MS": ["gc-ms", "gas chromatography"],
    "Process Simulation": ["process simulation"],
    "Materials Characterization": ["materials characterization", "sem analysis"],

    # --- Robotics / controls / aerospace ------------------------------------
    "ROS": ["ros", "ros2", "robot operating system"],
    "PLC Programming": ["plc", "plc programming", "ladder logic"],
    "SCADA": ["scada"],
    "Control Systems": ["control systems", "control theory"],
    "Kinematics": ["kinematics", "inverse kinematics"],
    "DO-178C": ["do-178c", "do178c"],
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
