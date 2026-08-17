#!/usr/bin/env python3
"""Check the status of a Fabric notebook run-job instance by ID.

Usage:
    python scripts/check_job_status.py <job-instance-id> [--notebook-name Healthcare_Data_Generator]
"""
import argparse
import json
import subprocess
import sys
import urllib.request

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


def find_notebook_id(token, workspace_id, notebook_name):
    url = f"{API_ROOT}/workspaces/{workspace_id}/notebooks"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    for nb in payload.get('value', []):
        if nb.get('displayName') == notebook_name:
            return nb.get('id')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id', help='Job instance ID to check')
    parser.add_argument('--workspace-id', default=WORKSPACE_ID)
    parser.add_argument('--notebook-name', default='Healthcare_Data_Generator')
    args = parser.parse_args()

    token = get_access_token()
    if not token:
        print("Could not get access token")
        sys.exit(1)

    notebook_id = find_notebook_id(token, args.workspace_id, args.notebook_name)
    if not notebook_id:
        print(f"Notebook '{args.notebook_name}' not found")
        sys.exit(1)

    url = f"{API_ROOT}/workspaces/{args.workspace_id}/items/{notebook_id}/jobs/instances/{args.job_id}"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(json.dumps(json.loads(resp.read().decode('utf-8')), indent=2))


if __name__ == '__main__':
    main()
