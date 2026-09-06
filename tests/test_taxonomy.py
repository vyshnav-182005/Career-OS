import unittest

from backend.services import taxonomy


class ClassifyTitleTests(unittest.TestCase):
    def test_classifies_representative_titles_per_family(self):
        cases = {
            "Senior Frontend Developer": "frontend",
            "Front-End Engineer": "frontend",
            "React Developer": "frontend",
            "Backend Engineer": "backend",
            "Back-End Developer": "backend",
            "Python Developer": "backend",
            "Full Stack Engineer": "fullstack",
            "Fullstack Developer": "fullstack",
            "Mobile Engineer": "mobile",
            "iOS Developer": "mobile",
            "Android Engineer": "mobile",
            "Data Engineer": "data-engineering",
            "ETL Developer": "data-engineering",
            "Data Scientist": "data-science",
            "Machine Learning Engineer": "ml-engineering",
            "NLP Engineer": "ml-engineering",
            "DevOps Engineer": "devops-sre",
            "Site Reliability Engineer": "devops-sre",
            "Platform Engineer": "devops-sre",
            "Cloud Engineer": "cloud-infra",
            "QA Engineer": "qa-testing",
            "SDET": "qa-testing",
            "Security Engineer": "security",
            "Embedded Systems Engineer": "embedded",
            "Product Designer": "product-design",
            "Technical Writer": "technical-writing",
        }
        for title, expected_family in cases.items():
            with self.subTest(title=title):
                self.assertEqual(taxonomy.classify_title(title), expected_family)

    def test_ambiguous_titles_return_none_rather_than_guess(self):
        # "Software Engineer" is deliberately NOT in this list any more. It is
        # unspecialised, not ambiguous - we know it is software work - and
        # leaving it unclassified made ~900 such jobs unreachable for every
        # candidate, because the retrieval gate drops NULL role_family. It now
        # classifies as "software-general"; see the test below.
        for title in ["Consultant", "Analyst", "Manager", "Coordinator", ""]:
            with self.subTest(title=title):
                self.assertIsNone(taxonomy.classify_title(title))

    def test_non_engineering_titles_stay_unclassified(self):
        """The catch-all families must not start swallowing unrelated work."""
        for title in [
            "Line Cook",
            "Sales Development Representative",
            "Corporate Counsel",
            "Account Executive",
            "Product Manager",
            "Recruiter",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(taxonomy.classify_title(title))

    def test_generic_software_titles_use_the_catch_all_family(self):
        for title in [
            "Software Engineer",
            "Software Engineer II",
            "Senior Software Engineer",
            "Software Developer",
            "SDE II",
            "Member of Technical Staff",
        ]:
            with self.subTest(title=title):
                self.assertEqual(taxonomy.classify_title(title), "software-general")

    def test_classifies_titles_across_every_engineering_domain(self):
        """
        Guards the regression that made this taxonomy software-only: a
        cybersecurity or ECE resume matched almost nothing because the titles
        its field advertises under classified as None and were then dropped by
        the role_family gate.
        """
        cases = {
            # security - these are the commonest real postings and none of
            # them matched the original six patterns.
            "Security Researcher": "security",
            "SOC Analyst": "security",
            "Security Operations Engineer": "security",
            "Threat Intelligence Analyst": "security",
            "Malware Analyst": "security",
            "GRC Analyst": "security",
            "Incident Response Engineer": "security",
            # electronics / ECE
            "Electrical Engineer": "hardware-electronics",
            "VLSI Design Engineer": "hardware-electronics",
            "RF Engineer": "hardware-electronics",
            "FPGA Programmer": "hardware-electronics",
            "ASIC Design Engineer": "hardware-electronics",
            "PCB Design Engineer": "hardware-electronics",
            "Hardware Development Intern": "hardware-electronics",
            # embedded stays its own family
            "Firmware Engineer": "embedded",
            "Embedded Systems Intern": "embedded",
            # the rest of engineering
            "Mechanical Engineer": "mechanical",
            "HVAC Engineer": "mechanical",
            "Civil Engineer": "civil-structural",
            "Structural Engineer": "civil-structural",
            "Chemical Engineer": "chemical-materials",
            "Materials Engineer": "chemical-materials",
            "Biomedical Engineer": "biomedical",
            "Aerospace Engineer": "aerospace",
            "Avionics Engineer": "aerospace",
            "Robotics Engineer": "robotics-controls",
            "Control Systems Engineer": "robotics-controls",
        }
        for title, expected_family in cases.items():
            with self.subTest(title=title):
                self.assertEqual(taxonomy.classify_title(title), expected_family)

    def test_domain_wins_over_the_generic_test_engineer_pattern(self):
        """
        ROLE_FAMILIES order is load-bearing: qa-testing's bare "test engineer"
        pattern must not claim hardware or flight test roles, which is what it
        did before the hardware families were moved ahead of it.
        """
        self.assertEqual(taxonomy.classify_title("RF Test Engineer"), "hardware-electronics")
        self.assertEqual(taxonomy.classify_title("Flight Test Engineer"), "aerospace")
        self.assertEqual(taxonomy.classify_title("Software Test Engineer"), "qa-testing")
        self.assertEqual(taxonomy.classify_title("QA Engineer"), "qa-testing")

    def test_specialism_wins_over_the_software_catch_all(self):
        self.assertEqual(taxonomy.classify_title("Embedded Software Engineer"), "embedded")
        self.assertEqual(taxonomy.classify_title("Security Software Engineer"), "security")
        self.assertEqual(taxonomy.classify_title("Robotics Software Engineer"), "robotics-controls")

    def test_security_family_excludes_the_non_cyber_senses_of_the_word(self):
        """
        "security" on its own is also guards, physical site security and social
        security casework. Matching the bare word put all of those in a
        cybersecurity candidate's results, so the family requires a technical
        head noun and rejects those qualifiers.
        """
        for title in [
            "Security Guard",
            "Security Officer",
            "Physical Security Specialist",
            "Lead Physical Security Engineer",
            "Campus Security",
            "Food Security Analyst",
            "Social Security Caseworker",
        ]:
            with self.subTest(title=title):
                self.assertNotEqual(taxonomy.classify_title(title), "security")

    def test_security_family_still_covers_real_cyber_titles(self):
        for title in [
            "Security Engineer",
            "Security Researcher",
            "Security Operations Engineer",
            "Application Security Engineer",
            "Information Security Analyst",
            "Network Security Engineer",
            "Product Security Engineer",
            "Offensive Security Engineer",
            "Security Compliance Specialist",
            "Cloud Security Engineer",
            "Penetration Tester",
            "SOC Analyst",
        ]:
            with self.subTest(title=title):
                self.assertEqual(taxonomy.classify_title(title), "security")

    def test_semiconductor_process_engineer_is_hardware_not_chemical(self):
        """Both families claim "process engineer"; hardware is checked first."""
        self.assertEqual(
            taxonomy.classify_title("Semiconductor Process Engineer"), "hardware-electronics"
        )
        self.assertEqual(taxonomy.classify_title("Chemical Process Engineer"), "chemical-materials")

    def test_classify_title_is_case_insensitive(self):
        self.assertEqual(taxonomy.classify_title("devops engineer"), "devops-sre")
        self.assertEqual(taxonomy.classify_title("DEVOPS ENGINEER"), "devops-sre")


class CanonicalizeSkillsTests(unittest.TestCase):
    def test_collapses_known_aliases_to_canonical_form(self):
        result = taxonomy.canonicalize_skills(["ReactJS", "React.js", "react", "javascript"])
        self.assertEqual(result, ["React", "JavaScript"])

    def test_deduplicates_preserving_first_seen_order(self):
        result = taxonomy.canonicalize_skills(["Python", "python3", "Go", "python"])
        self.assertEqual(result, ["Python", "Go"])

    def test_unknown_skill_passes_through_title_cased(self):
        result = taxonomy.canonicalize_skills(["some obscure tool"])
        self.assertEqual(result, ["Some Obscure Tool"])

    def test_blank_entries_are_dropped(self):
        result = taxonomy.canonicalize_skills(["Python", "  ", ""])
        self.assertEqual(result, ["Python"])


class AdjacentFamiliesTests(unittest.TestCase):
    _APPLICATION_DEV_FAMILIES = {"frontend", "backend", "fullstack", "mobile"}

    def test_devops_sre_has_no_application_dev_family_as_neighbor(self):
        neighbors = set(taxonomy.ADJACENT_FAMILIES.get("devops-sre", []))
        self.assertFalse(neighbors & self._APPLICATION_DEV_FAMILIES)

    def test_no_application_dev_family_lists_devops_sre_as_a_neighbor(self):
        for family in self._APPLICATION_DEV_FAMILIES:
            with self.subTest(family=family):
                self.assertNotIn("devops-sre", taxonomy.ADJACENT_FAMILIES.get(family, []))

    def test_every_family_has_an_adjacency_entry(self):
        for family in taxonomy.ROLE_FAMILIES:
            with self.subTest(family=family):
                self.assertIn(family, taxonomy.ADJACENT_FAMILIES)

    def test_adjacency_only_references_real_families(self):
        for family, neighbors in taxonomy.ADJACENT_FAMILIES.items():
            with self.subTest(family=family):
                self.assertIn(family, taxonomy.ROLE_FAMILIES)
                for neighbor in neighbors:
                    self.assertIn(neighbor, taxonomy.ROLE_FAMILIES)

    def test_embedded_reaches_the_hardware_families(self):
        """
        The ECE case: a resume that reads as "embedded" must still be able to
        surface RF/VLSI/hardware work, which is where most ECE postings live.
        """
        neighbors = set(taxonomy.ADJACENT_FAMILIES["embedded"])
        self.assertIn("hardware-electronics", neighbors)
        self.assertIn("hardware-electronics", taxonomy.ADJACENT_FAMILIES["embedded"])
        self.assertIn("embedded", taxonomy.ADJACENT_FAMILIES["hardware-electronics"])


class TaxonomyCoverageTests(unittest.TestCase):
    def test_every_family_has_title_patterns(self):
        for family in taxonomy.ROLE_FAMILIES:
            with self.subTest(family=family):
                self.assertTrue(taxonomy.FAMILY_TITLE_PATTERNS.get(family))

    def test_no_orphan_pattern_families(self):
        for family in taxonomy.FAMILY_TITLE_PATTERNS:
            with self.subTest(family=family):
                self.assertIn(family, taxonomy.ROLE_FAMILIES)

    def test_software_general_is_checked_last(self):
        """It is a catch-all; any specialised family must get first refusal."""
        self.assertEqual(taxonomy.ROLE_FAMILIES[-1], "software-general")

    def test_every_family_has_seed_queries(self):
        for family in taxonomy.ROLE_FAMILIES:
            with self.subTest(family=family):
                self.assertTrue(taxonomy.DOMAIN_SEED_QUERIES.get(family))

    def test_seed_queries_classify_back_to_their_own_family(self):
        """
        A seed query that classifies elsewhere would stock the wrong family.
        Only checked where the query is a job title we expect to recognise.
        """
        for family, queries in taxonomy.DOMAIN_SEED_QUERIES.items():
            for query in queries:
                classified = taxonomy.classify_title(query)
                if classified is None:
                    continue
                with self.subTest(family=family, query=query):
                    self.assertIn(
                        classified,
                        {family, *taxonomy.ADJACENT_FAMILIES.get(family, [])},
                        f"seed query {query!r} for {family} classifies as {classified}",
                    )

    def test_all_seed_queries_are_deduplicated(self):
        queries = taxonomy.all_seed_queries()
        lowered = [q.lower() for q in queries]
        self.assertEqual(len(lowered), len(set(lowered)))


class DomainSkillExtractionTests(unittest.TestCase):
    """
    The vocabulary was software-only, so a security or hardware job mined zero
    skills - which zeroed skill_overlap (a fifth of the match score) and left
    the lexical retrieval arm with nothing to query on.
    """

    def test_extracts_security_tooling(self):
        found = taxonomy.extract_skills(
            "Penetration testing with Burp Suite and Metasploit, triage alerts in "
            "Splunk SIEM, and map findings to OWASP Top 10 and MITRE ATT&CK."
        )
        for expected in ["Burp Suite", "Metasploit", "Splunk", "SIEM", "OWASP"]:
            with self.subTest(skill=expected):
                self.assertIn(expected, found)

    def test_extracts_electronics_tooling(self):
        found = taxonomy.extract_skills(
            "Design RTL in Verilog and SystemVerilog, simulate in Cadence, lay out "
            "PCBs in Altium, and debug over JTAG on an STM32."
        )
        for expected in ["Verilog", "SystemVerilog", "Cadence", "Altium Designer", "JTAG", "STM32"]:
            with self.subTest(skill=expected):
                self.assertIn(expected, found)

    def test_extracts_mechanical_and_civil_tooling(self):
        mech = taxonomy.extract_skills(
            "Model assemblies in SolidWorks and CATIA, run FEA in ANSYS, apply GD&T."
        )
        for expected in ["SolidWorks", "CATIA", "ANSYS", "GD&T"]:
            with self.subTest(skill=expected):
                self.assertIn(expected, mech)

        civil = taxonomy.extract_skills("Structural analysis in STAAD Pro and ETABS, detailing in Revit.")
        for expected in ["STAAD Pro", "ETABS", "Revit"]:
            with self.subTest(skill=expected):
                self.assertIn(expected, civil)

    def test_domain_skills_canonicalize_from_resume_spellings(self):
        """Resume text arrives title-cased from the parser, not lowercase."""
        self.assertEqual(
            taxonomy.canonicalize_skills(["Ltspice", "Keil Uvision", "Ansys Hfss"]),
            ["LTspice", "Keil uVision", "ANSYS HFSS"],
        )

    def test_still_extracts_software_skills(self):
        found = taxonomy.extract_skills(
            "Build REST APIs in Python with FastAPI on PostgreSQL, deployed with Docker."
        )
        for expected in ["Python", "FastAPI", "PostgreSQL", "Docker"]:
            with self.subTest(skill=expected):
                self.assertIn(expected, found)


if __name__ == "__main__":
    unittest.main()
