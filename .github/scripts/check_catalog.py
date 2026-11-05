#!/usr/bin/env python3
"""Check a pull request against the jaira plugin catalogue.

Reads plugins.json as it is on main and as the pull request leaves it, and
checks every entry the pull request adds or changes:

- the file is a JSON array of entries that match schema/plugins-entry.schema.json
- every id is unique, does not contain "jaira" and does not name a jaira command
- the repository exists on GitHub and is public
- the pull request's author owns the repository (or is a public member of the
  organisation that does); changing `repo` or `author` of a listed id needs
  the owner of the listed repository as well
- jaira-plugin.json on the repository's default branch matches
  schema/jaira-plugin.schema.json and carries the entry's id
- a release v<version> exists, with a binary for linux, darwin and windows on
  amd64 and arm64, and a checksums.txt that lists every one of them

The pull request's own code is never run: this script and the schemas come
from main, plugins.json from the pull request is read as data.

Usage:
  check_catalog.py --base <plugins.json on main> --head <plugins.json of the PR>
                   --author <login> [--changed-files <file>] [--report <file>]

Exit 0 when the pull request passes, 1 when it does not; the problems are
printed as a Markdown list and, with --report, written to that file.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
ENTRY_SCHEMA = ROOT / "schema" / "plugins-entry.schema.json"
MANIFEST_SCHEMA = ROOT / "schema" / "jaira-plugin.schema.json"
CATALOG = "plugins.json"

# jaira's own commands win over a plugin's id: `jaira <id>` could never reach
# a plugin that is called like one of them. The first block is `jaira --help`
# of 0.5; the second holds names jaira keeps for itself.
JAIRA_COMMANDS = frozenset(
    """
    archive board boards checkpoint claim completion create delete dod epic
    fetch help hook init json lanes links list logbook milestone move next
    note projects pull reject release resolve restore resume roles self
    sessions set share show snapshot sync-tasks tag tags tasks update validate
    web whoami
    plugin plugins install uninstall version
    """.split()
)

PLATFORMS = [
    (os_, arch) for os_ in ("linux", "darwin", "windows") for arch in ("amd64", "arm64")
]

API = "https://api.github.com"


class NotFound(Exception):
    pass


Fetch = Callable[[str], bytes]


def github_fetch(token: Optional[str]) -> Fetch:
    """Return a function that GETs a URL, raising NotFound on 404."""

    def fetch(url: str) -> bytes:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "jaira-releases-catalog-check")
        if url.startswith(API):
            req.add_header("Accept", "application/vnd.github+json")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound(url) from e
            raise

    return fetch


def get_json(fetch: Fetch, url: str):
    return json.loads(fetch(url))


def load_schema(path: Path) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(json.loads(path.read_text()))


def schema_errors(validator, doc) -> list[str]:
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(top level)"
        out.append(f"`{where}`: {err.message}")
    return out


def check_file_shape(head_text: str, entry_schema) -> tuple[list, list[str]]:
    """Parse plugins.json and check it against the entry schema."""
    try:
        doc = json.loads(head_text)
    except json.JSONDecodeError as e:
        return [], [f"`{CATALOG}` is not valid JSON: {e}"]
    if not isinstance(doc, list):
        return [], [f"`{CATALOG}` must be a JSON array of entries"]
    problems = []
    for i, entry in enumerate(doc):
        label = entry.get("id", f"#{i}") if isinstance(entry, dict) else f"#{i}"
        for msg in schema_errors(entry_schema, entry):
            problems.append(f"entry `{label}`: {msg}")
    return doc, problems


def check_ids(entries: list) -> list[str]:
    problems = []
    seen: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        id_ = entry["id"]
        seen[id_] = seen.get(id_, 0) + 1
        if "jaira" in id_:
            problems.append(f"entry `{id_}`: the id must not contain `jaira`; the program is already called `jaira-{id_}`")
        if id_ in JAIRA_COMMANDS:
            problems.append(f"entry `{id_}`: `{id_}` is a jaira command, so `jaira {id_}` could never reach the plugin")
    for id_, n in seen.items():
        if n > 1:
            problems.append(f"entry `{id_}`: the id is taken — it appears {n} times in `{CATALOG}`")
    return problems


def check_owner(fetch: Fetch, owner_info: dict, author: str) -> Optional[str]:
    login = owner_info.get("login", "")
    if login.lower() == author.lower():
        return None
    if owner_info.get("type") == "Organization":
        try:
            fetch(f"{API}/orgs/{login}/public_members/{author}")
            return None
        except NotFound:
            return (
                f"the pull request's author `{author}` is not a public member of `{login}`, "
                f"which owns the repository; make your membership public or let an owner open the pull request"
            )
    return f"the repository belongs to `{login}`, but the pull request was opened by `{author}`; only the owner can list it"


def check_release(fetch: Fetch, owner: str, repo: str, id_: str, version: str) -> list[str]:
    tag = f"v{version}"
    try:
        rel = get_json(fetch, f"{API}/repos/{owner}/{repo}/releases/tags/{tag}")
    except NotFound:
        return [f"no release `{tag}`; `version` in jaira-plugin.json is `{version}`, so the release tag must be `{tag}`"]
    assets = {a["name"]: a for a in rel.get("assets", [])}
    problems = []
    binaries = []
    for os_, arch in PLATFORMS:
        name = f"jaira-{id_}_{os_}_{arch}"
        if os_ == "windows" and name + ".exe" in assets:
            name += ".exe"
        if name not in assets:
            problems.append(f"release `{tag}` has no binary `{name}`" + (" (or `.exe`)" if os_ == "windows" else ""))
        else:
            binaries.append(name)
    if "checksums.txt" not in assets:
        problems.append(f"release `{tag}` has no `checksums.txt`")
        return problems
    try:
        text = fetch(assets["checksums.txt"]["browser_download_url"]).decode("utf-8", "replace")
    except (NotFound, urllib.error.URLError) as e:
        return problems + [f"`checksums.txt` of release `{tag}` could not be read: {e}"]
    listed = {line.split()[-1].lstrip("*") for line in text.splitlines() if len(line.split()) >= 2}
    for name in binaries:
        if name not in listed:
            problems.append(f"`checksums.txt` of release `{tag}` has no line for `{name}`")
    return problems


def check_entry(fetch: Fetch, entry: dict, author: str, manifest_schema) -> list[str]:
    id_ = entry["id"]
    owner, repo = entry["repo"].split("/")[-2:]  # the schema pins https://github.com/<owner>/<repo>
    p = lambda msg: f"entry `{id_}`: {msg}"
    try:
        info = get_json(fetch, f"{API}/repos/{owner}/{repo}")
    except NotFound:
        return [p(f"the repository {entry['repo']} does not exist or is not public")]
    if info.get("private"):
        return [p(f"the repository {entry['repo']} is private; the catalogue lists public repositories only")]

    problems = []
    owner_problem = check_owner(fetch, info.get("owner", {}), author)
    if owner_problem:
        problems.append(p(owner_problem))

    branch = info.get("default_branch", "main")
    try:
        content = get_json(fetch, f"{API}/repos/{owner}/{repo}/contents/jaira-plugin.json?ref={branch}")
        manifest = json.loads(base64.b64decode(content["content"]))
    except NotFound:
        return problems + [p(f"no `jaira-plugin.json` at the root of `{branch}`")]
    except (ValueError, KeyError) as e:
        return problems + [p(f"`jaira-plugin.json` on `{branch}` is not valid JSON: {e}")]

    errs = schema_errors(manifest_schema, manifest)
    if errs:
        return problems + [p(f"`jaira-plugin.json` on `{branch}`: {msg}") for msg in errs]
    if manifest["id"] != id_:
        problems.append(p(f"`jaira-plugin.json` says id `{manifest['id']}`, the entry says `{id_}`; they must match"))
        return problems

    problems += [p(msg) for msg in check_release(fetch, owner, repo, id_, manifest["version"])]
    return problems


def check_takeover(fetch: Fetch, old: dict, new: dict, author: str) -> list[str]:
    """A listed entry changes hands only when the author owns the old repository too.

    check_entry already requires the author to own the new one; without this,
    anybody could point a listed id at a repository of their own.
    """
    if old["repo"] == new["repo"] and old["author"] == new["author"]:
        return []
    id_ = new["id"]
    owner, repo = old["repo"].split("/")[-2:]
    try:
        info = get_json(fetch, f"{API}/repos/{owner}/{repo}")
    except NotFound:
        return [f"entry `{id_}`: the listed repository {old['repo']} no longer exists, so nobody can prove they own it; ask a maintainer to change the entry"]
    if check_owner(fetch, info.get("owner", {}), author):
        return [
            f"entry `{id_}`: changing `repo` or `author` of a listed plugin needs the owner of the listed repository {old['repo']} "
            f"as well as of the new one; `{author}` does not own it"
        ]
    return []


def run(base_text: str, head_text: str, author: str, changed_files: list[str], fetch: Fetch) -> list[str]:
    problems = []
    others = [f for f in changed_files if f and f != CATALOG]
    if others:
        problems.append(
            "a catalogue pull request changes `plugins.json` only; it also changes "
            + ", ".join(f"`{f}`" for f in others)
        )

    entry_schema = load_schema(ENTRY_SCHEMA)
    head, shape = check_file_shape(head_text, entry_schema)
    problems += shape
    if shape:
        return problems
    problems += check_ids(head)
    try:
        base = json.loads(base_text)
    except json.JSONDecodeError:
        base = []
    head_ids = {e.get("id") for e in head if isinstance(e, dict)}
    for e in base:
        if isinstance(e, dict) and e.get("id") not in head_ids:
            problems.append(f"entry `{e.get('id')}`: the pull request removes it; a maintainer removes entries, not a pull request")

    manifest_schema = load_schema(MANIFEST_SCHEMA)
    listed = {e.get("id"): e for e in base if isinstance(e, dict)}
    checked = set()
    for entry in (e for e in head if listed.get(e["id"]) != e):  # new or changed entries only
        if entry["id"] in checked:  # a second entry with this id is already reported by check_ids
            continue
        checked.add(entry["id"])
        try:
            if entry["id"] in listed:
                problems += check_takeover(fetch, listed[entry["id"]], entry, author)
            problems += check_entry(fetch, entry, author, manifest_schema)
        except urllib.error.HTTPError as e:
            problems.append(f"entry `{entry['id']}`: GitHub answered {e.code} for {e.url}; this is not your entry's fault — re-run the check")
        except urllib.error.URLError as e:
            problems.append(f"entry `{entry['id']}`: GitHub could not be reached ({e.reason}); re-run the check")
    return problems


def report(problems: list[str]) -> str:
    if not problems:
        return "### Catalogue check passed\n\nEvery entry this pull request adds or changes is complete. A maintainer will look at it next.\n"
    lines = ["### Catalogue check failed", "", "Fix these and push again; the check runs on every push.", ""]
    lines += [f"- {msg}" for msg in problems]
    lines += ["", "What an entry needs is in CONTRIBUTING.md."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--changed-files")
    ap.add_argument("--report")
    args = ap.parse_args(argv)

    changed = Path(args.changed_files).read_text().split("\n") if args.changed_files else []
    problems = run(
        Path(args.base).read_text(),
        Path(args.head).read_text(),
        args.author,
        changed,
        github_fetch(os.environ.get("GITHUB_TOKEN")),
    )
    text = report(problems)
    print(text)
    if args.report:
        Path(args.report).write_text(text)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
