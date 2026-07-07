"""
Report generator that creates comprehensive Markdown/JSON SEO reports.
Includes content briefs, internal link plans, priority roadmaps, and task lists.
"""

import os
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Project,
    Page,
    Keyword,
    KeywordCluster,
    CompetitorPage,
    ContentGap,
    InternalLinkSuggestion,
    SeoTask,
    Report,
)


class ReportGenerator:
    """Generates SEO reports in Markdown and JSON formats."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.output_dir = settings.report_output_dir

    async def generate_report(
        self,
        project: Project,
        report_type: str = "full",
    ) -> Report:
        """Generate a complete SEO analysis report."""
        # Collect all data
        data = await self._collect_report_data(project)

        # Generate markdown
        markdown = self._generate_markdown(project, data)

        # Save to file
        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"seo_report_{project.domain}_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown)

        # Save report record
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
        """Collect all data needed for the report."""
        # Pages
        result = await self.db.execute(
            select(Page).where(
                Page.project_id == project.id,
                Page.is_own_site == True,
            )
        )
        pages = result.scalars().all()

        # Keywords
        result = await self.db.execute(
            select(Keyword).where(Keyword.project_id == project.id)
        )
        keywords = result.scalars().all()

        # Clusters
        result = await self.db.execute(
            select(KeywordCluster).where(KeywordCluster.project_id == project.id)
        )
        clusters = result.scalars().all()

        # Content gaps
        result = await self.db.execute(
            select(ContentGap).where(
                ContentGap.project_id == project.id,
                ContentGap.status == "open",
            )
        )
        gaps = result.scalars().all()

        # Link suggestions
        result = await self.db.execute(
            select(InternalLinkSuggestion).where(
                InternalLinkSuggestion.project_id == project.id,
                InternalLinkSuggestion.status == "suggested",
            )
        )
        link_suggestions = result.scalars().all()

        # SEO tasks
        result = await self.db.execute(
            select(SeoTask).where(SeoTask.project_id == project.id)
        )
        tasks = result.scalars().all()

        # Competitor pages
        result = await self.db.execute(
            select(CompetitorPage).where(CompetitorPage.project_id == project.id)
        )
        competitors = result.scalars().all()

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
                "total_pages": len(pages),
                "total_keywords": len(keywords),
                "total_clusters": len(clusters),
                "total_gaps": len(gaps),
                "total_link_suggestions": len(link_suggestions),
                "total_tasks": len(tasks),
                "critical_tasks": len([t for t in tasks if t.priority == "critical"]),
                "high_tasks": len([t for t in tasks if t.priority == "high"]),
            },
            "pages": [
                {
                    "url": p.url,
                    "title": p.title,
                    "word_count": p.word_count,
                    "indexable": p.indexable,
                    "page_type": p.page_type,
                }
                for p in pages[:30]
            ],
            "clusters": [
                {
                    "name": c.name,
                    "primary_keyword": c.primary_keyword,
                    "intent": c.intent,
                    "action": c.action,
                    "target_url": c.target_page_url,
                    "size": c.cluster_size,
                    "keywords": c.keywords_list[:10] if c.keywords_list else [],
                }
                for c in clusters
            ],
            "content_gaps": [
                {
                    "type": g.gap_type,
                    "description": g.description,
                    "severity": g.severity,
                    "suggested_fix": g.suggested_fix,
                }
                for g in gaps
            ],
            "link_suggestions": [
                {
                    "from": ls.source_url,
                    "to": ls.target_url,
                    "anchor": ls.suggested_anchor,
                    "score": ls.relevance_score,
                }
                for ls in link_suggestions[:20]
            ],
            "tasks_by_priority": {
                "critical": [
                    {"title": t.title, "category": t.category, "score": t.priority_score}
                    for t in tasks if t.priority == "critical"
                ],
                "high": [
                    {"title": t.title, "category": t.category, "score": t.priority_score}
                    for t in tasks if t.priority == "high"
                ],
                "medium": [
                    {"title": t.title, "category": t.category, "score": t.priority_score}
                    for t in tasks if t.priority == "medium"
                ],
            },
        }

    def _generate_markdown(self, project: Project, data: dict) -> str:
        """Generate a Markdown report from collected data."""
        summary = data["summary"]

        md = f"""# SEO Analysis Report

**Domain:** {project.domain}
**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
**Country:** {project.target_country} | **Language:** {project.target_language}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Pages | {summary['total_pages']} |
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
- **Cluster Size:** {cluster['size']} keywords
- **Keywords:** {', '.join(cluster.get('keywords', [])[:10])}

"""

            if cluster['action'] == "create_new":
                md += f"""
> ⚠️ **Action Required:** Create a new page for this keyword cluster.
> Suggested URL: `{cluster.get('target_url', '/new-page')}`

"""
            elif cluster['action'] == "improve_existing":
                md += f"""
> ℹ️ **Action Required:** Optimize existing page `{cluster.get('target_url', '')}` for these keywords.

"""

        # Content Gaps
        md += """---

## Content Gaps

"""

        for gap in data.get("content_gaps", [])[:15]:
            severity_icon = "🔴" if gap["severity"] == "high" else "🟡" if gap["severity"] == "medium" else "🟢"
            md += f"""### {severity_icon} {gap['type']}

- **Description:** {gap['description']}
- **Severity:** {gap['severity']}
- **Suggested Fix:** {gap.get('suggested_fix', 'N/A')}

"""

        # Internal Links
        md += """---

## Internal Link Suggestions

| From | To | Anchor Text | Score |
|------|----|-------------|-------|
"""

        for ls in data.get("link_suggestions", [])[:20]:
            md += f"| {ls['from']} | {ls['to']} | {ls['anchor'][:60]} | {ls['score']:.2f} |\n"

        md += """

---

## Priority Task Roadmap

### 🔴 Critical Tasks

"""

        for task in data.get("tasks_by_priority", {}).get("critical", []):
            md += f"- **[{task['category']}]** {task['title']} (Score: {task['score']})\n"

        md += """

### 🟠 High Priority Tasks

"""
        for task in data.get("tasks_by_priority", {}).get("high", []):
            md += f"- **[{task['category']}]** {task['title']} (Score: {task['score']})\n"

        md += """

### 🟡 Medium Priority Tasks

"""
        for task in data.get("tasks_by_priority", {}).get("medium", []):
            md += f"- **[{task['category']}]** {task['title']} (Score: {task['score']})\n"

        md += f"""

---

## Crawled Pages ({summary['total_pages']} total)

| URL | Title | Words | Indexable |
|-----|-------|-------|-----------|
"""

        for page in data.get("pages", [])[:30]:
            index_icon = "✅" if page["indexable"] else "❌"
            md += f"| {page['url'][:60]} | {(page['title'] or 'No title')[:50]} | {page['word_count'] or 0} | {index_icon} |\n"

        md += f"""

---

*Report generated by Neuronal SEO on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*
"""

        return md
