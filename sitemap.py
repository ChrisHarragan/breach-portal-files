"""
Sitemap generator for Breach Signal portal.

Shared module — used by main.py (/generate-sitemap route)
and generate_sitemap.py (standalone CLI script).
"""

import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import date

import requests

log = logging.getLogger(__name__)

SITEMAP_COLS = "id,company_name,date_reported"


def _slugify(name: str) -> str:
    name = (name or "").lower().strip()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def build_sitemap(
    supabase_url: str,
    supabase_key: str,
    portal_url: str,
    output_path: str = "static/sitemap.xml",
) -> int:
    """
    Query all breaches, write XML sitemap to output_path.
    Returns number of URLs written.
    """
    portal_url = portal_url.rstrip("/")
    headers = {
        "apikey":        supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }

    # Page through all breaches
    rows, offset = [], 0
    while True:
        r = requests.get(
            f"{supabase_url}/rest/v1/breaches",
            headers=headers,
            params={
                "select": SITEMAP_COLS,
                "order":  "id.asc",
                "limit":  "1000",
                "offset": str(offset),
            },
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        if len(batch) < 1000:
            break
        log.info("Fetched %d breach rows so far…", len(rows))

    log.info("Total rows fetched: %d", len(rows))

    # Build XML
    root = ET.Element("urlset")
    root.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")

    today = date.today().isoformat()
    count = 0

    for row in rows:
        bid  = row.get("id")
        name = row.get("company_name") or ""
        if not bid or not name:
            continue

        slug    = _slugify(name)
        lastmod = row.get("date_reported") or today

        url_el = ET.SubElement(root, "url")
        ET.SubElement(url_el, "loc").text         = f"{portal_url}/breaches/{bid}-{slug}"
        ET.SubElement(url_el, "lastmod").text     = lastmod
        ET.SubElement(url_el, "changefreq").text  = "monthly"
        ET.SubElement(url_el, "priority").text    = "0.7"
        count += 1

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode" if False else "utf-8", xml_declaration=False)

    log.info("Sitemap written to %s (%d URLs)", output_path, count)
    return count
