#!/usr/bin/env python3
"""Trigger an on-demand run of the Healthcare Data Generator notebook in
Microsoft Fabric via the REST Jobs API, then poll until it completes.

Usage:
    python scripts/run_fabric_notebook.py
    python scripts/run_fabric_notebook.py --poll-interval 15 --timeout 3600
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

WORKSPACE_ID = "8ecba42e-a6c5-4672-854f-d570b4f45d10"
NOTEBOOK_NAME = "Healthcare_Data_Generator"
API_ROOT = "https://api.fabric.microsoft.com/v1"


def get_access_token():
    """Get Azure access token for the Fabric API via the az CLI."""
    ps_cmd = (
        '$token = (az account get-access-token --resource '
        '"https://api.fabric.microsoft.com" | ConvertFrom-Json).accessToken; '
        'Write-Host $token'
    )
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command', ps_cmd],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Failed to get access token: {result.stderr}")
        return None
    token = result.stdout.strip()
    return token or None


def api_request(url, token, method='GET', body=None):
    headers = {'Authorization': f'Bearer {token}'}
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode('utf-8')

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body_text = response.read().decode('utf-8')
            location = response.headers.get('Location')
            payload = json.loads(body_text) if body_text else {}
            return response.status, payload, location
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
    print(f"Notebook '{notebook_name}' not found. Available notebooks:")
    for nb in payload.get('value', []):
        print(f"   - {nb.get('displayName')}")
    return None


def start_run(token, workspace_id, notebook_id):
    url = f"{API_ROOT}/workspaces/{workspace_id}/items/{notebook_id}/jobs/instances?jobType=RunNotebook"
    status, payload, location = api_request(url, token, method='POST', body={})
    if status == 202:
        job_instance_url = location or payload.get('id')
        print(f"Run started (HTTP 202 Accepted).")
        return job_instance_url
    print(f"Failed to start run (HTTP {status}): {payload}")
    return None


def poll_run(job_instance_url, poll_interval, timeout):
    print(f"Polling job status every {poll_interval}s (timeout {timeout}s)...")
    start = time.time()
    last_status = None
    token = get_access_token()
    token_fetched_at = time.time()
    while time.time() - start < timeout:
        # AAD access tokens expire after ~1 hour; refresh proactively so long
        # backfills don't fail polling with a stale token (job itself is
        # unaffected -- it authenticates independently inside Fabric).
        if time.time() - token_fetched_at > 2700:
            token = get_access_token()
            token_fetched_at = time.time()

        status_code, payload, _ = api_request(job_instance_url, token)
        if status_code == 401:
            token = get_access_token()
            token_fetched_at = time.time()
            time.sleep(2)
            continue
        if status_code != 200:
            print(f"Warning: status check failed (HTTP {status_code}): {payload}")
            time.sleep(poll_interval)
            continue

        run_status = payload.get('status')
        if run_status != last_status:
            elapsed = int(time.time() - start)
            print(f"   [{elapsed:>4}s] status = {run_status}")
            last_status = run_status

        if run_status in ('Completed', 'Failed', 'Cancelled', 'Deduped'):
            return run_status, payload

        time.sleep(poll_interval)

    print("Timed out waiting for job to finish.")
    return 'Timeout', None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-id', default=WORKSPACE_ID)
    parser.add_argument('--notebook-name', default=NOTEBOOK_NAME)
    parser.add_argument('--poll-interval', type=int, default=15, help='Seconds between status checks')
    parser.add_argument('--timeout', type=int, default=3600, help='Max seconds to wait for completion')
    args = parser.parse_args()

    print("=" * 70)
    print("FABRIC NOTEBOOK - PROGRAMMATIC RUN")
    print("=" * 70)

    print("\n[1/4] Authenticating with Azure...")
    token = get_access_token()
    if not token:
        print("Could not get access token")
        sys.exit(1)
    print("Authentication successful")

    print("\n[2/4] Locating notebook...")
    notebook_id = find_notebook_id(token, args.workspace_id, args.notebook_name)
    if not notebook_id:
        sys.exit(1)
    print(f"Notebook ID: {notebook_id}")

    print("\n[3/4] Starting on-demand run...")
    job_instance_url = start_run(token, args.workspace_id, notebook_id)
    if not job_instance_url:
        sys.exit(1)
    print(f"Job instance: {job_instance_url}")

    print("\n[4/4] Waiting for run to complete...")
    final_status, final_payload = poll_run(job_instance_url, args.poll_interval, args.timeout)

    print("\n" + "=" * 70)
    if final_status == 'Completed':
        print("RUN COMPLETED SUCCESSFULLY")
    else:
        print(f"RUN ENDED WITH STATUS: {final_status}")
    print("=" * 70)

    if final_payload:
        print(json.dumps(final_payload, indent=2))

    web_url = f"https://app.fabric.microsoft.com/groups/{args.workspace_id}/notebooks/{notebook_id}"
    print(f"\nView in Fabric: {web_url}")

    if final_status != 'Completed':
        sys.exit(1)


if __name__ == '__main__':
    main()
