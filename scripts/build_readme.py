"""Rebuild the generated sections of README.md from public GitHub data.

Run every day by .github/workflows/readme.yml. Standard library only.
Generated sections sit between <!-- work:start --> and <!-- work:end -->, and between
<!-- activity:start --> and <!-- activity:end -->. README.md is written only when its content changes.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

USER = "Baptiste6913"
SELECTED = ["ede-platform", "coach-lifestyle", "Osint-tool"]
ACTIVITY_LIMIT = 5
ACTIVITY_PER_REPO = 2
# Engineering commits only: maintenance types (docs, chore, ci, style, test, build) are left out.
SKIPPED_TYPES = re.compile(r"^(docs|chore|ci|style|test|build)(\(.+?\))?!?:", re.I)
MIN_LANGUAGE_SHARE = 0.05
API = "https://api.github.com"
README = Path(__file__).resolve().parent.parent / "README.md"


def get(path):
    request = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    token = os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def clean(text):
    """One line of plain text, safe inside a Markdown table cell or list item."""
    text = " ".join(text.split()).replace(" \u2014 ", ": ").replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def languages(repo):
    sizes = get(f"/repos/{USER}/{repo}/languages")
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda item: -item[1])
    return ", ".join(name for name, size in ranked if size / total >= MIN_LANGUAGE_SHARE) or "-"


def work_list():
    """One item per selected repository: link, description, then languages and last push on a second line."""
    items = []
    for name in SELECTED:
        repo = get(f"/repos/{USER}/{name}")
        if repo["private"] or repo["archived"]:
            continue
        items.append(f"- **[{name}]({repo['html_url']})**: {clean(repo['description'] or '')}<br>"
                     f"<sub>{languages(name)} · last push {repo['pushed_at'][:10]}</sub>")
    return "\n".join(items)


def activity():
    items = []
    for repo in get(f"/users/{USER}/repos?type=owner&sort=pushed&per_page=100"):
        if repo["fork"] or repo["archived"] or repo["private"] or repo["name"] == USER:
            continue
        kept = 0
        for commit in get(f"/repos/{USER}/{repo['name']}/commits?per_page=100"):
            subject = commit["commit"]["message"].splitlines()[0]
            is_bot = (commit.get("author") or {}).get("type") == "Bot"
            if is_bot or subject.startswith("Merge ") or SKIPPED_TYPES.match(subject):
                continue
            items.append((commit["commit"]["author"]["date"], repo["name"], commit["html_url"], subject))
            kept += 1
            if kept == ACTIVITY_PER_REPO:
                break
    items.sort(reverse=True)
    return "\n".join(f"- `{date[:10]}` [{name}]({url}): {clean(subject)}"
                     for date, name, url, subject in items[:ACTIVITY_LIMIT])


def fill(text, key, body):
    pattern = re.compile(rf"(<!-- {key}:start -->\n).*?(<!-- {key}:end -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"Marker '{key}' not found in README.md")
    return pattern.sub(lambda match: match.group(1) + body + "\n" + match.group(2), text)


def main():
    with open(README, encoding="utf-8", newline="") as handle:
        current = handle.read()
    updated = fill(fill(current, "work", work_list()), "activity", activity())
    if updated == current:
        print("README.md unchanged")
        return
    with open(README, "w", encoding="utf-8", newline="") as handle:
        handle.write(updated)
    print("README.md updated")


if __name__ == "__main__":
    main()
