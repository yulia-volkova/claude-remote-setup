#!/usr/bin/env python3
"""Upload files to Google Drive via the Drive API.

Usage:
    python3 upload_to_gdrive.py FILE [FILE ...] [--folder FOLDER_ID] [--name NAME]

Example:
    python3 upload_to_gdrive.py logs/eval_result.eval --folder 1abc123 --name "bfcl_attack_2026-04-15.eval"

Requires:
    - google-api-python-client, google-auth (pip install)
    - OAuth token at ~/.config/google-docs-mcp/token.json with drive.file scope
    - Google Drive API enabled in the Google Cloud project
"""

import argparse
import json
import mimetypes
import sys
from pathlib import Path


def get_drive_service():
    """Build Drive API service from the shared OAuth token."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = Path.home() / ".config/google-docs-mcp/token.json"
    if not token_path.exists():
        print(f"ERROR: OAuth token not found at {token_path}", file=sys.stderr)
        sys.exit(1)

    token_data = json.loads(token_path.read_text())
    creds = Credentials(
        token=None,
        refresh_token=token_data["refresh_token"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def upload_file(service, file_path, name=None, folder_id=None):
    """Upload a single file to Google Drive. Returns file metadata."""
    from googleapiclient.http import MediaFileUpload

    file_path = Path(file_path)
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    upload_name = name or file_path.name
    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    file_metadata = {"name": upload_name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
    result = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink",
    ).execute()

    return result


def main():
    parser = argparse.ArgumentParser(description="Upload files to Google Drive")
    parser.add_argument("files", nargs="+", help="File(s) to upload")
    parser.add_argument(
        "--folder",
        default=None,
        help="Google Drive folder ID to upload into. "
        "Find it in the folder's URL: drive.google.com/drive/folders/FOLDER_ID",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Override the filename in Drive (only applies when uploading a single file).",
    )
    args = parser.parse_args()

    if args.name and len(args.files) > 1:
        print("ERROR: --name can only be used with a single file", file=sys.stderr)
        sys.exit(1)

    service = get_drive_service()

    for file_path in args.files:
        name = args.name if args.name else None
        result = upload_file(service, file_path, name=name, folder_id=args.folder)
        print(f"Uploaded: {result['name']}")
        print(f"  ID: {result['id']}")
        print(f"  Link: {result.get('webViewLink', 'N/A')}")


if __name__ == "__main__":
    main()
