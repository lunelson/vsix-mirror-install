# vsix-bridge

Keep a local mirror of your **official VS Code Marketplace** extensions and bulk-install them into VS Code fork IDEs (Cursor, Anti-Gravity, etc.) using each IDE’s CLI.

Many fork IDEs can only install from unofficial extension catalogs (e.g. OpenVSIX), which may lag updates and can include typosquats or low-vetting packages. `vsix-bridge` uses your **local VS Code install as the source of truth**, downloads the matching `.vsix` artifacts from the **Microsoft VS Code Marketplace**, and installs them directly.

## Features

- **Sync based on VS Code**  
  Downloads VSIX files from the Microsoft VS Code Marketplace based on extensions currently installed in `code` (or an optional fixed list). For each target IDE, it saves `.vsix` files into a sibling directory post-fixed by IDE name (e.g. `vsix-cursor`, `vsix-agy`) and selects the **newest engine-compatible** version for that IDE.

- **Bulk install**  
  Installs VSIX files into target IDEs via their CLIs. By default it **updates existing** extensions; use `--force` to install everything (new + updates).

- **Private / local-first**  
  Everything stays local: VSIX files are downloaded to your machine and installed directly via IDE CLIs.

## Prerequisites

- Node.js (LTS recommended)
- Target IDE CLI(s) available in your `PATH` (e.g. `cursor`, `code`, `agy`)
- Internet connection when running `sync`

## Install

### Global install (recommended)

```bash
npm install -g vsix-bridge-cli
````

This provides the executable:

```bash
vsix-bridge
```

### One-off via npx

```bash
npx vsix-bridge-cli --help
```

## Usage

`vsix-bridge` has two main commands:

* `sync` — download/update a local VSIX mirror per IDE
* `install` — bulk-install from the mirror into an IDE

### 1) Sync VSIX files per IDE

By default, `vsix-bridge` knows about two IDE targets:

* `cursor`
* `agy` (Anti-Gravity)

Run:

```bash
vsix-bridge sync
```

Limit to specific IDEs:

```bash
vsix-bridge sync --to cursor
vsix-bridge sync --to agy
```

This will download compatible VSIX files into `vsix-<target>` directories (e.g. `vsix-cursor`) and remove stale ones.

### 2) Bulk-install VSIX files directly

By default, `install` only updates extensions that are already present in the target IDE. Use `--force` to install everything (new extensions + updates). The default VSIX dir is `vsix-<target>`.

```bash
vsix-bridge install --to cursor --dry-run   # see plan
vsix-bridge install --to cursor             # update existing extensions only
vsix-bridge install --to cursor --force     # install everything (new + updates)
```

## How it works (high level)

1. Reads your installed extension list from **VS Code** (`code`) or an explicit list.
2. For each target IDE, determines that IDE’s engine version (or uses a configured value).
3. Queries the **Microsoft VS Code Marketplace** for available versions and picks the newest version whose `engines.vscode` range is compatible.
4. Downloads the `.vsix` into `vsix-<target>/`.
5. Installs using the target IDE’s CLI.

## Troubleshooting

* **Missing extensions**
  If an extension is installed locally but isn’t found in the Microsoft VS Code Marketplace (e.g. private/deprecated), sync will skip it and warn.

* **No compatible version**
  If no version’s `engines.vscode` range accepts a target IDE’s engine version, you’ll get a warning and it won’t appear in that target’s mirror directory.

* **Version parsing quirks**
  Sorting prefers semantic versions, with a string fallback. Extensions using non-semver version strings may sort oddly—check the logs if something is skipped.

* **CLI not found**
  Ensure the target IDE CLI is installed and on your `PATH`:

  * macOS/Linux: `which cursor`, `which agy`
  * Windows (PowerShell): `where.exe cursor`, `where.exe agy`

## Notes / Safety

`vsix-bridge` reduces risk from unofficial catalogs, but it can’t guarantee an extension is safe. Prefer reputable publishers and keep your IDEs updated.

## License

MIT (or your chosen license)
