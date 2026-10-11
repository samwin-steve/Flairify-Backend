#!/usr/bin/env python3
"""Trusted operator bootstrap. Never exposed through an HTTP endpoint."""

import argparse
import hashlib
import subprocess
from datetime import datetime, timezone
import httpx
from google.cloud import firestore
from google.oauth2.credentials import Credentials


def main():
    parser = argparse.ArgumentParser(
        description="Grant Flairify access to an existing Firebase account by exact email."
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default="flairify")
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=["owner", "seller", "revoked"], required=True)
    args = parser.parse_args()
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    response = httpx.post(
        f"https://identitytoolkit.googleapis.com/v1/projects/{args.project}/accounts:lookup",
        headers={"Authorization": "Bearer " + token},
        json={"email": [args.email]},
        timeout=30,
    )
    response.raise_for_status()
    users = [
        u for u in response.json().get("users", []) if u.get("email", "").casefold() == args.email.casefold()
    ]
    if len(users) != 1 or users[0].get("disabled"):
        raise SystemExit("An active account with this email must sign in to Flairify first.")
    uid = users[0]["localId"]
    db = firestore.Client(project=args.project, database=args.database, credentials=Credentials(token))
    doc = hashlib.sha256(f"system:{uid}".encode()).hexdigest()
    data = {
        "id": uid,
        "role": args.role,
        "email": users[0]["email"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": "trusted-operator",
    }
    db.collection("flairify_seller_access").document(doc).set({"owner": "system", "id": uid, "data": data})
    print(f"Flairify {args.role} access saved for {users[0]['email']}. Refresh Seller Studio to use it.")


if __name__ == "__main__":
    main()
