# vsix-bridge Specification

## Core Concept

**vsix-bridge** solves the problem of VS Code fork IDEs (Cursor, Antigravity, Windsurf, etc.) having limited or unreliable extension catalogs. These forks often use OpenVSIX or similar registries which may:

- Lag behind official Microsoft Marketplace updates
- Contain typosquats or poorly vetted packages
- Miss extensions entirely

**Solution:** Use the user's local VS Code installation as the source of truth. Download the exact extensions (and compatible versions) from the official Microsoft VS Code Marketplace, then install them directly into fork IDEs via their CLIs.

---

## Current Implementation Overview

### Two-Phase Architecture

1. **`sync` (sync_vsix.py)** - Downloads VSIX files from Microsoft Marketplace
2. **`install` (bulk_install_vsix.py)** - Installs VSIX files into target IDEs

### Sync Phase Logic

```
1. Get extension list (from VS Code CLI or hard-coded list)
2. For each target IDE:
   a. Get that IDE's VS Code engine version (currently hard-coded)
   b. Create output directory: vsix-{ide_name}/
3. For each extension:
   a. Query Microsoft Marketplace API for all versions
   b. Sort versions by semver (newest first)
   c. For each target IDE:
      - Find newest version where engines.vscode range accepts IDE's engine version
      - Download VSIX to vsix-{ide_name}/{publisher.name}-{version}.vsix
4. Cleanup: Remove any VSIX files in output dirs that aren't the desired version
```

### Install Phase Logic

```
1. List currently installed extensions via IDE CLI (--list-extensions --show-versions)
2. For each VSIX file in vsix-{ide_name}/:
   a. Parse filename to extract extension ID and version
   b. Check if extension is already installed:
      - If not installed:
        - Default mode: Skip (log message)
        - --force mode: Queue for install
      - If installed:
        - Default mode: Install only if VSIX version > installed version
        - --force mode: Install regardless
3. Execute planned installs via CLI (--install-extension)
```

---

## Current Configuration

### Hard-coded Values

| Value | Location | Current State |
|-------|----------|---------------|
| Target IDEs | `MARKET_ENGINES` dict | `cursor: 1.105.1`, `agy: 1.104.0` |
| Engine versions | `MARKET_ENGINES` dict | Manually set, outdated |
| Extension list source | `EXTENSIONS` list | Empty (uses VS Code CLI) |
| Output directories | Derived | `vsix-{ide_name}` |
| Source CLI | Hard-coded | Always `code` |

### FUTURE.md Notes

Shows how to dynamically get embedded VS Code versions:
```sh
# Cursor (macOS)
jq -r '.vscodeVersion' /Applications/Cursor.app/Contents/Resources/app/product.json

# Antigravity (macOS)
jq -r '.ideVersion' /Applications/Antigravity.app/Contents/Resources/app/product.json
```

---

## Edge Cases Currently Handled

| Scenario | Current Behavior |
|----------|------------------|
| Extension not in Microsoft Marketplace | Warn and skip |
| No versions in metadata | Warn and skip |
| No compatible version for engine | Warn and skip that IDE |
| No VSIX download URL | Warn and skip |
| Non-semver version strings | Fallback to string comparison |
| VSIX file already downloaded | Skip download |
| Extension not installed in target IDE | Skip install (unless --force) |
| Installed version >= VSIX version | Skip install |
| Stale VSIX files from old versions | Deleted during cleanup phase |

---

## User Scenarios & Starting States (Gaps to Address)

### Scenario 1: Fresh System - Multiple Fork IDEs Installed

**User state:**
- VS Code installed with extensions
- Cursor, Antigravity, Windsurf installed
- Fork IDEs have no extensions or only defaults

**Current behavior:** Works as intended

**Gap:** User must know which CLIs are available and manually specify markets

**Needed:**
- Auto-detect installed fork IDEs
- Verify CLI is available in PATH for each

---

### Scenario 2: Fork IDEs Have Existing Extensions from OpenVSIX

**User state:**
- Fork IDEs already have extensions installed from OpenVSIX or other registries

