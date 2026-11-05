"""Tests for check_catalog.py, with GitHub replaced by a dictionary.

Run: python -m unittest discover -s .github/scripts
"""

import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_catalog as cc  # noqa: E402

API = cc.API
REPO = "https://github.com/jane/jaira-jira"

ENTRY = {
    "id": "jira",
    "name": "Jira",
    "author": "Jane Doe",
    "description": "Mirror Jira issues into tickets and back.",
    "repo": REPO,
}

MANIFEST = {
    "id": "jira",
    "name": "Jira",
    "version": "1.2.0",
    "minJairaVersion": "0.6.0",
    "commands": [{"name": "pull", "summary": "pull issues"}],
    "capabilities": ["read", "write"],
}

BINARIES = [
    f"jaira-jira_{o}_{a}" + (".exe" if o == "windows" else "")
    for o in ("linux", "darwin", "windows")
    for a in ("amd64", "arm64")
]
CHECKSUMS_URL = "https://github.com/jane/jaira-jira/releases/download/v1.2.0/checksums.txt"


def github(owner_type="User", owner="jane", manifest=MANIFEST, assets=None, checksums=None, public_members=()):
    """A fake GitHub: URL -> bytes, missing URL -> NotFound."""
    if assets is None:
        assets = BINARIES + ["checksums.txt"]
    if checksums is None:
        checksums = "".join(f"{'0' * 64}  {b}\n" for b in BINARIES)
    pages = {
        f"{API}/repos/jane/jaira-jira": {
            "private": False,
            "default_branch": "main",
            "owner": {"login": owner, "type": owner_type},
        },
        f"{API}/repos/jane/jaira-jira/releases/tags/v1.2.0": {
            "assets": [
                {"name": n, "browser_download_url": CHECKSUMS_URL if n == "checksums.txt" else "x"}
                for n in assets
            ]
        },
    }
    if manifest is not None:
        pages[f"{API}/repos/jane/jaira-jira/contents/jaira-plugin.json?ref=main"] = {
            "content": base64.b64encode(json.dumps(manifest).encode()).decode()
        }
    raw = {CHECKSUMS_URL: checksums.encode()}
    for m in public_members:
        raw[f"{API}/orgs/{owner}/public_members/{m}"] = b""

    def fetch(url):
        if url in raw:
            return raw[url]
        if url in pages:
            return json.dumps(pages[url]).encode()
        raise cc.NotFound(url)

    return fetch


def run(head, base=(), author="jane", changed=("plugins.json",), fetch=None):
    return cc.run(json.dumps(list(base)), json.dumps(list(head)), author, list(changed), fetch or github())


