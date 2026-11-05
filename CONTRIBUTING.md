# Listing a plugin

You wrote a jaira plugin and want people to find it. Getting it into the
catalogue is one pull request; every release after that needs none.

## Before you open the pull request

Your plugin's repository must already have:

1. **A public GitHub repository that you own** — under your own account, or
   under an organisation where your membership is
   [public](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-your-membership-in-organizations/publicizing-or-hiding-organization-membership).
   The pull request must be opened by that account.
2. **`jaira-plugin.json`** at the root of the default branch, matching
   [`schema/jaira-plugin.schema.json`](schema/jaira-plugin.schema.json).
3. **A release `v<version>`**, where `<version>` is the `version` in that
   manifest, with these assets:
   - `jaira-<id>_linux_amd64`, `jaira-<id>_linux_arm64`
   - `jaira-<id>_darwin_amd64`, `jaira-<id>_darwin_arm64`
   - `jaira-<id>_windows_amd64.exe`, `jaira-<id>_windows_arm64.exe`
   - `checksums.txt` with a line for each of them

[jaira-plugin-template](https://github.com/panda-bobr/jaira-plugin-template)
builds all of this — press **Use this template**, do not fork it.

## The pull request

1. Fork this repository.
2. Append one entry to the array in `plugins.json`:

   ```json
   {
     "id": "jira",
     "name": "Jira",
     "author": "Jane Doe",
     "description": "Mirror Jira issues into tickets and back.",
     "repo": "https://github.com/jane/jaira-jira"
   }
   ```

   | Field | Rule |
   |---|---|
   | `id` | lower-case letters, digits and single dashes, starting with a letter; the same as `id` in your `jaira-plugin.json`; not taken; must not contain `jaira`; must not be a jaira command (`list`, `move`, `web`, …) |
   | `name` | what a person reads, up to 80 characters |
   | `author` | you, up to 80 characters |
   | `description` | one line, up to 200 characters |
   | `repo` | `https://github.com/<owner>/<repo>` — where the releases are |

   All five are required, and nothing else is allowed. The full rules are in
   [`schema/plugins-entry.schema.json`](schema/plugins-entry.schema.json).
3. Change nothing but `plugins.json`, and leave the other entries alone.
4. Open the pull request against `main`.

## What the check tells you

Every push to the pull request runs `check-catalog`. It looks at the entries
you add or change and answers in a comment on the pull request, with every
problem it found at once:

- the entry matches the schema, and the id is free and allowed
- the repository exists, is public, and is yours
- `jaira-plugin.json` matches its schema and carries the same id
- the release `v<version>` exists with all six binaries and `checksums.txt`,
  and `checksums.txt` lists each binary

Fix what it names and push again. When it passes, a maintainer looks at the
plugin and merges the entry — the check is the minimum, not the decision.

## After it is listed

- **A new version** is a new release in your repository. No pull request.
- **A changed name, description or repository** is a pull request that
  changes your entry; the same check runs.
- **Removing a plugin** is done by a maintainer; open an issue.

A plugin that does more than its `capabilities` declare is removed from the
catalogue.
