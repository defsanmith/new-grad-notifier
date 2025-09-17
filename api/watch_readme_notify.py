"""
Vercel Serverless Function to monitor GitHub file changes and send email notifications.

This function polls the GitHub API for commits that touched a specific file,
compares against the last seen commit SHA stored in Vercel KV, and sends
email notifications via Gmail SMTP when changes are detected.

Uses only Python stdlib - no external dependencies.
"""

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Dict, List, Optional, Tuple, Any


def _json_response(
    status: int, data: Dict[str, Any]
) -> Tuple[int, Dict[str, str], str]:
    """Helper to return JSON response with proper content type."""
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data, indent=2)
    return status, headers, body


def gh_api(url: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Make a GET request to GitHub API with proper headers.

    Args:
        url: GitHub API URL
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response

    Raises:
        urllib.error.HTTPError: On HTTP errors
        json.JSONDecodeError: On invalid JSON
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "vercel-github-watcher/1.0",
    }

    # Add authorization if GitHub token is provided
    gh_token = os.environ.get("GH_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Include response body in error for debugging
        error_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        raise urllib.error.HTTPError(
            e.url, e.code, f"{e.reason}: {error_body}", e.headers, e.fp
        )


def get_commits_touching_file(
    owner: str, repo: str, branch: str, path: str, per_page: int = 30
) -> List[Dict[str, Any]]:
    """
    Get commits that touched a specific file in a repository.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch name
        path: File path
        per_page: Number of commits to fetch

    Returns:
        List of commit objects from GitHub API
    """
    encoded_path = urllib.parse.quote(path, safe="")
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/commits"
        f"?sha={branch}&path={encoded_path}&per_page={per_page}"
    )
    return gh_api(url)


