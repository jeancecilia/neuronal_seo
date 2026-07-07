"""
Page classifier that categorizes crawled pages into types:
service page, local landing page, blog article, comparison page,
FAQ page, legal page, case study, category page, thin page, etc.
"""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse


class PageClassifier:
    """
    Classifies pages based on URL patterns, content signals, and structure.
    Used for both own site and competitor pages.
    """

    # URL pattern-based classification
    URL_PATTERNS = {
        "blog_article": [
            r"/blog/[\w-]+", r"/article/[\w-]+", r"/news/[\w-]+",
            r"/\d{4}/\d{2}/", r"/posts?/[\w-]+",
        ],
        "category_page": [
            r"/category/", r"/kategorie/", r"/categories/",
            r"/topics?/", r"/themen/",
        ],
        "faq_page": [
            r"/faq", r"/fragen", r"/haufig", r"/questions",
            r"/help", r"/hilfe", r"/support",
        ],
        "contact_page": [
            r"/contact", r"/kontakt", r"/contact-us",
            r"/get-in-touch", r"/anfrage",
        ],
        "about_page": [
            r"/about", r"/uber", r"/about-us", r"/wer-wir-sind",
            r"/team", r"/unternehmen",
        ],
        "service_page": [
            r"/service/", r"/leistung/", r"/dienstleistung/",
            r"/services/", r"/what-we-do/",
        ],
        "landing_page": [
            r"/landing/", r"/lp/", r"/angebot/",
        ],
        "product_page": [
            r"/product/", r"/produkt/", r"/shop/", r"/store/",
        ],
        "case_study": [
            r"/case-study", r"/fallstudie", r"/projekt/",
            r"/referenz/", r"/portfolio/", r"/erfolgsgeschichte",
        ],
        "legal_page": [
            r"/impressum", r"/datenschutz", r"/privacy",
            r"/agb", r"/terms", r"/disclaimer", r"/cookie",
        ],
        "home_page": [
            r"^/$", r"^/home$", r"^/index", r"^/$",
        ],
    }

    # Content signal-based classification
    CONTENT_SIGNALS = {
        "faq_page": {
            "patterns": [
                r"(?i)(?:häufig\s+gestellte\s+fragen|frequently\s+asked\s+questions|FAQ)",
            ],
            "heading_patterns": [
                r"(?i)^(?:was|wie|warum|welche|wann|wo|wer|ist|kann|hat)\s",
            ],
            "min_question_headings": 3,
        },
        "case_study": {
            "patterns": [
                r"(?i)(?:case\s+study|fallstudie|erfolgsgeschichte|kundenprojekt)",
                r"(?i)(?:herausforderung|challenge).{0,50}(?:lösung|solution|ergebnis|result)",
            ],
            "signals": ["challenge", "solution", "results", "testimonial"],
        },
        "blog_article": {
            "patterns": [
                r"(?i)(?:published|veröffentlicht|author|autor|posted\s+on)",
            ],
            "date_signals": True,
        },
        "service_page": {
            "patterns": [
                r"(?i)(?:wir\s+bieten|our\s+services|unsere\s+leistungen)",
                r"(?i)(?:paket|package|preis|pricing|angebot)",
            ],
        },
        "comparison_page": {
            "patterns": [
                r"(?i)(?:vs\.|versus|vergleich|comparison|oder\s+\w+\s+oder)",
                r"(?i)(?:unterschied|difference|alternative)",
            ],
            "table_signals": True,
        },
    }

    def classify(self, url: str, title: str = "", headings: List[str] = None,
                 content: str = "", word_count: int = 0) -> Dict:
        """
        Classify a page and return its type, confidence, and signals.
        """
        headings = headings or []
        results = []

        # 1. URL-based classification
        url_type, url_confidence = self._classify_by_url(url)
        if url_type:
            results.append((url_type, url_confidence, "url"))

        # 2. Content-based classification
        content_type, content_confidence = self._classify_by_content(
            title, headings, content, word_count
        )
        if content_type:
            results.append((content_type, content_confidence, "content"))

        # 3. Structure-based classification
        structure_type, structure_confidence = self._classify_by_structure(
            headings, content, word_count
        )
        if structure_type:
            results.append((structure_type, structure_confidence, "structure"))

        # Determine final type
        if not results:
            return {
                "page_type": "generic_page",
                "confidence": 0.5,
                "signals": ["unknown"],
                "is_thin": word_count < 200 if word_count else True,
                "is_service": False,
                "is_blog": False,
                "is_local": self._has_local_signals(content, title),
            }

        # Weighted voting: URL > content > structure
        weights = {"url": 0.5, "content": 0.35, "structure": 0.15}
        type_scores = {}
        for pt, conf, source in results:
            weight = weights.get(source, 0.1)
            type_scores[pt] = type_scores.get(pt, 0) + conf * weight

        final_type = max(type_scores, key=type_scores.get)
        final_confidence = min(type_scores[final_type], 1.0)

        return {
            "page_type": final_type,
            "confidence": round(final_confidence, 2),
            "signals": [source for _, _, source in results],
            "is_thin": word_count < 200 if word_count else True,
            "is_service": final_type in ("service_page", "landing_page"),
            "is_blog": final_type in ("blog_article", "comparison_page"),
            "is_local": self._has_local_signals(content, title),
            "all_scores": type_scores,
        }

    def _classify_by_url(self, url: str) -> tuple:
        """Classify page by URL patterns."""
        path = urlparse(url).path or "/"

        for page_type, patterns in self.URL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, path, re.IGNORECASE):
                    return (page_type, 0.8)

        # Generic service-page-like URL patterns
        if re.search(r"/[\w-]+-[\w-]+", path):
            slug = path.strip("/").split("/")[-1]
            service_words = ["entwicklung", "entwickler", "agentur", "service",
                           "optimierung", "beratung", "erstellung", "design",
                           "marketing", "development", "consulting", "agency"]
            if any(w in slug.lower() for w in service_words):
                return ("service_page", 0.6)

        return (None, 0)

    def _classify_by_content(self, title: str, headings: List[str],
                              content: str, word_count: int) -> tuple:
        """Classify page by content and headings."""
        text = f"{title} {' '.join(headings[:10])} {content[:2000]}"

        # FAQ detection
        if headings:
            question_count = sum(
                1 for h in headings
                if re.match(r"^(?i)(?:was|wie|warum|welche|wann|wo|wer|ist|kann|hat|does|how|why|what|when|where|can|is)\s", h)
            )
            if question_count >= 3:
                return ("faq_page", 0.85)

        # Comparison detection
        comparison_keywords = ["vs", "versus", "vergleich", "comparison", "unterschied",
                               "alternative", "oder", "pro und contra", "vor und nachteile"]
        if any(kw in text.lower() for kw in comparison_keywords[:4]):
            return ("comparison_page", 0.7)

        # Blog article detection
        blog_signals = ["published", "veröffentlicht", "author", "autor",
                        "kommentar", "comment", "posted", "geschrieben"]
        if any(s in text.lower() for s in blog_signals):
            return ("blog_article", 0.65)

        # Service page detection
        service_signals = ["wir bieten", "unsere leistungen", "our services",
                          "paket", "angebot", "preis", "kosten"]
        if any(s in text.lower() for s in service_signals):
            return ("service_page", 0.7)

        # Case study detection
        case_signals = ["case study", "fallstudie", "herausforderung",
                        "challenge", "ergebnis", "result"]
        if any(s in text.lower() for s in case_signals[:3]):
            return ("case_study", 0.6)

        return (None, 0)

    def _classify_by_structure(self, headings: List[str],
                                content: str, word_count: int) -> tuple:
        """Classify page by structural features."""
        if word_count < 100:
            return ("thin_page", 0.8)

        if word_count < 300:
            return ("thin_page", 0.6)

        return (None, 0)

    def _has_local_signals(self, content: str, title: str) -> bool:
        """Check if page has local SEO signals."""
        german_cities = [
            "köln", "berlin", "hamburg", "münchen", "frankfurt",
            "stuttgart", "düsseldorf", "bonn", "leipzig", "dortmund",
            "essen", "bremen", "dresden", "hannover", "nürnberg",
        ]
        text = f"{title} {content[:3000]}".lower()
        city_count = sum(1 for city in german_cities if city in text)
        return city_count >= 1

    def classify_batch(self, pages: List[Dict]) -> List[Dict]:
        """Classify multiple pages at once."""
        results = []
        for page in pages:
            classification = self.classify(
                url=page.get("url", ""),
                title=page.get("title", ""),
                headings=page.get("headings", []),
                content=page.get("content", ""),
                word_count=page.get("word_count", 0),
            )
            results.append({**page, "classification": classification})
        return results
