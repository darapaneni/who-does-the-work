"""Where participant responses go.

GitHubCSV appends rows to one CSV file in a GitHub repository through the
GitHub REST "contents" API (GET the file and its sha, append, PUT it back).
If two participants submit at the same moment, GitHub rejects the second write
(409/422: stale sha); we re-read the file and retry with jitter, so no row is lost.

LocalCSV is the fallback when no GitHub settings are configured (local testing).
Every submission is also appended to a local backup file.
"""
from __future__ import annotations

import base64
import csv
import io
import random
import subprocess
import threading
import time
from pathlib import Path

import requests

API = "https://api.github.com"
COLUMNS = [
    "submitted_utc", "submission_id", "app_version", "session_code", "participant", "role", "ai_experience",
    "round", "eps_multiplier", "rho_multiplier", "task_id", "task_name", "plan", "codified", "allocation",
    "n_human", "n_agent", "p_correct", "value", "value_full_autonomy", "value_all_human", "value_split",
    "best_reference", "gain_over_best_reference", "optimal_value", "share_of_optimum", "is_split_design",
    "seconds_on_task", "edits", "reflection",
]
# Seminar feedback on agent access: long format, one row per answer.
FEEDBACK_COLUMNS = [
    "submitted_utc", "submission_id", "app_version", "session_code", "participant", "role", "ai_experience",
    "question_id", "question", "item", "answer",
]


def sanitize(v):
    """Neutralise spreadsheet formula injection and keep text on one line."""
    if isinstance(v, str):
        v = v.replace("\r", " ").replace("\n", " ").strip()[:2000]
        if v[:1] in ("=", "+", "-", "@", "\t"):
            v = "'" + v
    return v


def rows_to_csv(rows: list[dict], header: bool, columns: list[str] | None = None) -> str:
    columns = columns or COLUMNS
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    if header:
        w.writeheader()
    for r in rows:
        w.writerow({k: sanitize(r.get(k, "")) for k in columns})
    return buf.getvalue()


_FILE_LOCK = threading.Lock()   # one Streamlit server = one process; participants are threads


class LocalCSV:
    def __init__(self, path: str | Path, columns: list[str] | None = None):
        self.path = Path(path).resolve()
        self.columns = columns or COLUMNS
        self.label = f"local file {self.path}"

    def append(self, rows: list[dict]) -> str:
        with _FILE_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            new = not self.path.exists() or self.path.stat().st_size == 0
            with self.path.open("a", encoding="utf-8", newline="") as f:
                f.write(rows_to_csv(rows, header=new, columns=self.columns))
        return f"Saved {len(rows)} rows to {self.label}."

    def read(self) -> str:
        with _FILE_LOCK:
            return self.path.read_text(encoding="utf-8") if self.path.exists() else ""


