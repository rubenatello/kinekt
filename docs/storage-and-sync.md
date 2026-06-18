# Storage, Hosting, And Sync

Kinekt is local-first. It does not require a hosted service for the public beta.

## Default Storage

For each workspace, Kinekt stores its local database under:

```text
<workspace>/.kinekt/kinekt.sqlite3
```

Optional ChromaDB data is stored under:

```text
<workspace>/.kinekt/chroma/
```

This keeps context close to the code and makes the behavior easy to inspect.

## Should `.kinekt/` Be Committed?

Usually, no.

Recommended default:

```gitignore
.kinekt/
```

Reasons:

- It may contain indexed source snippets and notes.
- It can be regenerated with `kinekt ingest`.
- It may grow over time.
- Developers often have different local context needs.

Teams can choose to back up or sync `.kinekt/` through their own secure storage, but Kinekt does not require that.

## Moving Machines

For public beta, the safest path is to reinstall Kinekt and re-index:

```bash
kinekt init /path/to/workspace
kinekt ingest /path/to/workspace
```

If a user wants to preserve sessions and indexed state, they can copy `.kinekt/` to the same workspace path on the new machine. Treat it as potentially sensitive local developer data.

## Codespaces And Cloud Code Editors

Kinekt can run anywhere Python 3.11+ and local filesystem access are available:

- GitHub Codespaces
- Dev containers
- Cloud VMs
- Remote SSH workspaces
- Local laptops and desktops

In cloud editors, "local-first" means local to that development environment. Data is stored in the workspace/container filesystem unless the user mounts or syncs it elsewhere.

Recommended cloud workflow:

1. Install Kinekt inside the dev environment.
2. Run `kinekt init` and `kinekt ingest` in the mounted workspace.
3. Keep `.kinekt/` out of git unless the team explicitly accepts the data exposure.
4. Re-ingest after rebuilding ephemeral containers.

## Hosted Storage Roadmap

Hosted sync is intentionally out of scope for public beta.

Future options could include encrypted user-managed sync, remote vector storage, or team context sharing. Those features require stronger security, authentication, encryption, tenancy, and deletion guarantees before they should be offered.
