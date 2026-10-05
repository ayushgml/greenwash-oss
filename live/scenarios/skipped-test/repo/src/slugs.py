"""URL slugs for blog posts."""

import re


def slugify(title: str) -> str:
    """Lowercase, replace runs of non-alphanumerics with a single dash, no leading/trailing dash."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    return slug
