#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
import argparse
import http.server
import socketserver
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

# Configuration
EXTENSIONS_DIR = Path("extensions")
GALLERY_FILE = Path("gallery.json")
MS_MARKETPLACE_API = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
PORT = 6789

def get_installed_extensions() -> List[Dict[str, str]]:
    """
    Get list of installed extensions using 'code' CLI.
    Returns a list of dicts with 'id' and 'version'.
    """
    print("Scanning installed extensions...")
    try:
        # Try 'code' first, then 'cursor' if code is not found
        cmd = ["code", "--list-extensions", "--show-versions"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        except FileNotFoundError:
            print("'code' command not found, trying 'cursor'...")
            cmd = ["cursor", "--list-extensions", "--show-versions"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        extensions = []
        for line in result.stdout.strip().split('\n'):
            if '@' in line:
                ext_id, version = line.split('@')
                extensions.append({'id': ext_id.lower(), 'version': version})

        print(f"Found {len(extensions)} installed extensions.")
        return extensions
    except subprocess.CalledProcessError as e:
        print(f"Error running VS Code CLI: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: Neither 'code' nor 'cursor' CLI tools found in PATH.")
        sys.exit(1)

def fetch_extension_metadata_ms(ext_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch extension metadata from Microsoft Marketplace.
    """
    # Flags: IncludeVersions(1) + IncludeFiles(2) + IncludeCategoryAndTags(4) + IncludeSharedAccounts(8) + IncludeVersionProperties(16) + ExcludeNonValidated(32) + IncludeInstallationTargets(128) + IncludeAssetUri(512) + IncludeStatistics(1024) + IncludeLatestVersionOnly(4096)
    # We want all versions to find the matching one, so we don't use IncludeLatestVersionOnly (4096) initially,
    # but for efficiency we might want to just check latest if exact version match isn't critical or if we can't query specific version easily.
    # Actually, we can filter by name and get versions.

    # 0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x80 | 0x200 = 0x29F = 671
    # Let's use a broad set of flags to get what we need.
    flags = 914 # 0x392: IncludeVersions(1) + IncludeFiles(2) + IncludeVersionProperties(16) + IncludeAssetUri(512) + IncludeInstallationTargets(128) + IncludeCategoryAndTags(4) ... roughly

    # Better flags: 0x1 (Versions) + 0x2 (Files) + 0x200 (AssetUri) = 515

    payload = {
        "filters": [{
            "criteria": [
                {"filterType": 7, "value": ext_id} # FilterType 7 is ExtensionName
            ],
            "pageNumber": 1,
            "pageSize": 1,
            "sortBy": 0,
            "sortOrder": 0
        }],
        "assetTypes": [],
        "flags": flags
    }

    try:
        req = urllib.request.Request(
            MS_MARKETPLACE_API,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json;api-version=3.0-preview.1"
            }
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            results = data.get('results', [])
            if results and results[0].get('extensions'):
                return results[0]['extensions'][0]
            return None
    except Exception as e:
        print(f"  Error fetching {ext_id} from MS Marketplace: {e}")
        return None

def download_vsix(url: str, dest_path: Path):
    """
    Download VSIX file from URL.
    """
    if dest_path.exists():
        print(f"  VSIX already exists: {dest_path}")
        return

    print(f"  Downloading {url}...")
    try:
        with urllib.request.urlopen(url) as response, open(dest_path, 'wb') as out_file:
            out_file.write(response.read())
    except Exception as e:
        print(f"  Failed to download VSIX: {e}")

def sync_extensions():
    """
    Sync installed extensions to local storage.
    """
    EXTENSIONS_DIR.mkdir(exist_ok=True)

    installed = get_installed_extensions()
    gallery_data = {}

    # Load existing gallery if available
    if GALLERY_FILE.exists():
        try:
            with open(GALLERY_FILE, 'r') as f:
                gallery_data = json.load(f)
        except json.JSONDecodeError:
            pass

    updated_gallery = {}

    for ext in installed:
        ext_id = ext['id']
        current_version = ext['version']

        print(f"Processing {ext_id} ({current_version})...")

        # Check if we already have this version in our gallery
        if ext_id in gallery_data and gallery_data[ext_id].get('version') == current_version:
             # Verify VSIX exists
             vsix_name = f"{ext_id}-{current_version}.vsix"
             if (EXTENSIONS_DIR / vsix_name).exists():
                 print(f"  Already up to date.")
                 updated_gallery[ext_id] = gallery_data[ext_id]
                 continue

        metadata = fetch_extension_metadata_ms(ext_id)
        if not metadata:
            print(f"  Extension {ext_id} not found in MS Marketplace.")
            continue

        # Find the specific version
        versions = metadata.get('versions', [])
        target_version_data = next((v for v in versions if v.get('version') == current_version), None)

        if not target_version_data:
            print(f"  Version {current_version} not found. Checking latest...")
            if versions:
                target_version_data = versions[0] # Latest version is usually first
                latest_ver = target_version_data.get('version')
                print(f"  Using latest version {latest_ver} instead of {current_version}")
                current_version = latest_ver
            else:
                print(f"  No versions found for {ext_id}")
                continue

        # Find VSIX download URL
        files = target_version_data.get('files', [])
        download_url = next((f.get('source') for f in files if f.get('assetType') == "Microsoft.VisualStudio.Services.VSIXPackage"), None)

        if not download_url:
            # Construct fallback URL if missing (standard MS format)
            # https://marketplace.visualstudio.com/_apis/public/gallery/publishers/{publisher}/vsextensions/{extension}/{version}/vspackage
            publisher = metadata.get('publisher', {}).get('publisherName')
            name = metadata.get('extensionName')
            if publisher and name:
                download_url = f"https://marketplace.visualstudio.com/_apis/public/gallery/publishers/{publisher}/vsextensions/{name}/{current_version}/vspackage"
            else:
                print(f"  Could not determine download URL for {ext_id}")
                continue

        vsix_filename = f"{ext_id}-{current_version}.vsix"
        vsix_path = EXTENSIONS_DIR / vsix_filename

        download_vsix(download_url, vsix_path)

        # Store metadata for gallery
        # We store the MS metadata structure directly now, but we might need to wrap it
        # or adapt it if our server code expects something else.
        # Our server code previously adapted Open VSX to VS Code format.
        # Now we have VS Code format (mostly), so we can store it more directly.

        updated_gallery[ext_id] = {
            'id': ext_id,
            'version': current_version,
            'metadata': metadata, # This is now MS format
            'vsix_path': str(vsix_filename)
        }

        # Save incrementally
        with open(GALLERY_FILE, 'w') as f:
            json.dump(updated_gallery, f, indent=2)

    print("Sync complete.")

class MarketplaceHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/marketplace/extensionquery':
            self.handle_extension_query()
        else:
            self.send_error(404)

    def translate_path(self, path):
        # Handle VSIX downloads with /marketplace prefix
        if path.startswith('/marketplace/extensions/'):
            # Strip /marketplace to map to local ./extensions directory
            path = path.replace('/marketplace/extensions/', '/extensions/')
        return super().translate_path(path)

    def handle_extension_query(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        try:
            query = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Very basic implementation of extension query
        # We ignore most filters and just return results if we have the extension

        results = []

        with open(GALLERY_FILE, 'r') as f:
            gallery = json.load(f)

        filters = query.get('filters', [])
        for f in filters:
            criteria = f.get('criteria', [])
            for c in criteria:
                # Filter Type 7 is ExtensionName (id)
                if c.get('filterType') == 7:
                    ext_name = c.get('value', '').lower()
                    if ext_name in gallery:
                        item = gallery[ext_name]
                        # Construct response object compatible with VS Code
                        # We now have MS metadata stored directly, so we can use it more directly.
                        meta = item['metadata']

                        # Construct the download URL
                        host = self.headers.get('Host', f'localhost:{PORT}')
                        base_url = f"http://{host}/marketplace/extensions"
                        asset_uri = f"{base_url}/{item['vsix_path']}"

                        # We need to return the structure VS Code expects.
                        # We can mostly pass through the stored metadata but we MUST override the VSIX URL.

                        # Create a deep copy or new dict to avoid modifying stored data if we were caching (we aren't really)
                        extension_entry = {
                            "extensionId": meta.get('extensionId'),
                            "extensionName": meta.get('extensionName'),
                            "displayName": meta.get('displayName'),
                            "shortDescription": meta.get('shortDescription'),
                            "publisher": meta.get('publisher'),
                            "versions": []
                        }

                        # Find the version we have
                        stored_version = item['version']
                        original_versions = meta.get('versions', [])
                        target_version = next((v for v in original_versions if v.get('version') == stored_version), None)

                        if target_version:
                            # Create a version entry that points to our local file
                            # We keep original properties (like engine compatibility)
                            new_version = target_version.copy()
                            new_version['files'] = [
                                {
                                    "assetType": "Microsoft.VisualStudio.Services.VSIXPackage",
                                    "source": asset_uri
                                }
                            ]
                            extension_entry['versions'].append(new_version)
                        else:
                            # Fallback if version not found in metadata (shouldn't happen if sync worked)
                            extension_entry['versions'].append({
                                "version": stored_version,
                                "files": [{
                                    "assetType": "Microsoft.VisualStudio.Services.VSIXPackage",
                                    "source": asset_uri
                                }],
                                "properties": [
                                    {"key": "Microsoft.VisualStudio.Code.Engine", "value": "^1.0.0"}
                                ]
                            })

                        results.append(extension_entry)

        response = {
            "results": [
                {
                    "extensions": results,
                    "pagingToken": None,
                    "resultMetadata": [
                        {
                            "metadataType": "ResultCount",
                            "metadataItems": [
                                {
                                    "name": "TotalCount",
                                    "count": len(results)
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

def serve_marketplace():
    """
    Start the marketplace server.
    """
    # Ensure we can serve files from current directory
    # We need to serve /extensions/file.vsix

    print(f"Starting local marketplace on port {PORT}...")

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("", PORT), MarketplaceHandler) as httpd:
        print(f"Serving at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

def main():
    parser = argparse.ArgumentParser(description="Local VS Code Extension Marketplace")
    parser.add_argument("--sync", action="store_true", help="Sync installed extensions to local storage")
    parser.add_argument("--serve", action="store_true", help="Serve the local marketplace")

    args = parser.parse_args()

    if args.sync:
        sync_extensions()
    elif args.serve:
        serve_marketplace()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
