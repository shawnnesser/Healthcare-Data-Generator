#!/usr/bin/env python3
"""Deploy (create or update) the Healthcare Data Model Fabric semantic model
from the local TMSL files under fabric_items/Healthcare_Data_Model/.

If a semantic model with the given display name already exists in the
workspace, its definition is updated in place (POST .../updateDefinition).
Otherwise a new semantic model item is created (POST .../semanticModels).

Usage:
    python scripts/deploy_semantic_model.py --model-name Healthcare_Data_Model --folder-name "Healthcare Provider Simulation"
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
MODEL_DIR = Path(__file__).resolve().parents[1] / "fabric_items" / "Healthcare_Data_Model"


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


def find_semantic_model_id(token, workspace_id, model_name):
    url = f"{API_ROOT}/workspaces/{workspace_id}/semanticModels"
    status, payload, _ = api_request(url, token)
    if status != 200:
        print(f"Failed to list semantic models (HTTP {status}): {payload}")
        return None
    for sm in payload.get('value', []):
        if sm.get('displayName') == model_name:
            return sm.get('id')
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


def _part(path, payload_bytes):
    return {
        'path': path,
        'payloadType': 'InlineBase64',
        'payload': base64.b64encode(payload_bytes).decode('utf-8'),
    }


def build_definition(model_dir: Path):
    model_bim = (model_dir / 'model.bim').read_bytes()
    pbism = (model_dir / 'definition.pbism').read_bytes()
    return {
        'parts': [
            _part('model.bim', model_bim),
            _part('definition.pbism', pbism),
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-id', default=WORKSPACE_ID)
    parser.add_argument('--model-dir', default=str(MODEL_DIR))
    parser.add_argument('--model-name', required=True)
    parser.add_argument('--folder-name', help='Fabric workspace folder to place the semantic model in (created if missing)')
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    if not (model_dir / 'model.bim').exists():
        print(f"model.bim not found under {model_dir} -- run scripts/build_semantic_model.py first.")
        sys.exit(1)

    token = get_access_token()
    if not token:
        print("Could not get access token")
        sys.exit(1)

    folder_id = None
    if args.folder_name:
        folder_id = find_or_create_folder(token, args.workspace_id, args.folder_name)
        if not folder_id:
            sys.exit(1)

    definition = build_definition(model_dir)
    model_id = find_semantic_model_id(token, args.workspace_id, args.model_name)

    if model_id:
        print(f"Found existing semantic model '{args.model_name}' ({model_id}) -- updating definition...")
        url = f"{API_ROOT}/workspaces/{args.workspace_id}/items/{model_id}/updateDefinition"
        status, payload, location = api_request(url, token, method='POST', body={'definition': definition})
        if status not in (200, 202):
            print(f"Update failed (HTTP {status}): {payload}")
            sys.exit(1)
        ok = poll_lro(token, location) if location else True
        print("Update complete." if ok else "Update did not report success -- check the Fabric portal.")
        if folder_id:
            if move_item_to_folder(token, args.workspace_id, model_id, folder_id):
                print(f"Moved into folder '{args.folder_name}'.")
    else:
        print(f"Semantic model '{args.model_name}' not found -- creating new semantic model...")
        url = f"{API_ROOT}/workspaces/{args.workspace_id}/semanticModels"
        create_body = {'displayName': args.model_name, 'definition': definition}
        if folder_id:
            create_body['folderId'] = folder_id
        status, payload, location = api_request(url, token, method='POST', body=create_body)
        if status not in (200, 201, 202):
            print(f"Create failed (HTTP {status}): {payload}")
            sys.exit(1)
        model_id = payload.get('id') if payload else None
        if not model_id and status == 202 and location:
            poll_lro(token, location)
            model_id = find_semantic_model_id(token, args.workspace_id, args.model_name)
        if not model_id:
            print("Created, but could not determine the new semantic model ID.")
            sys.exit(1)
        print(f"Created semantic model '{args.model_name}' ({model_id}).")

    print(f"\nFabric URL: https://app.fabric.microsoft.com/groups/{args.workspace_id}/datasets/{model_id}")


if __name__ == '__main__':
    main()
