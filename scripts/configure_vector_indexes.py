"""Create only Flairify's missing indexes. Uses the operator's gcloud login."""

import json
import os
import subprocess

project = os.environ.get("GOOGLE_CLOUD_PROJECT", "data-workshops")
database = os.environ.get("FIRESTORE_DATABASE", "flairify")
base = ["gcloud", "firestore", "indexes", "composite"]
flags = ["--project=" + project, "--database=" + database]
existing = json.loads(subprocess.check_output(base + ["list", *flags, "--format=json"], text=True))
fields = [
    "--field-config=field-path=owner,order=ASCENDING",
    "--field-config=field-path=space,order=ASCENDING",
    "--field-config=field-path=active,order=ASCENDING",
    "--field-config=field-path=facets,array-config=CONTAINS",
    "--field-config=field-path=price,order=ASCENDING",
]
for vector in (False, True):
    desired = {"owner", "space", "active", "facets", "price"} | ({"embedding"} if vector else set())
    if any(
        "/flairify_vectors/" in i["name"] and {f["fieldPath"] for f in i["fields"]} - {"__name__"} == desired
        for i in existing
    ):
        print("Index already present:", "vector" if vector else "price")
        continue
    vector_field = (
        ['--field-config=field-path=embedding,vector-config={"dimension":"768","flat":{}}'] if vector else []
    )
    subprocess.run(
        base
        + [
            "create",
            *flags,
            "--collection-group=flairify_vectors",
            "--query-scope=COLLECTION",
            *fields,
            *vector_field,
            "--async",
            "--quiet",
        ],
        check=True,
    )
