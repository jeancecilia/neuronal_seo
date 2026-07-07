"""
Topic and entity extractor for crawled pages.
Extracts services, cities, technologies, problems, pricing terms,
FAQs, CTA patterns, trust signals, and schema types from page content.
"""

import re
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse


class EntityExtractor:
    """
    Extracts structured topics and entities from web page content.
    Used to build competitor topic maps and detect missing topics.
    """

    # German/English entity patterns
    ENTITY_PATTERNS = {
        "services": {
            "patterns": [
                r"(?i)(?:app\s*entwicklung|webentwicklung|softwareentwicklung)",
                r"(?i)(?:flutter|react\s*native|ios|android)\s*(?:entwicklung|app)",
                r"(?i)(?:wordpress|shopify|magento)\s*(?:entwicklung|plugin|theme)",
                r"(?i)(?:seo|suchmaschinenoptimierung|online\s*marketing)",
                r"(?i)(?:ki|ai|künstliche\s*intelligenz|machine\s*learning|automatisierung)",
                r"(?i)(?:mvp|prototyp|minimum\s*viable\s*product)",
                r"(?i)(?:beratung|consulting|strategie|coaching)",
                r"(?i)(?:ux|ui|user\s*experience|design|webdesign)",
                r"(?i)(?:cloud|devops|hosting|server|infrastruktur)",
                r"(?i)(?:api|integration|schnittstelle|backend)",
            ],
        },
        "technologies": {
            "patterns": [
                r"\b(?:flutter|react|angular|vue|svelte)\b",
                r"\b(?:python|javascript|typescript|java|php|ruby|go|rust|swift|kotlin|dart)\b",
                r"\b(?:node\.?js|django|flask|fastapi|laravel|spring)\b",
                r"\b(?:aws|azure|gcp|google\s*cloud|firebase|heroku)\b",
                r"\b(?:docker|kubernetes|terraform|ansible)\b",
                r"\b(?:postgresql|mysql|mongodb|redis|elasticsearch)\b",
                r"\b(?:wordpress|shopify|magento|woocommerce|prestashop)\b",
                r"\b(?:figma|sketch|adobe|photoshop|illustrator)\b",
            ],
        },
        "pricing_terms": {
            "patterns": [
                r"(?i)(?:ab\s*\d+[\.,]?\d*\s*€)",
                r"(?i)(?:preis(?:e)?\s*(?:ab|von)?\s*\d+)",
                r"(?i)(?:stundensatz\s*\d+)",
                r"(?i)(?:festpreis|pauschalpreis|projektpreis)",
                r"(?i)(?:kostenlos|gratis|free|kostenfrei)",
                r"(?i)(?:angebot|kostenvoranschlag|quote)",
                r"(?i)(?:monatlich|jährlich|monthly|yearly)",
            ],
        },
        "trust_signals": {
            "patterns": [
                r"(?i)(?:zertifiziert|certified|iso|din)",
                r"(?i)(?:auszeichnung|award|preis|gewinner)",
                r"(?i)(?:referenz|kundenstimme|testimonial|bewertung|review)",
                r"(?i)(?:partner\s*(?:von|of)\s*\w+)",
                r"(?i)(?:vertrauen|trusted|sicher|secure)",
                r"(?i)(?:datenschutz|dsgvo|gdpr)",
                r"(?i)(?:jahre\s*erfahrung|years\s*experience)",
                r"(?i)(?:über\s*\d+\s*(?:kunden|projekte|clients))",
            ],
        },
        "cta_patterns": {
            "patterns": [
                r"(?i)(?:jetzt\s*(?:anfragen|kontaktieren|beraten|starten|buchen))",
                r"(?i)(?:kostenlose?\s*(?:beratung|erstgespräch|analyse|demo))",
                r"(?i)(?:termin\s*(?:vereinbaren|buchen))",
                r"(?i)(?:kontaktieren\s*sie\s*uns)",
                r"(?i)(?:rufen\s*sie\s*uns\s*an)",
                r"(?i)(?:get\s*(?:started|a\s*quote|in\s*touch))",
                r"(?i)(?:free\s*(?:consultation|quote|demo|trial))",
                r"(?i)(?:contact\s*us|request\s*(?:a\s*)?(?:demo|quote|callback))",
            ],
        },
        "local_references": {
            "patterns": [
                r"\b(?:köln|cologne|bonn|düsseldorf|duesseldorf|berlin|hamburg|münchen|munich|frankfurt|stuttgart|leipzig|dresden|nürnberg|nuernberg|hannover|bremen|essen|dortmund)\b",
                r"(?i)(?:vor\s*ort|lokal|local|in\s*der\s*nähe|in\s*your\s*area)",
                r"(?i)(?:region|umgebung|umkreis|einzugsgebiet)",
                r"(?i)(?:stadt|city|gemeinde|bezirk)",
            ],
        },
        "problem_terms": {
            "patterns": [
                r"(?i)(?:problem|herausforderung|challenge|schwierigkeit)",
                r"(?i)(?:lösung|solution|ansatz|ansatzweise)",
                r"(?i)(?:optimierung|verbesserung|optimization|improvement)",
                r"(?i)(?:fehler|bug|issue|problem)",
                r"(?i)(?:reparieren|fix|beheben|korrigieren)",
                r"(?i)(?:automatisieren|vereinfachen|beschleunigen)",
            ],
        },
    }

    def extract(self, content: str, title: str = "",
                headings: List[str] = None, url: str = "") -> Dict:
        """Extract all entities from page content."""
        headings = headings or []
        full_text = f"{title} {' '.join(headings[:10])} {content or ''}"
        full_text_lower = full_text.lower()

        result = {
            "services": [],
            "technologies": [],
            "pricing_terms": [],
            "trust_signals": [],
            "cta_patterns": [],
            "local_references": [],
            "problem_terms": [],
            "faqs": [],
            "schema_types": [],
            "cities": [],
            "word_count": len(content.split()) if content else 0,
        }

        # Extract pattern-based entities
        for category, config in self.ENTITY_PATTERNS.items():
            found = set()
            for pattern in config["patterns"]:
                matches = re.findall(pattern, full_text, re.IGNORECASE)
                found.update(m.lower().strip() for m in matches if m)
            result[category] = list(found)[:20]

        # Extract FAQs from headings
        result["faqs"] = self._extract_faqs(headings, content)

        # Extract cities
        result["cities"] = self._extract_cities(full_text)

        # Detect schema types from content signals
        result["schema_types"] = self._detect_schema_types(full_text_lower, result)

        return result

    def _extract_faqs(self, headings: List[str], content: str) -> List[Dict]:
        """Extract FAQ patterns from headings."""
        faqs = []
        question_pattern = re.compile(
            r"^(?i)(?:was|wie|warum|welche|wann|wo|wer|ist|kann|hat|"
            r"does|how|why|what|when|where|who|can|is|are|do)\s"
        )

        for i, heading in enumerate(headings):
            if question_pattern.match(heading.strip()):
                # Try to find the answer in the next paragraph
                answer = ""
                if content and heading in content:
                    idx = content.find(heading)
                    if idx >= 0:
                        answer_section = content[idx + len(heading):idx + len(heading) + 500]
                        answer = answer_section.strip()[:300]
                faqs.append({
                    "question": heading.strip(),
                    "answer_preview": answer,
                })

        return faqs[:15]

    def _extract_cities(self, text: str) -> List[str]:
        """Extract city references."""
        cities_pattern = re.compile(
            r"\b(köln|cologne|bonn|düsseldorf|duesseldorf|berlin|hamburg|"
            r"münchen|munich|frankfurt|stuttgart|leipzig|dresden|"
            r"nürnberg|nuernberg|hannover|bremen|essen|dortmund)\b",
            re.IGNORECASE
        )
        return list(set(m.lower() for m in cities_pattern.findall(text)))

    def _detect_schema_types(self, text: str, entities: Dict) -> List[str]:
        """Detect which schema.org types are likely relevant."""
        schema_types = []

        if entities.get("services"):
            schema_types.append("Service")
        if entities.get("local_references") or entities.get("cities"):
            schema_types.append("LocalBusiness")
        if entities.get("faqs"):
            schema_types.append("FAQPage")
        if entities.get("pricing_terms"):
            schema_types.append("Offer")
        if entities.get("trust_signals"):
            schema_types.append("Organization")
        if entities.get("cta_patterns"):
            schema_types.append("Action")

        # Content-based signals
        if re.search(r"(?i)(?:product|produkt|shop|price)", text):
            schema_types.append("Product")
        if re.search(r"(?i)(?:article|blog|beitrag|artikel)", text):
            schema_types.append("Article")
        if re.search(r"(?i)(?:review|bewertung|rezension|rating)", text):
            schema_types.append("Review")
        if re.search(r"(?i)(?:event|veranstaltung|event|webinar)", text):
            schema_types.append("Event")

        return list(set(schema_types))

    def compare_entities(self, own_entities: Dict,
                         competitor_entities: List[Dict]) -> Dict:
        """Compare your page entities against competitors to find gaps."""
        if not competitor_entities:
            return {"missing": [], "weak": [], "matching": []}

        gaps = {
            "missing_services": [],
            "missing_technologies": [],
            "missing_trust_signals": [],
            "missing_cta_patterns": [],
            "missing_cities": [],
            "missing_faq_topics": [],
            "missing_schema_types": [],
        }

        for category in ["services", "technologies", "trust_signals",
                         "cta_patterns", "local_references"]:
            own_set = set(own_entities.get(category, []))
            comp_set = set()
            for comp in competitor_entities[:3]:
                comp_set.update(comp.get(category, []))

            missing = comp_set - own_set
            gap_key = f"missing_{category}"
            if gap_key in gaps:
                gaps[gap_key] = list(missing)[:10]

        # Schema gaps
        own_schema = set(own_entities.get("schema_types", []))
        comp_schema = set()
        for comp in competitor_entities[:3]:
            comp_schema.update(comp.get("schema_types", []))
        gaps["missing_schema_types"] = list(comp_schema - own_schema)

        return gaps

    def build_topic_map(self, pages: List[Dict]) -> Dict:
        """Build a topic map from a list of extracted page entities."""
        topic_map = {
            "total_pages": len(pages),
            "all_services": set(),
            "all_technologies": set(),
            "all_cities": set(),
            "faq_topics": [],
            "common_sections": {},
            "cta_usage": 0,
            "trust_signal_usage": 0,
        }

        for page in pages:
            entities = page.get("entities", {})
            topic_map["all_services"].update(entities.get("services", []))
            topic_map["all_technologies"].update(entities.get("technologies", []))
            topic_map["all_cities"].update(entities.get("cities", []))
            topic_map["faq_topics"].extend(
                [f["question"] for f in entities.get("faqs", [])]
            )
            if entities.get("cta_patterns"):
                topic_map["cta_usage"] += 1
            if entities.get("trust_signals"):
                topic_map["trust_signal_usage"] += 1

        # Convert sets to lists
        topic_map["all_services"] = list(topic_map["all_services"])
        topic_map["all_technologies"] = list(topic_map["all_technologies"])
        topic_map["all_cities"] = list(topic_map["all_cities"])

        return topic_map
