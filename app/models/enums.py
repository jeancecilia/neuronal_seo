"""
Enumerations used across the SEO pipeline models.
"""

from enum import Enum


class IntentType(str, Enum):
    LOCAL_TRANSACTIONAL = "local_transactional"
    COMMERCIAL = "commercial"
    INFORMATIONAL = "informational"
    COMPARISON = "comparison"
    PROBLEM_SOLUTION = "problem_solution"
    BRAND = "brand"
    SUPPORT = "support"
    NAVIGATIONAL = "navigational"
    UNKNOWN = "unknown"


class PageType(str, Enum):
    LANDING_PAGE = "landing_page"
    SERVICE_PAGE = "service_page"
    BLOG_POST = "blog_post"
    ARTICLE = "article"
    PRODUCT_PAGE = "product_page"
    CATEGORY_PAGE = "category_page"
    FAQ_PAGE = "faq_page"
    CONTACT_PAGE = "contact_page"
    ABOUT_PAGE = "about_page"
    HOME_PAGE = "home_page"
    UNKNOWN = "unknown"


class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    REJECTED = "rejected"


class ClusterAction(str, Enum):
    CREATE_NEW = "create_new"
    IMPROVE_EXISTING = "improve_existing"
    MERGE = "merge"
    NOINDEX = "noindex"
    NO_ACTION = "no_action"


class GapSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