class LocalGitCSV(LocalCSV):
    """A CSV inside a local git clone of your repo. After each submission the file is committed
    (and, if asked, pushed) by a background thread, so participants never wait for git."""

    def __init__(self, path, commit: bool = True, push: bool = False, remote: str = "origin",
                 columns: list[str] | None = None):
        super().__init__(path, columns)
        self.commit, self.push, self.remote = commit, push, remote
        self.repo = self._repo_root()
        self.last_git_message = "no git activity yet"
        if self.repo is None:
            self.commit = self.push = False
            self.last_git_message = f"{self.path.parent} is not inside a git repository; saving the CSV only"

    def _git(self, *args, check=True):
        return subprocess.run(["git", "-C", str(self.repo or self.path.parent), *args], capture_output=True,
                              text=True, timeout=120, check=check)

    def _repo_root(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["git", "-C", str(self.path.parent), "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True, timeout=20)
            return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
        except (OSError, subprocess.SubprocessError):
            return None                      # git not installed

    def append(self, rows):
        msg = super().append(rows)
        if self.commit:
            who = str(rows[0].get("participant", ""))[:40]
            threading.Thread(target=self.sync, args=(f"exercise: {len(rows)} response rows ({who})",),
                             daemon=True).start()
        return msg

    def sync(self, message: str = "exercise: responses") -> str:
        """Commit the CSV (and push if enabled). Safe to call from the facilitator page."""
        if self.repo is None:
            return self.last_git_message
        with _FILE_LOCK:
            try:
                rel = str(self.path.relative_to(self.repo))
                self._git("add", rel)
                if self._git("diff", "--cached", "--quiet", "--", rel, check=False).returncode == 0:
                    out = "nothing new to commit"
                else:
                    self._git("commit", "-m", message, "--", rel)
                    out = "committed"
                if self.push:
                    self._git("pull", "--rebase", "--autostash", self.remote, check=False)
                    p = self._git("push", self.remote, "HEAD", check=False)
                    out += "; pushed" if p.returncode == 0 else f"; push failed: {p.stderr.strip()[:200]}"
            except subprocess.CalledProcessError as e:
                out = f"git error: {(e.stderr or e.stdout or '').strip()[:200]}"
            except (OSError, subprocess.SubprocessError) as e:
                out = f"git error: {e}"
        self.last_git_message = f"{time.strftime('%H:%M:%S')} {out}"
        return self.last_git_message


class GitHubCSV:
    def __init__(self, token: str, repo: str, path: str, branch: str = "main", session: requests.Session | None = None,
                 max_attempts: int = 8, columns: list[str] | None = None):
        self.columns = columns or COLUMNS
        if "/" not in repo:
            raise ValueError("repo must be 'owner/name'")
        self.repo, self.path, self.branch = repo, path.lstrip("/"), branch
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})
        self.max_attempts = max_attempts
        self.label = f"github.com/{repo}/blob/{branch}/{self.path}"

    def ensure_branch(self) -> None:
        """Create the data branch from the default branch the first time (keeps response commits off the
        branch the app is deployed from, so Streamlit Cloud does not redeploy on every submission)."""
        if getattr(self, "_branch_ok", False):
            return
        r = self.http.get(f"{API}/repos/{self.repo}/git/ref/heads/{self.branch}", timeout=20)
        if r.status_code == 404:
            info = self.http.get(f"{API}/repos/{self.repo}", timeout=20)
            info.raise_for_status()
            default = info.json()["default_branch"]
            head = self.http.get(f"{API}/repos/{self.repo}/git/ref/heads/{default}", timeout=20)
            head.raise_for_status()
            c = self.http.post(f"{API}/repos/{self.repo}/git/refs", timeout=20,
                               json={"ref": f"refs/heads/{self.branch}", "sha": head.json()["object"]["sha"]})
            if c.status_code not in (201, 422):      # 422: someone else created it meanwhile
                c.raise_for_status()
        else:
            r.raise_for_status()
        self._branch_ok = True

    @property
    def url(self) -> str:
        return f"{API}/repos/{self.repo}/contents/{self.path}"

    def _get(self) -> tuple[str, str | None]:
        r = self.http.get(self.url, params={"ref": self.branch}, timeout=20)
        if r.status_code == 404:
            return "", None
        r.raise_for_status()
        j = r.json()
        if j.get("encoding") == "base64" and j.get("content") is not None and j.get("size", 0) <= 900_000:
            return base64.b64decode(j["content"]).decode("utf-8"), j["sha"]
        # files above ~1 MB: the contents API returns no content; fetch the raw blob instead
        raw = self.http.get(self.url, params={"ref": self.branch},
                            headers={"Accept": "application/vnd.github.raw+json"}, timeout=30)
        raw.raise_for_status()
        return raw.text, j["sha"]

    def read(self) -> str:
        return self._get()[0]

    def append(self, rows: list[dict]) -> str:
        self.ensure_branch()
        last = None
        for attempt in range(self.max_attempts):
            text, sha = self._get()
            if text and not text.endswith("\n"):
                text += "\n"
            body = text + rows_to_csv(rows, header=(text == ""), columns=self.columns)
            payload = {"message": f"exercise: {len(rows)} response rows ({rows[0].get('participant', '')[:40]})",
                       "content": base64.b64encode(body.encode("utf-8")).decode("ascii"), "branch": self.branch}
            if sha:
                payload["sha"] = sha
            r = self.http.put(self.url, json=payload, timeout=30)
            if r.status_code in (200, 201):
                return f"Saved {len(rows)} rows to {self.label}."
            if r.status_code in (409, 422):         # someone else wrote first: re-read and retry
                last = r.text
                time.sleep(min(8.0, 0.4 * 2 ** attempt) * (0.5 + random.random()))
                continue
            r.raise_for_status()
        raise RuntimeError(f"Could not save after {self.max_attempts} attempts (last response: {last})")


class Mirrored:
    """Primary store plus a local backup copy of every submission."""

    def __init__(self, primary, backup: LocalCSV):
        self.primary, self.backup = primary, backup
        self.label = primary.label

    def append(self, rows):
        self.backup.append(rows)
        return self.primary.append(rows)

    def read(self):
        return self.primary.read()


def _sibling(path: str, filename: str | None) -> str:
    if not filename:
        return path
    p = path.rsplit("/", 1)
    return (p[0] + "/" + filename) if len(p) == 2 else filename


def from_settings(secrets, base_dir: Path, local: dict | None = None, filename: str | None = None,
                  columns: list[str] | None = None):
    """GitHub API mode if a [github] token is configured; otherwise local mode (the default on localhost):
    the CSV is written to `csv_path` (relative to the app folder) and optionally committed/pushed with git.
    `filename` stores a second file (e.g. feedback.csv) next to the responses file, with its own `columns`."""
    gh = dict(secrets.get("github", {})) if secrets else {}
    if gh.get("token") and gh.get("repo"):
        backup = LocalCSV(base_dir / "data" / ("backup_" + (filename or "responses.csv")), columns)
        primary = GitHubCSV(gh["token"], gh["repo"], _sibling(gh.get("path", "data/exercise/responses.csv"), filename),
                            gh.get("branch", "exercise-data"), columns=columns)
        return Mirrored(primary, backup), "github"
    local = local or {}
    path = Path(_sibling(str(local.get("csv_path", "../data/exercise/responses.csv")).replace("\\", "/"), filename))
    if not path.is_absolute():
        path = base_dir / path
    if local.get("git_commit", False) or local.get("git_push", False):
        return LocalGitCSV(path, commit=True, push=bool(local.get("git_push", False)),
                           remote=local.get("git_remote", "origin"), columns=columns), "local-git"
    return LocalCSV(path, columns), "local"
