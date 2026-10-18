"""Create/update Flairify's dedicated input template; leave other templates/floors alone."""

import argparse
import json
import subprocess
from pathlib import Path

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials as UserCredentials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="data-workshops")
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--template", default="flairify-input-guard")
    parser.add_argument(
        "--gcloud-login", action="store_true", help="Use your current gcloud login instead of ADC"
    )
    args = parser.parse_args()
    subprocess.run(
        ["gcloud", "services", "enable", "modelarmor.googleapis.com", f"--project={args.project}", "--quiet"],
        check=True,
    )
    credentials: Credentials
    if args.gcloud_login:
        credentials = UserCredentials(
            subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        )
    else:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)
    collection = f"https://modelarmor.{args.region}.rep.googleapis.com/v1/projects/{args.project}/locations/{args.region}/templates"
    name = f"projects/{args.project}/locations/{args.region}/templates/{args.template}"
    body = json.loads((Path(__file__).resolve().parents[1] / "infra/model-armor-template.json").read_text())
    existing = session.get(f"{collection}/{args.template}", timeout=30)
    if existing.status_code == 404:
        result = session.post(collection, params={"templateId": args.template}, json=body, timeout=30)
    else:
        existing.raise_for_status()
        result = session.patch(
            f"{collection}/{args.template}",
            params={"updateMask": "filterConfig,templateMetadata,labels"},
            json={**body, "name": name},
            timeout=30,
        )
    result.raise_for_status()
    subprocess.run(
        [
            "gcloud",
            "projects",
            "add-iam-policy-binding",
            args.project,
            f"--member=serviceAccount:flairify-api@{args.project}.iam.gserviceaccount.com",
            "--role=roles/modelarmor.user",
            "--condition=None",
            "--quiet",
            "--format=none",
        ],
        check=True,
    )
    print(f"Configured {name}; API runtime can sanitize, without template administration.")


if __name__ == "__main__":
    main()