class CatalogCheck(unittest.TestCase):
    def test_complete_entry_passes(self):
        self.assertEqual(run([ENTRY]), [])

    def test_empty_catalogue_passes(self):
        self.assertEqual(run([]), [])

    def test_duplicate_id_is_refused(self):
        listed = dict(ENTRY, name="Jira, listed first")
        problems = run([listed, ENTRY], base=[listed])
        self.assertTrue(any("the id is taken" in p for p in problems), problems)

    def test_duplicate_is_checked_once(self):
        problems = run([ENTRY, dict(ENTRY, name="Jira again")], fetch=github(assets=BINARIES))
        self.assertEqual(sum("no `checksums.txt`" in p for p in problems), 1, problems)

    def test_id_with_jaira_is_refused(self):
        problems = run([dict(ENTRY, id="jaira-jira")])
        self.assertTrue(any("must not contain `jaira`" in p for p in problems), problems)

    def test_id_naming_a_command_is_refused(self):
        problems = run([dict(ENTRY, id="move")])
        self.assertTrue(any("is a jaira command" in p for p in problems), problems)

    def test_schema_violation_is_refused(self):
        bad = dict(ENTRY)
        del bad["author"]
        problems = run([bad])
        self.assertTrue(any("'author' is a required property" in p for p in problems), problems)

    def test_not_json_is_refused(self):
        problems = cc.run("[]", "[{", "jane", ["plugins.json"], github())
        self.assertTrue(any("not valid JSON" in p for p in problems), problems)

    def test_other_files_are_refused(self):
        problems = run([ENTRY], changed=["plugins.json", ".github/scripts/check_catalog.py"])
        self.assertTrue(any("changes `plugins.json` only" in p for p in problems), problems)

    def test_removing_an_entry_is_refused(self):
        problems = run([], base=[ENTRY])
        self.assertTrue(any("removes it" in p for p in problems), problems)

    def test_unchanged_entries_are_not_fetched(self):
        def no_network(url):
            raise AssertionError(f"fetched {url}")

        self.assertEqual(run([ENTRY], base=[ENTRY], fetch=no_network), [])

    def test_missing_repo_is_refused(self):
        problems = run([dict(ENTRY, repo="https://github.com/jane/nothing")])
        self.assertTrue(any("does not exist or is not public" in p for p in problems), problems)

    def test_foreign_author_is_refused(self):
        problems = run([ENTRY], author="mallory")
        self.assertTrue(any("only the owner can list it" in p for p in problems), problems)

    def test_org_public_member_passes(self):
        fetch = github(owner_type="Organization", owner="acme", public_members=["jane"])
        self.assertEqual(run([ENTRY], fetch=fetch), [])

    def test_org_non_member_is_refused(self):
        fetch = github(owner_type="Organization", owner="acme")
        problems = run([ENTRY], fetch=fetch)
        self.assertTrue(any("not a public member of `acme`" in p for p in problems), problems)

    def test_missing_manifest_is_refused(self):
        problems = run([ENTRY], fetch=github(manifest=None))
        self.assertTrue(any("no `jaira-plugin.json`" in p for p in problems), problems)

    def test_manifest_id_mismatch_is_refused(self):
        problems = run([ENTRY], fetch=github(manifest=dict(MANIFEST, id="youtrack")))
        self.assertTrue(any("they must match" in p for p in problems), problems)

    def test_invalid_manifest_is_refused(self):
        problems = run([ENTRY], fetch=github(manifest=dict(MANIFEST, capabilities=["root"])))
        self.assertTrue(any("jaira-plugin.json" in p and "root" in p for p in problems), problems)

    def test_missing_release_is_refused(self):
        problems = run([ENTRY], fetch=github(manifest=dict(MANIFEST, version="2.0.0")))
        self.assertTrue(any("no release `v2.0.0`" in p for p in problems), problems)

    def test_missing_checksums_is_refused(self):
        problems = run([ENTRY], fetch=github(assets=BINARIES))
        self.assertTrue(any("no `checksums.txt`" in p for p in problems), problems)

    def test_missing_binary_is_refused(self):
        problems = run([ENTRY], fetch=github(assets=BINARIES[1:] + ["checksums.txt"]))
        self.assertTrue(any("no binary `jaira-jira_linux_amd64`" in p for p in problems), problems)

    def test_binary_missing_from_checksums_is_refused(self):
        problems = run([ENTRY], fetch=github(checksums=f"{'0' * 64}  {BINARIES[0]}\n"))
        self.assertTrue(any("has no line for `jaira-jira_darwin_amd64`" in p for p in problems), problems)

    def test_github_error_is_reported_not_raised(self):
        import urllib.error

        def broken(url):
            raise urllib.error.HTTPError(url, 503, "unavailable", None, None)

        problems = run([ENTRY], fetch=broken)
        self.assertTrue(any("GitHub answered 503" in p and "re-run" in p for p in problems), problems)

    def test_event_is_a_free_id(self):
        self.assertNotIn("event", cc.JAIRA_COMMANDS)

    def test_report_lists_problems(self):
        text = cc.report(["entry `x`: broken"])
        self.assertIn("failed", text)
        self.assertIn("- entry `x`: broken", text)
        self.assertIn("passed", cc.report([]))


if __name__ == "__main__":
    unittest.main()
