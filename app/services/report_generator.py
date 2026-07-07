"""
Report generator that creates comprehensive Markdown/JSON SEO reports.
"""

import os
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Project, Page, Keyword, KeywordCluster,
    CompetitorPage, ContentGap,
    InternalLinkSuggestion, SeoTask, Report,
)


class ReportGenerator:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.output_dir = settings.report_output_dir

    async def generate_report(self, project: Project, report_type: str = "full") -> Report:
        data = await self._collect_report_data(project)
        markdown = self._generate_markdown(project, data)

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"seo_report_{project.domain}_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown)

        report = Report(
            project_id=project.id,
            report_type=report_type,
            title=f"SEO Analysis Report - {project.domain} - {datetime.utcnow().strftime('%Y-%m-%d')}",
            content_markdown=markdown,
            content_json=data,
            file_path=filepath,
        )
        self.db.add(report)
        await self.db.flush()
        return report

    async def _collect_report_data(self, project: Project) -> dict:
        result = await self.db.execute(
            select(Page).where(Page.project_id == project.id, Page.is_own_site == True)
        )
        pages = result.scalars().all()

        result = await self.db.execute(
            select(Keyword).where(Keyword.project_id == project.id)
        )
        keywords = result.scalars().all()

        result = await self.db.execute(
            select(KeywordCluster).where(KeywordCluster.project_id == project.id)
        )
        clusters = result.scalars().all()

        result = await self.db.execute(
            select(ContentGap).where(ContentGap.project_id == project.id, ContentGap.status == "open")
        )
        gaps = result.scalars().all()

        result = await self.db.execute(
            select(InternalLinkSuggestion).where(
                InternalLinkSuggestion.project_id == project.id,
                InternalLinkSuggestion.status == "suggested",
            )
        )
        link_suggestions = result.scalars().all()

        result = await self.db.execute(
            select(SeoTask).where(SeoTask.project_id == project.id)
        )
        tasks = result.scalars().all()

        result = await self.db.execute(
            select(CompetitorPage).where(CompetitorPage.project_id == project.id)
        )
        competitors = result.scalars().all()

        # Determine crawl status
        pages_with_content = [p for p in pages if p.content and (p.word_count or 0) > 50]
        pages_403 = [p for p in pages if p.status_code == 403]
        crawl_ok = len(pages_with_content) > 0

        return {
            "project": {
                "domain": project.domain,
                "country": project.target_country,
                "language": project.target_language,
                "cities": project.target_cities,
                "services": project.services,
                "competitors": project.competitors,
            },
            "summary": {
                "report_type": "full_analysis" if crawl_ok else "seed_report",
                "crawl_status": "success" if crawl_ok else ("failed_403" if pages_403 else "no_pages"),
                "total_pages": len(pages),
                "pages_with_content": len(pages_with_content),
                "pages_blocked_403": len(pages_403),
                "total_keywords": len(keywords),
                "total_clusters": len(clusters),
                "total_gaps": len(gaps),
                "total_link_suggestions": len(link_suggestions),
                "total_tasks": len(tasks),
                "critical_tasks": len([t for t in tasks if t.priority == "critical"]),
                "high_tasks": len([t for t in tasks if t.priority == "high"]),
            },
            "pages": [
                {"url": p.url, "title": p.title, "word_count": p.word_count,
                 "status_code": p.status_code, "indexable": p.indexable, "page_type": p.page_type}
                for p in pages[:30]
            ],
            "clusters": [
                {"name": c.name, "primary_keyword": c.primary_keyword, "intent": c.intent,
                 "action": c.action, "target_url": c.target_page_url, "size": c.cluster_size,
                 "keywords": c.keywords_list[:10] if c.keywords_list else []}
                for c in clusters
            ],
            "content_gaps": [
                {"type": g.gap_type, "description": g.description, "severity": g.severity,
                 "suggested_fix": g.suggested_fix}
                for g in gaps
            ],
            "link_suggestions": [
                {"from": ls.source_url, "to": ls.target_url, "anchor": ls.suggested_anchor,
                 "score": ls.relevance_score}
                for ls in link_suggestions[:20]
            ],
            "tasks_by_priority": {
                "critical": [{"title": t.title, "category": t.category, "score": t.priority_score}
                              for t in tasks if t.priority == "critical"],
                "high": [{"title": t.title, "category": t.category, "score": t.priority_score}
                          for t in tasks if t.priority == "high"],
                "medium": [{"title": t.title, "category": t.category, "score": t.priority_score}
                            for t in tasks if t.priority == "medium"],
            },
        }

    def _generate_markdown(self, project: Project, data: dict) -> str:
        summary = data["summary"]
        report_type_label = "📊 Full Analysis" if summary.get("report_type") == "full_analysis" else "🌱 Seed Report"
        crawl_label = summary.get("crawl_status", "unknown")

        md = f"""# SEO Analysis Report — {report_type_label}

**Domain:** {project.domain}
**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
**Country:** {project.target_country} | **Language:** {project.target_language}
**Crawl Status:** {crawl_label}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Report Type | {report_type_label} |
| Crawl Status | {crawl_label} |
| Total Pages | {summary['total_pages']} |
| Pages With Content | {summary.get('pages_with_content', 0)} |
| Pages Blocked (403) | {summary.get('pages_blocked_403', 0)} |
| Total Keywords | {summary['total_keywords']} |
| Keyword Clusters | {summary['total_clusters']} |
| Content Gaps | {summary['total_gaps']} |
| Link Suggestions | {summary['total_link_suggestions']} |
| SEO Tasks | {summary['total_tasks']} |
| 🔴 Critical Tasks | {summary['critical_tasks']} |
| 🟠 High Priority | {summary['high_tasks']} |

---

## Project Configuration

- **Services:** {', '.join(project.services or [])}
- **Target Cities:** {', '.join(project.target_cities or [])}
- **Competitors:** {', '.join(project.competitors or [])}

---

## Keyword Clusters

"""

        for cluster in data.get("clusters", []):
            md += f"""### {cluster['name']}
- **Primary Keyword:** {cluster['primary_keyword']}
- **Intent:** {cluster['intent']}
- **Action:** {cluster['action']}
- **Target URL:** {cluster.get('target_url', 'New page needed')}
- **Size:** {cluster['size']} keywords
- **Keywords:** {', '.join(cluster.get('keywords', [])[:10])}

"""

        md += """---

## Content Gaps

"""

        for gap in data.get("content_gaps", [])[:15]:
            icon = "🔴" if gap["severity"] == "high" else "🟡" if gap["severity"] == "medium" else "🟢"
            md += f"### {icon} {gap['type']}\n- {gap['description']}\n- Fix: {gap.get('suggested_fix', 'N/A')}\n\n"

        md += """---

## Priority Task Roadmap

### 🔴 Critical Tasks

"""
        for task in data.get("tasks_by_priority", {}).get("critical", []):
            md += f"- **[{task['category']}]** {task['title']} (Score: {task['score']})\n"

        md += "\n### 🟠 High Priority Tasks\n"
        for task in data.get("tasks_by_priority", {}).get("high", []):
            md += f"- **[{task['category']}]** {task['title']} (Score: {task['score']})\n"

        md += "\n### 🟡 Medium Priority Tasks\n"
        for task in data.get("tasks_by_priority", {}).get("medium", []):
            md += f"- **[{task['category']}]** {task['title']} (Score: {task['score']})\n"

        md += f"""

---

## Crawled Pages ({summary['total_pages']} total)

| URL | Title | Words | Status | Indexable |
|-----|-------|-------|--------|-----------|
"""
        for page in data.get("pages", [])[:30]:
            icon = "✅" if page["indexable"] else "❌"
            status = page.get("status_code", "?")
            md += f"| {page['url'][:60]} | {(page['title'] or 'No title')[:40]} | {page['word_count'] or 0} | {status} | {icon} |\n"

        md += f"""

---

*Report generated by Neuronal SEO on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*
"""
        return md
