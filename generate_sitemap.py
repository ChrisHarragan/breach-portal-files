#!/usr/bin/env python3
"""
Standalone sitemap generator.

Usage:
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python generate_sitemap.py
    python generate_sitemap.py --output static/sitemap.xml
"""

import argparse
import logging
import os
import sys

from sitemap import build_sitemap

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")

def main():
    parser = argparse.ArgumentParser(description="Generate breach portal sitemap")
    parser.add_argument("--output", default="static/sitemap.xml", help="Output path")
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    portal_url   = os.environ.get("PORTAL_URL", "https://web-production-54737.up.railway.app")

    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    count = build_sitemap(supabase_url, supabase_key, portal_url, args.output)
    print(f"Done. {count} URLs written to {args.output}")

if __name__ == "__main__":
    main()
