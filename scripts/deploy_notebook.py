#!/usr/bin/env python3
"""Deploy (create or update) a Fabric notebook from a local .ipynb file.

If a notebook with the given display name already exists in the workspace,
its definition is updated in place (POST .../updateDefinition). Otherwise a
new notebook item is created (POST .../notebooks).

Usage:
    python scripts/deploy_notebook.py --notebook-path notebooks/healthcare_data_generator_fabric_inlined.ipynb --notebook-name Healthcare_Data_Generator
    python scripts/deploy_notebook.py --notebook-path notebooks/healthcare_data_validation.ipynb --notebook-name Healthcare_Data_Validation
"""
import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

WORKSPACE_ID = "8ecba42e-a6c5-4672-854f-d570b4f45d10"
API_ROOT = "https://api.fabric.microsoft.com/v1"


def get_access_token():
    ps_cmd = (
        '$token = (az account get-access-token --resource '
        '"https://api.fabric.microsoft.com" | ConvertFrom-Json).accessToken; '
        'Write-Host $token'
    )
    result = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd],
                             capture_output=True, text=True, timeout=30)
    return result.stdout.strip() or None


def api_request(url, token, method='GET', body=None):
    headers = {'Authorization': f'Bearer {token}'}
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body_text = resp.read().decode('utf-8')
            location = resp.headers.get('Location')
            payload = json.loads(body_text) if body_text else {}
            return resp.status, payload, location
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            payload = json.loads(error_body) if error_body else {}
        except json.JSONDecodeError:
            payload = {'raw': error_body}
        return e.code, payload, e.headers.get('Location') if e.headers else None


def find_notebook_id(token, workspace_id, notebook_name):
    url = f"{API_ROOT}/workspaces/{workspace_id}/notebooks"
    status, payload, _ = api_request(url, token)
    if status != 200:
        print(f"Failed to list notebooks (HTTP {status}): {payload}")
        return None
    for nb in payload.get('value', []):
        if nb.get('displayName') == notebook_name:
            return nb.get('id')
    return None


def find_or_create_folder(token, workspace_id, folder_name):
    url = f"{API_ROOT}/workspaces/{workspace_id}/folders"
    status, payload, _ = api_request(url, token)
    if status != 200:
        print(f"Failed to list folders (HTTP {status}): {payload}")
        return None
    for folder in payload.get('value', []):
        if folder.get('displayName') == folder_name and not folder.get('parentFolderId'):
            return folder.get('id')
    print(f"Folder '{folder_name}' not found -- creating it...")
    status, payload, _ = api_request(url, token, method='POST', body={'displayName': folder_name})
    if status != 201:
        print(f"Failed to create folder (HTTP {status}): {payload}")
        return None
    return payload.get('id')


def move_item_to_folder(token, workspace_id, item_id, folder_id):
    url = f"{API_ROOT}/workspaces/{workspace_id}/items/{item_id}/move"
    status, payload, _ = api_request(url, token, method='POST', body={'targetFolderId': folder_id})
    if status != 200:
        print(f"Failed to move item into folder (HTTP {status}): {payload}")
        return False
    return True


def poll_lro(token, location):
    for _ in range(30):
        time.sleep(2)
        status, payload, _ = api_request(location, token)
        print(f"   status = {payload.get('status')}")
        if payload.get('status') in ('Succeeded', 'Failed'):
            return payload.get('status') == 'Succeeded'
    return False


def build_definition(notebook_path):
    notebook_content = json.loads(Path(notebook_path).read_text(encoding='utf-8'))
    return {
        'format': 'ipynb',
        'parts': [
            {
                'path': 'notebook-content.ipynb',
                'payloadType': 'InlineBase64',
                'payload': base64.b64encode(json.dumps(notebook_content).encode('utf-8')).decode('utf-8')
            }
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-id', default=WORKSPACE_ID)
    parser.add_argument('--notebook-path', required=True)
    parser.add_argument('--notebook-name', required=True)
    parser.add_argument('--folder-name', help='Fabric workspace folder to place the notebook in (created if missing)')
    args = parser.parse_args()

    token = get_access_token()
    if not token:
        print("Could not get access token")
        sys.exit(1)

    folder_id = None
    if args.folder_name:
        folder_id = find_or_create_folder(token, args.workspace_id, args.folder_name)
        if not folder_id:
            sys.exit(1)

    definition = build_definition(args.notebook_path)
    notebook_id = find_notebook_id(token, args.workspace_id, args.notebook_name)

    if notebook_id:
        print(f"Found existing notebook '{args.notebook_name}' ({notebook_id}) -- updating definition...")
        url = f"{API_ROOT}/workspaces/{args.workspace_id}/items/{notebook_id}/updateDefinition"
        status, payload, location = api_request(url, token, method='POST', body={'definition': definition})
        if status != 202:
            print(f"Update failed (HTTP {status}): {payload}")
            sys.exit(1)
        ok = poll_lro(token, location) if location else True
        print("Update complete." if ok else "Update did not report success -- check the Fabric portal.")
        if folder_id:
            if move_item_to_folder(token, args.workspace_id, notebook_id, folder_id):
                print(f"Moved into folder '{args.folder_name}'.")
    else:
        print(f"Notebook '{args.notebook_name}' not found -- creating new notebook...")
        url = f"{API_ROOT}/workspaces/{args.workspace_id}/notebooks"
        create_body = {'displayName': args.notebook_name, 'definition': definition}
        if folder_id:
            create_body['folderId'] = folder_id
        status, payload, location = api_request(url, token, method='POST', body=create_body)
        if status not in (200, 201, 202):
            print(f"Create failed (HTTP {status}): {payload}")
            sys.exit(1)
        notebook_id = payload.get('id')
        if not notebook_id and status == 202 and location:
            poll_lro(token, location)
            notebook_id = find_notebook_id(token, args.workspace_id, args.notebook_name)
        if not notebook_id:
            print("Created, but could not determine the new notebook ID.")
            sys.exit(1)
        print(f"Created notebook '{args.notebook_name}' ({notebook_id}).")

    print(f"\nFabric URL: https://app.fabric.microsoft.com/groups/{args.workspace_id}/notebooks/{notebook_id}")


if __name__ == '__main__':
    main()
