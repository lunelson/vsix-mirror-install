# Local VS Code Extension Marketplace

A lean, single-script solution to serve your locally installed VS Code extensions as a private marketplace for other IDEs (like Cursor or Antigravity).

## Features

-   **Sync**: Automatically detects installed extensions from VS Code (or Cursor) and downloads compatible VSIX files from the official Microsoft Marketplace.
-   **Serve**: Runs a lightweight HTTP server compatible with the VS Code Extension Gallery API.
-   **Private**: Keeps your extension list private and local.

## Prerequisites

-   Python 3.6+
-   `code` or `cursor` CLI command available in your PATH.

## Usage

### 1. Sync Extensions

Run the script with the `--sync` flag to index your installed extensions and download them:

```bash
python3 local_marketplace.py --sync
```

This will:
1.  List all installed extensions.
2.  Fetch metadata from Open VSX.
3.  Download VSIX files to the `./extensions` directory.
4.  Generate a `gallery.json` database.

### 2. Start the Marketplace

Run the script with the `--serve` flag to start the server:

```bash
python3 local_marketplace.py --serve
```

The server will start on `http://localhost:3000`.

### 3. Configure Your IDE

To use this local marketplace in Cursor or another VS Code fork, you need to configure the `serviceUrl` in your `product.json` or via settings if supported.

For **Cursor**, you can typically configure this in your settings (UI or JSON):

1.  Open Settings (`Cmd+,`).
2.  Search for "Marketplace".
3.  Set the **Extension Gallery Service URL** to:
    ```
    http://localhost:3000/extensionquery
    ```
4.  (Optional) Set **Extension Url Template** to:
    ```
    http://localhost:3000/extensions
    ```

Now, when you search for extensions in Cursor, it will query your local marketplace.

## Troubleshooting

-   **Missing Extensions**: If an extension is installed but not found in the Microsoft Marketplace (e.g., private or deprecated extensions), the script will skip it.
-   **Version Mismatch**: The script tries to match the exact installed version. If not found, it falls back to the latest available version on the Marketplace.
