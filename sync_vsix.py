#!/usr/bin/env python3
"""Engine-aware VSIX sync script for coder/code-marketplace.

This script:
- Figures out which extension versions are compatible with one or more
  VS Code engine versions (e.g. Cursor vs Antigravity).
- Downloads those VSIX files into per-market folders for coder/code-marketplace.
- Deletes any VSIX files in those folders that are no longer the desired
  version for any configured market.

By default, the extension list is derived from your installed extensions
via the VS Code / Cursor CLI. You can also hard-code EXTENSIONS below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, TypedDict

import semantic_version

import local_marketplace

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


# Configure one entry per logical marketplace you want to serve.
# "engine" should be the VS Code engine version of that client
# (e.g. the core version used by Antigravity or Cursor).
# "directory" is the folder passed to coder/code-marketplace's --directory.
class MarketConfig(TypedDict):
    engine: str
    directory: Path


MARKETS: Dict[str, MarketConfig] = {
    "legacy": {
        "engine": "1.89.0",  # cursor: 1.99.3
        "directory": Path("vsix-legacy"),
    },
    "modern": {
        "engine": "1.93.0",  # agy: 1.104.0
        "directory": Path("vsix-modern"),
    },
}

# Optional: hard-code extension IDs here. If left empty, we derive
# the list from your installed extensions via local_marketplace.get_installed_extensions().
EXTENSIONS: List[str] = []

# Base URL format for fallback VSIX downloads
MS_VSIX_BASE = (
    "https://marketplace.visualstudio.com/_apis/public/gallery/"
    "publishers/{publisher}/vsextensions/{name}/{version}/vspackage"
)


def get_extensions_to_sync() -> List[str]:
    if EXTENSIONS:
        return sorted({e.lower() for e in EXTENSIONS})
    installed = local_marketplace.get_installed_extensions()
    return sorted({e["id"].lower() for e in installed})


def get_target_engines() -> Dict[str, semantic_version.Version]:
    engines: Dict[str, semantic_version.Version] = {}
    for market, cfg in MARKETS.items():
        raw = cfg.get("engine")
        if not isinstance(raw, str):
            raise ValueError(f"Missing engine version for market '{market}'")
        engines[market] = semantic_version.Version(raw)
    return engines


def get_vsix_url_for_version(
    metadata: Dict, version_data: Dict, version_str: str
) -> str | None:
    files = version_data.get("files", []) or []
    for f in files:
        if f.get("assetType") == "Microsoft.VisualStudio.Services.VSIXPackage":
            src = f.get("source")
            if src:
                return src
    publisher = (metadata.get("publisher") or {}).get("publisherName")
    name = metadata.get("extensionName")
    if publisher and name:
        return MS_VSIX_BASE.format(publisher=publisher, name=name, version=version_str)
    return None


def find_compatible_versions_for_extension(
    ext_id: str, target_engines: Dict[str, semantic_version.Version]
) -> Tuple[Dict[str, Tuple[str, str]], Dict]:
    """Return per-market compatible versions and the raw metadata.

    result: {market_name: (version_str, vsix_url)}
    """
    metadata = local_marketplace.fetch_extension_metadata_ms(ext_id)
    if not metadata:
        print(f"[WARN] {ext_id}: not found in MS Marketplace")
        return {}, {}

    versions = metadata.get("versions", []) or []
    if not versions:
        print(f"[WARN] {ext_id}: no versions in metadata")
        return {}, metadata

    versions_sorted = sorted(
        versions,
        key=lambda v: semantic_version.Version(v["version"]),
        reverse=True,
    )

    per_market: Dict[str, Tuple[str, str]] = {}

    for market, engine_ver in target_engines.items():
        for vdata in versions_sorted:
            props = vdata.get("properties", []) or []
            engine_prop = next(
                (
                    p
                    for p in props
                    if p.get("key") == "Microsoft.VisualStudio.Code.Engine"
                ),
                None,
            )
            if not engine_prop:
                continue
            try:
                spec = semantic_version.SimpleSpec(engine_prop["value"])
            except ValueError:
                continue
            if engine_ver not in spec:
                continue
            ver_str = vdata["version"]
            url = get_vsix_url_for_version(metadata, vdata, ver_str)
            if not url:
                print(f"[WARN] {ext_id}: no VSIX URL for {ver_str} in {market}")
                break
            per_market[market] = (ver_str, url)
            break
        if market not in per_market:
            print(
                f"[WARN] {ext_id}: no compatible version for engine {engine_ver} in market '{market}'"
            )

    return per_market, metadata


def sync_markets() -> None:
    target_engines = get_target_engines()
    market_dirs: Dict[str, Path] = {}
    expected_files: Dict[str, set[str]] = {}

    for market, cfg in MARKETS.items():
        path = cfg["directory"]
        path.mkdir(parents=True, exist_ok=True)
        market_dirs[market] = path
        expected_files[market] = set()

    exts = get_extensions_to_sync()
    print(f"Syncing {len(exts)} extensions across {len(MARKETS)} markets...")

    for ext_id in exts:
        print(f"== {ext_id} ==")
        per_market, _ = find_compatible_versions_for_extension(ext_id, target_engines)
        for market, (ver_str, url) in per_market.items():
            dest_dir = market_dirs[market]
            filename = f"{ext_id}-{ver_str}.vsix"
            dest_path = dest_dir / filename
            expected_files[market].add(filename)
            local_marketplace.download_vsix(url, dest_path)

    # Cleanup: remove any VSIX files that are no longer desired in each market
    for market, dir_path in market_dirs.items():
        keep = expected_files[market]
        for vsix_path in dir_path.glob("*.vsix"):
            if vsix_path.name not in keep:
                print(f"[CLEAN] Removing outdated VSIX from {market}: {vsix_path.name}")
                vsix_path.unlink()

    print("Sync complete.")


def main() -> None:
    sync_markets()


if __name__ == "__main__":
    main()