**Current behavior:**
- Default mode: Only updates existing extensions (preserves user's set)
- --force mode: Installs all extensions from VS Code

**Gap:** No warning about the semantic difference

**Needed:**
- Warn user that their VS Code extensions will become the source of truth
- Optionally: Offer to merge or show diff between VS Code and fork extensions
- Consider: Should --force uninstall extensions not in VS Code?

---

### Scenario 3: CLI Not Installed or Not in PATH

**User state:**
- IDE is installed but CLI not available (e.g., user hasn't run "Install 'cursor' command in PATH")

**Current behavior:**
- sync_vsix.py: Hard exits with error if `code` CLI fails
- bulk_install_vsix.py: Fails with subprocess error

**Needed:**
- Detect missing CLIs before starting
- Provide helpful instructions for each IDE on how to install CLI
- Consider: Auto-detect CLI locations (varies by OS)

---

### Scenario 4: Unknown Engine Version

**User state:**
- New fork IDE not in configuration
- Or fork IDE updated its embedded VS Code version

**Current behavior:** Uses hard-coded, potentially outdated engine versions

**Needed:**
- Auto-detect engine version from each IDE's product.json (per FUTURE.md)
- Handle different property names (`vscodeVersion` vs `ideVersion`)
- Handle different app locations by OS

---

### Scenario 5: Extension Installed but Disabled/Uninstalled in VS Code

**User state:**
- Extension was installed in VS Code
- User later disabled or uninstalled it
- Extension still exists in fork IDE

**Current behavior:**
- If uninstalled from VS Code: Won't appear in extension list, won't be synced
- Fork IDE keeps its version (no removal)

**Gap:** Orphaned extensions in fork IDEs

**Needed:**
- Option to sync removals (uninstall from fork if not in VS Code)
- Or at minimum: Report extensions in fork that aren't in VS Code

---

### Scenario 6: Version Compatibility Mismatch

**User state:**
- VS Code is on latest version
- Fork IDE uses older embedded VS Code
- Some extensions require newer VS Code

**Current behavior:** Correctly finds compatible older version or warns if none exists

**Working as intended** - No gap

---

### Scenario 7: Network/API Failures

**User state:**
- Intermittent network issues
- Microsoft Marketplace rate limiting

**Current behavior:**
- Catches exceptions and warns
- Continues to next extension

**Gap:** No retry logic, no offline mode

**Needed:**
- Retry with backoff
- Cache metadata for offline reference
- Resume partial syncs

---

### Scenario 8: Cross-Platform Differences

**User state:**
- Running on Windows or Linux instead of macOS

**Current behavior:**
- CLI calls assume Unix-style
- product.json paths are macOS-specific

**Needed:**
- Platform-specific paths for product.json
- Platform-specific CLI detection
- Handle Windows path separators

---

## Extension State Matrix

| VS Code State | Fork IDE State | Default Behavior | --force Behavior |
|---------------|----------------|------------------|------------------|
| Installed | Not installed | Skip | Install |
| Installed | Installed (older) | Update | Update |
| Installed | Installed (same) | Skip | Reinstall |
| Installed | Installed (newer) | Skip | Reinstall (downgrade) |
| Not installed | Installed | No action | No action |
| Disabled | Installed | No action (not in list) | No action |

**Question:** Should there be a `--sync-removals` option to uninstall fork extensions not in VS Code?

---

## API Details

### Microsoft Marketplace API

**Endpoint:** `POST https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery`

**Request:**
```json
{
  "filters": [{
    "criteria": [{"filterType": 7, "value": "publisher.extensionName"}],
    "pageNumber": 1,
    "pageSize": 1
  }],
  "flags": 0x293  // Versions + Files + Properties + AssetURI + InstallTargets
}
```

**Response contains:**
- `versions[]` - All published versions
- `versions[].properties[]` - Including `Microsoft.VisualStudio.Code.Engine` (the `engines.vscode` value)
- `versions[].files[]` - Including VSIX download URL

### IDE CLI Commands

| Operation | Command |
|-----------|---------|
| List extensions | `{cli} --list-extensions --show-versions` |
| Install extension | `{cli} --install-extension {path} [--force]` |
| Uninstall extension | `{cli} --uninstall-extension {id}` (not currently used) |

---

## Proposed CLI Structure (Node.js Rewrite)

Based on the new README:

```
vsix-bridge sync [--to <ide>...]
vsix-bridge install [--to <ide>] [--force] [--dry-run]
```

**Additional commands to consider:**
```
vsix-bridge status           # Show extension diff between VS Code and forks
vsix-bridge detect           # Auto-detect installed IDEs and their engine versions
vsix-bridge config           # Show/edit configuration
```

---

## Open Questions for Review

1. **Source of truth:** Should VS Code always be the source, or allow specifying another IDE?

2. **Extension removal:** Should `--force` or a separate flag uninstall fork extensions not in VS Code?

3. **Merge strategy:** What if user wants to union VS Code + fork extensions rather than replace?

4. **First-run warning:** How explicit should the warning be about overwriting fork extensions?

5. **Engine version detection:** How to handle IDEs that don't expose their engine version in product.json?

6. **CLI detection:** Should we auto-detect CLIs or require user configuration?

7. **Workspace extensions:** Should we handle workspace-recommended extensions differently?

8. **Extension settings:** VSIX install doesn't migrate settings - should we note this?
