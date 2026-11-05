# jaira-releases

The catalogue of jaira plugins.

[jaira](https://github.com/BeMuCa/jaira) is a git-synced kanban board for
the tasks agents generate in a repository. A plugin is a program of its own,
`jaira-<id>`, written and released by its author in a repository of their own.
This repository stores no plugin code. It holds one list: which plugins exist
and where they live.

## What is here

| Path | What it is |
|---|---|
| `plugins.json` | the catalogue: an array of entries `{id, name, author, description, repo}` |
| `schema/plugins-entry.schema.json` | the schema of one entry |
| `schema/jaira-plugin.schema.json` | the schema of a plugin's manifest, `jaira-plugin.json` |
| `CONTRIBUTING.md` | how to get a plugin listed |
| `.github/workflows/check-catalog.yml` | the check every pull request runs |

The standard a plugin follows — invocation, environment, events, web pages,
exit codes, manifest, releases — is
[`docs/PLUGINS.md`](https://github.com/BeMuCa/jaira/blob/master/docs/PLUGINS.md)
in the jaira repository.

## The catalogue is a whitelist

A plugin is listed because a maintainer merged its entry, not because it
exists. An entry names a repository, not a version: once listed, every new
release of the plugin is available without another pull request.

## The schemas are copies

`schema/` holds copies of `docs/schema/*.json` from the jaira repository. When
jaira changes a schema, the copy here is updated in the same round; the check
reads only the copy.

## Later

A website with registration will replace the pull request and write into
`plugins.json` by a bot. The format of `plugins.json` stays the same, so
nothing that reads it has to change.
