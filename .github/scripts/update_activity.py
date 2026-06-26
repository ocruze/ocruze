#!/usr/bin/env python3
"""
Fetch the latest public GitHub activity for a user and update the
RECENT_ACTIVITY section in README.md.

All URLs are built from repo.name + payload numbers so that a missing
html_url on the pull_request object (a known GitHub API trimming) can
never produce an [undefined] link.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

USERNAME = "ocruze"
MAX_LINES = 5
README_FILE = "README.md"

# Events whose comment sub-events we skip (mirrors disabled_events: [comments])
SKIP_TYPES = {
    "IssueCommentEvent",
    "CommitCommentEvent",
    "PullRequestReviewCommentEvent",
}

GH_BASE = "https://github.com"


def gh_day_suffix(day):
    if 11 <= (day % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_date(dt):
    """Friday, June 26th, 2026, 1:07:07 AM"""
    day = dt.day
    suffix = gh_day_suffix(day)
    return dt.strftime(f"%A, %B {day}{suffix}, %Y, %-I:%M:%S %p")


def repo_link(name):
    return f"[{name}]({GH_BASE}/{name})"


def pr_link(repo_name, number):
    return f"[#{number}]({GH_BASE}/{repo_name}/pull/{number})"


def issue_link(repo_name, number):
    return f"[#{number}]({GH_BASE}/{repo_name}/issues/{number})"


def serialize_event(event):
    """Return a formatted activity line or None to skip the event."""
    t = event.get("type")
    payload = event.get("payload", {})
    repo_name = event.get("repo", {}).get("name", "")

    if t in SKIP_TYPES:
        return None

    if t == "PullRequestEvent":
        action = payload.get("action")
        pr = payload.get("pull_request", {})
        number = pr.get("number") or payload.get("number")
        if number is None:
            return None
        link = pr_link(repo_name, number)
        rlink = repo_link(repo_name)
        if action == "opened":
            return f"💪 Opened PR {link} in {rlink}"
        if action == "closed":
            if pr.get("merged"):
                return f"🎉 Merged PR {link} in {rlink}"
            return f"❌ Closed PR {link} in {rlink}"
        return None

    if t == "PullRequestReviewEvent":
        pr = payload.get("pull_request", {})
        number = pr.get("number") or payload.get("number")
        review = payload.get("review", {})
        state = review.get("state", "").lower()
        if number is None:
            return None
        link = pr_link(repo_name, number)
        rlink = repo_link(repo_name)
        review_url = review.get("html_url") or f"{GH_BASE}/{repo_name}/pull/{number}"
        link_with_review = f"[#{number}]({review_url})"
        if state == "approved":
            return f"👍 Approved {link_with_review} in {rlink}"
        if state == "changes_requested":
            return f"🔴 Requested changes in {link_with_review} in {rlink}"
        return None

    if t == "IssuesEvent":
        action = payload.get("action")
        issue = payload.get("issue", {})
        number = issue.get("number")
        if number is None:
            return None
        link = issue_link(repo_name, number)
        rlink = repo_link(repo_name)
        if action == "opened":
            return f"❗️ Opened issue {link} in {rlink}"
        if action == "closed":
            return f"✔️ Closed issue {link} in {rlink}"
        return None

    if t == "WatchEvent" and payload.get("action") == "started":
        return f"⭐ Starred {repo_link(repo_name)}"

    if t == "CreateEvent" and payload.get("ref_type") == "repository":
        return f"📔 Created new repository {repo_link(repo_name)}"

    if t == "ForkEvent":
        forkee = payload.get("forkee", {})
        fork_name = forkee.get("full_name", "")
        fork_url = forkee.get("html_url") or f"{GH_BASE}/{fork_name}"
        return f"🔱 Forked [{fork_name}]({fork_url}) from {repo_link(repo_name)}"

    if t == "MemberEvent" and payload.get("action") == "added":
        return f"🤝 Became collaborator on {repo_link(repo_name)}"

    if t == "ReleaseEvent" and payload.get("action") == "published":
        release = payload.get("release", {})
        tag = release.get("tag_name", "release")
        url = release.get("html_url") or f"{GH_BASE}/{repo_name}/releases"
        return f"✌️ Released [{tag}]({url}) in {repo_link(repo_name)}"

    if t == "GollumEvent":
        pages = payload.get("pages", [])
        if pages:
            page = pages[0]
            wiki_url = page.get("html_url") or f"{GH_BASE}/{repo_name}/wiki"
            return f"📖 Created new wiki page [{page.get('title', 'page')}]({wiki_url}) in {repo_link(repo_name)}"
        return None

    return None


def fetch_events():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = ["Accept: application/vnd.github+json"]
    if token:
        headers.append(f"Authorization: Bearer {token}")

    cmd = ["gh", "api", f"/users/{USERNAME}/events/public?per_page=100"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error fetching events: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def replace_between(lines, start_marker, end_marker, new_content):
    """Replace lines between start_marker and end_marker (exclusive)."""
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == start_marker)
        end = next(i for i, l in enumerate(lines) if l.strip() == end_marker)
    except StopIteration:
        return lines  # markers not found; leave unchanged
    return lines[: start + 1] + new_content + lines[end:]


def main():
    events = fetch_events()

    lines = []
    for event in events:
        line = serialize_event(event)
        if line:
            lines.append(line)
        if len(lines) >= MAX_LINES:
            break

    numbered = [f"{i + 1}. {line}" for i, line in enumerate(lines)]

    with open(README_FILE, "r", encoding="utf-8") as f:
        readme = f.read().splitlines()

    readme = replace_between(
        readme,
        "<!--RECENT_ACTIVITY:start-->",
        "<!--RECENT_ACTIVITY:end-->",
        numbered,
    )

    now = datetime.now(timezone.utc)
    date_str = format_date(now)
    readme = replace_between(
        readme,
        "<!--RECENT_ACTIVITY:last_update-->",
        "<!--RECENT_ACTIVITY:last_update_end-->",
        [f"Last Updated: {date_str}"],
    )

    new_content = "\n".join(readme) + "\n"
    with open(README_FILE, "r", encoding="utf-8") as f:
        old_content = f.read()

    if new_content == old_content:
        print("No changes detected. README unchanged.")
        return

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"README updated with {len(lines)} activity lines.")

    # Commit and push
    subprocess.run(["git", "config", "user.name", "readme-bot"], check=True)
    subprocess.run(
        [
            "git",
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ],
        check=True,
    )
    subprocess.run(["git", "add", README_FILE], check=True)
    result = subprocess.run(
        ["git", "commit", "-m", "⚡ Update README with the recent activity"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        sys.exit(result.returncode)
    subprocess.run(["git", "push"], check=True)
    print("Committed and pushed.")


if __name__ == "__main__":
    main()
