#!/usr/bin/env python3
"""
Check upstream WGDashboard for new releases and commits since our last sync.
Creates a GitLab issue if new upstream activity is detected.

Env vars required:
- GITLAB_API_TOKEN: PAT for creating issues in our GitLab project
- GITLAB_PROJECT_ID: our project ID (49)
- GITLAB_URL: GitLab base URL
"""
import json
import os
import subprocess
import sys
import urllib.request

UPSTREAM_REPO = "donaldzou/WGDashboard"
OUR_PROJECT_ID = os.environ.get("GITLAB_PROJECT_ID", "49")
GITLAB_URL = os.environ.get("GITLAB_URL", "https://git.half.net.ua")
GITLAB_TOKEN = os.environ.get("GITLAB_API_TOKEN")
STATE_FILE = "/opt/WGDashboard/.upstream_state.json"


def github_api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "wgdashboard-plus-plus"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_release": None, "last_commit_sha": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def create_gitlab_issue(title, description, labels="upstream-watch"):
    if not GITLAB_TOKEN:
        print("GITLAB_API_TOKEN not set, printing issue instead:")
        print(f"--- {title} ---")
        print(description)
        return
    data = json.dumps({"title": title, "description": description, "labels": labels}).encode()
    req = urllib.request.Request(
        f"{GITLAB_URL}/api/v4/projects/{OUR_PROJECT_ID}/issues",
        data=data,
        headers={"PRIVATE-TOKEN": GITLAB_TOKEN, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
        print(f"Created issue #{result['iid']}: {result['web_url']}")


def check_releases(state):
    try:
        latest = github_api(f"/repos/{UPSTREAM_REPO}/releases/latest")
    except Exception as e:
        print(f"Failed to fetch latest release: {e}")
        return state

    tag = latest.get("tag_name")
    if not tag:
        return state

    if tag == state.get("last_release"):
        print(f"No new release (current: {tag})")
        return state

    title = f"🔔 Upstream WGDashboard new release: {tag}"
    body = f"""## New upstream release

**Upstream:** https://github.com/{UPSTREAM_REPO}
**Release:** [{tag}]({latest.get('html_url')})
**Published:** {latest.get('published_at')}

### Release notes

{latest.get('body', 'No release notes provided.')[:3000]}

---

**Action:** Review changes and consider cherry-picking relevant fixes/features into WgDashboard++.
"""
    create_gitlab_issue(title, body, labels="upstream-watch,release")
    state["last_release"] = tag
    return state


def check_commits(state):
    try:
        commits = github_api(f"/repos/{UPSTREAM_REPO}/commits?sha=main&per_page=20")
    except Exception as e:
        print(f"Failed to fetch commits: {e}")
        return state

    if not commits:
        return state

    latest_sha = commits[0]["sha"]
    last_known = state.get("last_commit_sha")

    if last_known == latest_sha:
        print(f"No new commits (latest: {latest_sha[:8]})")
        return state

    # Collect new commits
    new_commits = []
    for c in commits:
        if c["sha"] == last_known:
            break
        new_commits.append(c)

    if not new_commits:
        state["last_commit_sha"] = latest_sha
        return state

    # Only create issue if there are many commits or a notable one
    if len(new_commits) < 3:
        print(f"Only {len(new_commits)} new commits, skipping issue")
        state["last_commit_sha"] = latest_sha
        return state

    title = f"📋 Upstream WGDashboard: {len(new_commits)} new commits"
    lines = [f"## Recent upstream commits\n", f"**Upstream:** https://github.com/{UPSTREAM_REPO}\n"]
    lines.append(f"### {len(new_commits)} new commits since last check\n")
    for c in new_commits[:20]:
        msg = c["commit"]["message"].split("\n")[0][:100]
        sha = c["sha"][:8]
        url = c["html_url"]
        lines.append(f"- [`{sha}`]({url}) {msg}")
    lines.append("\n---\n**Action:** Review commits for fixes/features worth cherry-picking.")
    create_gitlab_issue(title, "\n".join(lines), labels="upstream-watch,commits")
    state["last_commit_sha"] = latest_sha
    return state


def main():
    state = load_state()
    state = check_releases(state)
    state = check_commits(state)
    save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
