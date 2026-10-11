#!/usr/bin/env python3
"""Check upstream XiaoMi/ha_xiaomi_home releases and compare against our fork.

Usage:
    python3 scripts/check_upstream.py
    python3 scripts/check_upstream.py --update
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

UPSTREAM_REPO = "XiaoMi/ha_xiaomi_home"
VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".upstream_version")


def get_tracked_version() -> str:
    """Read the currently tracked upstream version from file."""
    if os.path.isfile(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as fp:
            return fp.read().strip()
    return "v0.5.0"


def save_tracked_version(version: str) -> None:
    """Save the newly adopted upstream version."""
    with open(VERSION_FILE, "w", encoding="utf-8") as fp:
        fp.write(f"{version}\n")
    print(f"[+] Updated tracked upstream version to: {version}")


def github_api_get(url: str) -> dict:
    """Send an authenticated or anonymous GET request to GitHub API."""
    headers = {
        "User-Agent": "ha-xiaomi-home-mod-tracker",
        "Accept": "application/vnd.github.v3+json",
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        print(f"[-] GitHub API error ({err.code}): {err.reason}", file=sys.stderr)
        if err.code == 403:
            print("[-] API rate limit reached. Set GITHUB_TOKEN environment variable to increase limits.", file=sys.stderr)
        sys.exit(1)
    except Exception as err:
        print(f"[-] Network connection error: {err}", file=sys.stderr)
        sys.exit(1)


def categorize_file(filename: str) -> str:
    """Categorize changed files into actionable triage groups."""
    if "spec_modify.yaml" in filename:
        return "Device Spec Override (High Value)"
    if "specv2entity.py" in filename:
        return "Spec Property Entity Mapping (High Value)"
    if "miot_cloud.py" in filename or "miot_mips.py" in filename:
        return "Core Protocol / Communication (Review Needed)"
    if "miot_device.py" in filename or "miot_client.py" in filename:
        return "Core Orchestration (Review Needed - Avoid Duplicates)"
    if "translations" in filename:
        return "Translations / I18n"
    if "config_flow" in filename:
        return "Config Flow UI"
    return "Other / Miscellaneous"


def main():
    parser = argparse.ArgumentParser(description="Track upstream XiaoMi/ha_xiaomi_home releases")
    parser.add_argument("--update", action="store_true", help="Update .upstream_version to the latest upstream release")
    parser.add_argument("--ci", action="store_true", help="Exit with code 1 if a new release is available (for CI pipelines)")
    args = parser.parse_args()

    tracked_version = get_tracked_version()
    print("=" * 70)
    print(" Upstream Release Tracker: XiaoMi/ha_xiaomi_home")
    print("=" * 70)
    print(f"[*] Currently tracked version: {tracked_version}")

    latest_release = github_api_get(f"https://api.github.com/repos/{UPSTREAM_REPO}/releases/latest")
    latest_tag = latest_release.get("tag_name")
    latest_name = latest_release.get("name", latest_tag)
    published_at = latest_release.get("published_at", "N/A")
    release_url = latest_release.get("html_url")

    print(f"[*] Latest upstream release:   {latest_name} ({latest_tag})")
    print(f"[*] Published date:            {published_at}")
    print(f"[*] Upstream release link:     {release_url}")
    print("-" * 70)

    if latest_tag == tracked_version:
        print(f"[✓] Your fork is 100% up to date with the latest upstream release ({latest_tag})!")
        print("    No new upstream releases detected.")
        print("=" * 70)
        sys.exit(0)

    print(f"[!] NEW UPSTREAM RELEASE DETECTED: {tracked_version} -> {latest_tag}")
    compare_url = f"https://github.com/{UPSTREAM_REPO}/compare/{tracked_version}...{latest_tag}"
    print(f"[*] Comparison link: {compare_url}")
    print("-" * 70)

    # Fetch comparison details
    compare_data = github_api_get(f"https://api.github.com/repos/{UPSTREAM_REPO}/compare/{tracked_version}...{latest_tag}")
    commits = compare_data.get("commits", [])
    files = compare_data.get("files", [])

    print(f"[*] Commits ahead ({len(commits)}):")
    for commit in commits:
        sha = commit.get("sha", "")[:7]
        author = commit.get("commit", {}).get("author", {}).get("name", "Unknown")
        msg = commit.get("commit", {}).get("message", "").split("\n")[0]
        print(f"    - [{sha}] {msg} (by {author})")

    print(f"\n[*] Files modified ({len(files)}):")
    for file_info in files:
        fn = file_info.get("filename", "")
        status = file_info.get("status", "")
        cat = categorize_file(fn)
        print(f"    - {fn} [{status}] -> {cat}")

    print("-" * 70)
    print("[*] Recommended Next Steps:")
    print("    1. Review files flagged as 'High Value' (spec_modify.yaml, specv2entity.py).")
    print("    2. Cherry-pick bug fixes while avoiding regressions to custom fork features.")
    print("    3. Ensure 0 Chinese characters in code: use Unicode escapes (\\uXXXX) if copying strings.")
    print("    4. Run 'python3 scripts/quality_audit.py' to verify tests and compliance.")
    print("    5. Once adopted, run 'python3 scripts/check_upstream.py --update' to advance tracking.")
    print("=" * 70)

    if args.update:
        save_tracked_version(latest_tag)

    if args.ci:
        sys.exit(1)


if __name__ == "__main__":
    main()