def kv_get(key: str, timeout: int = 10) -> Optional[str]:
    """
    Get value from Vercel KV store.

    Args:
        key: KV key to retrieve
        timeout: Request timeout in seconds

    Returns:
        Stored value or None if not found/error
    """
    kv_url = os.environ.get("KV_REST_API_URL")
    kv_token = os.environ.get("KV_REST_API_TOKEN")

    if not kv_url or not kv_token:
        raise ValueError("KV_REST_API_URL and KV_REST_API_TOKEN must be set")

    encoded_key = urllib.parse.quote(key, safe="")
    url = f"{kv_url}/get/{encoded_key}"

    headers = {
        "Authorization": f"Bearer {kv_token}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("result")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # Key not found
        raise


def kv_set(key: str, value: str, timeout: int = 10) -> None:
    """
    Set value in Vercel KV store.

    Args:
        key: KV key to set
        value: Value to store
        timeout: Request timeout in seconds

    Raises:
        urllib.error.HTTPError: On HTTP errors
        ValueError: If KV credentials not configured
    """
    kv_url = os.environ.get("KV_REST_API_URL")
    kv_token = os.environ.get("KV_REST_API_TOKEN")

    if not kv_url or not kv_token:
        raise ValueError("KV_REST_API_URL and KV_REST_API_TOKEN must be set")

    encoded_key = urllib.parse.quote(key, safe="")
    encoded_value = urllib.parse.quote(value, safe="")
    url = f"{kv_url}/set/{encoded_key}/{encoded_value}"

    headers = {
        "Authorization": f"Bearer {kv_token}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, method="POST", headers=headers)

    with urllib.request.urlopen(req, timeout=timeout) as response:
        response.read()  # Consume response


def send_email(subject: str, body: str, timeout: int = 20) -> None:
    """
    Send email via Gmail SMTP.

    Args:
        subject: Email subject
        body: Email body (HTML)
        timeout: SMTP timeout in seconds

    Raises:
        ValueError: If SMTP credentials not configured
        smtplib.SMTPException: On SMTP errors
    """
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    mail_from = os.environ.get("MAIL_FROM", smtp_user)
    mail_to = os.environ.get("MAIL_TO", "")

    if not smtp_user or not smtp_pass:
        raise ValueError("SMTP_USER and SMTP_PASS must be set")

    if not mail_to:
        raise ValueError("MAIL_TO must be set")

    # Parse comma-separated recipient list
    recipients = [email.strip() for email in mail_to.split(",") if email.strip()]
    if not recipients:
        raise ValueError("MAIL_TO must contain at least one valid email")

    # Create email message
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(body, subtype="html")

    # Send email via SMTP
    context = ssl.create_default_context()

    with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def build_email_body(
    commits: List[Dict[str, Any]], owner: str, repo: str, branch: str, path: str
) -> str:
    """
    Build HTML email body with commit details.

    Args:
        commits: List of new commits
        owner: Repository owner
        repo: Repository name
        branch: Branch name
        path: File path

    Returns:
        HTML email body
    """
    commit_count = len(commits)
    file_url = f"https://github.com/{owner}/{repo}/blob/{branch}/{path}"

    html_parts = [
        f"<h3>🔔 File Change Notification</h3>",
        f"<p><strong>Repository:</strong> <a href='https://github.com/{owner}/{repo}'>{owner}/{repo}</a></p>",
        f"<p><strong>Branch:</strong> {branch}</p>",
        f"<p><strong>File:</strong> <a href='{file_url}'>{path}</a></p>",
        f"<p><strong>New commits:</strong> {commit_count}</p>",
        "<hr>",
        "<h4>Recent Commits:</h4>",
        "<ul>",
    ]

    for commit in commits:
        sha = commit["sha"][:8]
        author = commit.get("author", {}).get("login", "Unknown")
        message = commit["commit"]["message"].split("\n")[0][:100]
        url = commit["html_url"]

        html_parts.append(
            f"<li>"
            f"<strong><a href='{url}'>{sha}</a></strong> "
            f"by {author}<br>"
            f"<em>{message}</em>"
            f"</li>"
        )

    html_parts.append("</ul>")
    html_parts.append(f"<p><small>Generated by Vercel GitHub Watcher</small></p>")

    return "\n".join(html_parts)


def handler(request, response):
    """
    Vercel serverless function handler.

    Monitors GitHub file changes and sends email notifications.
    Returns JSON response for observability.
    """
    try:
        # Get configuration from environment variables
        owner = os.environ.get("GH_OWNER", "SimplifyJobs")
        repo = os.environ.get("GH_REPO", "New-Grad-Positions")
        branch = os.environ.get("GH_BRANCH", "dev")
        target_path = os.environ.get("GH_TARGET_PATH", "README.md")

        # Build state key for KV storage
        state_key = os.environ.get(
            "STATE_KEY", f"{owner}/{repo}@{branch}:{target_path}"
        )

        # Validate KV configuration early
        if not os.environ.get("KV_REST_API_URL") or not os.environ.get(
            "KV_REST_API_TOKEN"
        ):
            status, headers, body = _json_response(
                500,
                {
                    "ok": False,
                    "error": "KV not configured: KV_REST_API_URL and KV_REST_API_TOKEN required",
                },
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        # Validate SMTP configuration early
        if not os.environ.get("SMTP_USER") or not os.environ.get("SMTP_PASS"):
            status, headers, body = _json_response(
                500,
                {
                    "ok": False,
                    "error": "SMTP not configured: SMTP_USER and SMTP_PASS required",
                },
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        if not os.environ.get("MAIL_TO"):
            status, headers, body = _json_response(
                500, {"ok": False, "error": "SMTP not configured: MAIL_TO required"}
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        # Fetch commits that touched the target file
        try:
            commits = get_commits_touching_file(owner, repo, branch, target_path)
        except urllib.error.HTTPError as e:
            status, headers, body = _json_response(
                500, {"ok": False, "error": f"GitHub API error: {e.code} {e.reason}"}
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body
        except Exception as e:
            status, headers, body = _json_response(
                500, {"ok": False, "error": f"Failed to fetch commits: {str(e)}"}
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        # Handle case where no commits found
        if not commits:
            status, headers, body = _json_response(
                200,
                {
                    "ok": True,
                    "message": "no commits found",
                    "repo": f"{owner}/{repo}",
                    "branch": branch,
                    "path": target_path,
                },
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        latest_sha = commits[0]["sha"]
        latest_short = latest_sha[:8]

        # Get last seen SHA from KV store
        try:
            last_seen = kv_get(state_key)
        except Exception as e:
            status, headers, body = _json_response(
                500, {"ok": False, "error": f"KV read error: {str(e)}"}
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        # Check if there are new commits
        if last_seen == latest_sha:
            status, headers, body = _json_response(
                200,
                {
                    "ok": True,
                    "changed": False,
                    "sha": latest_short,
                    "repo": f"{owner}/{repo}",
                    "branch": branch,
                    "path": target_path,
                },
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        # Find new commits (those after last_seen)
        new_commits = []
        for commit in commits:
            if commit["sha"] == last_seen:
                break
            new_commits.append(commit)

        # If no new commits found but SHA differs, take all commits
        if not new_commits and last_seen:
            new_commits = commits[:5]  # Limit to recent commits for email
        elif not new_commits:
            new_commits = commits[:1]  # First run, just show latest

        # Build and send email notification
        try:
            subject = f"[GitHub] {target_path} changed in {owner}/{repo}@{branch}"
            body = build_email_body(new_commits, owner, repo, branch, target_path)
            send_email(subject, body)
        except Exception as e:
            status, headers, body = _json_response(
                500, {"ok": False, "error": f"Email send failed: {str(e)}"}
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        # Update KV store with latest SHA
        try:
            kv_set(state_key, latest_sha)
        except Exception as e:
            status, headers, body = _json_response(
                500, {"ok": False, "error": f"KV write error: {str(e)}"}
            )
            response.status_code = status
            for key, value in headers.items():
                response.headers[key] = value
            return body

        # Return success response
        status, headers, body = _json_response(
            200,
            {
                "ok": True,
                "changed": True,
                "latest": latest_short,
                "new_commits": len(new_commits),
                "repo": f"{owner}/{repo}",
                "branch": branch,
                "path": target_path,
            },
        )
        response.status_code = status
        for key, value in headers.items():
            response.headers[key] = value
        return body

    except Exception as e:
        # Catch-all error handler
        status, headers, body = _json_response(
            500, {"ok": False, "error": f"Unexpected error: {str(e)}"}
        )
        response.status_code = status
        for key, value in headers.items():
            response.headers[key] = value
        return body
