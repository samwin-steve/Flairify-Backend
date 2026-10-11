import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from ..config import settings
from ..models import GenerationJob, now
from ..store import store
from . import wardrobe, try_on, video, avatars, garment_images

pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="flairify-local")


def public(job):
    return {k: v for k, v in job.items() if k not in ("payload", "operation", "lease_until")}


def enqueue(owner, job_id, delay=0):
    cfg = settings()
    if cfg.worker_url:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2

        client = tasks_v2.CloudTasksClient()
        request = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": cfg.worker_url + "/tasks/process",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"owner": owner, "job_id": job_id}).encode(),
            "oidc_token": {"service_account_email": cfg.task_service_account, "audience": cfg.worker_url},
        }
        task = {"http_request": request}
        if delay:
            stamp = timestamp_pb2.Timestamp()
            stamp.FromSeconds(int(time.time() + delay))
            task["schedule_time"] = stamp
        client.create_task(
            parent=client.queue_path(cfg.google_cloud_project, cfg.google_cloud_location, cfg.tasks_queue),
            task=task,
        )
    else:
        pool.submit(process, owner, job_id)


def create(owner, kind, payload, key):
    job_id = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:32]
    created = GenerationJob(id=job_id, kind=kind, payload=payload).model_dump(mode="json")
    record = store().mutate("jobs", owner, job_id, lambda old: old or created)
    if record["status"] == "queued":
        enqueue(owner, job_id)
    return public(record)


def update(owner, key, **fields):
    def change(old):
        if not old or old["status"] == "cancelled":
            raise InterruptedError("Job cancelled")
        return {**old, **fields, "updated_at": now()}

    return store().mutate("jobs", owner, key, change)


def process(owner, key):
    def claim(old):
        if (
            not old
            or old["status"] in ("succeeded", "cancelled", "failed")
            or old.get("lease_until", 0) > time.time()
        ):
            raise InterruptedError("Already processing or finished")
        if old["attempts"] >= 3 and not old.get("operation"):
            raise InterruptedError("Retry limit reached")
        return {
            **old,
            "status": "running",
            "lease_until": time.time() + 180,
            "attempts": old["attempts"] + (0 if old.get("operation") else 1),
            "updated_at": now(),
        }

    try:
        job = store().mutate("jobs", owner, key, claim)
    except InterruptedError:
        return
    progress = lambda stage: update(owner, key, stage=stage)
    result = None
    try:
        kind = job["kind"]
        if kind == "wardrobe":
            result = wardrobe.extract(owner, job["payload"]["photo_ids"], progress)
        elif kind == "garment_image":
            progress("Creating shop-style garment image with Gemini")
            result = garment_images.generate(owner, job["payload"])
        elif kind == "try_on":
            progress("Creating your style visualization")
            result = try_on.generate(owner, job["payload"])
        elif kind == "video":
            progress("Generating motion preview")
            result = video.generate(owner, job, lambda op: update(owner, key, operation=op))
            if result is None:
                if (
                    time.time() - __import__("datetime").datetime.fromisoformat(job["created_at"]).timestamp()
                    > 1800
                ):
                    raise ValueError("Video generation timed out after 30 minutes")
                update(owner, key, lease_until=0)
                if settings().worker_url:
                    enqueue(owner, key, delay=20)
                return
        elif kind == "index":
            from .indexing import index_products

            progress("Indexing catalogue")
            result = index_products(job["payload"]["catalog_owner"], job["payload"]["product_ids"])
        else:
            result = avatars.generate()
        # Cancellation can happen during a provider call: delete any returned media instead of publishing it.
        current = store().get("jobs", owner, key)
        if not current or current["status"] == "cancelled":
            if result and result.get("media_id"):
                from .media import delete

                delete(owner, result["media_id"])
            return
        if kind == "garment_image":
            try:
                garment_images.publish(owner, key, job["payload"], result)
            except Exception:
                from .media import delete

                delete(owner, result["media_id"])
                raise
        update(
            owner,
            key,
            status="succeeded",
            stage="Ready for review" if kind == "wardrobe" else "Complete",
            result=result,
            error=None,
            lease_until=0,
        )
    except InterruptedError:
        if job["kind"] == "garment_image" and result and result.get("media_id"):
            garment_images.discard(owner, job["payload"], result)
        return
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Job failure: kind=%s exception=%s", job["kind"], type(exc).__name__
        )
        message = (
            str(exc)
            if isinstance(exc, (try_on.CapabilityUnavailable, ValueError))
            else "The service could not finish this job. Check provider access and try again. No successful result was fabricated."
        )
        try:
            update(owner, key, status="failed", stage="Needs attention", error=message[:500], lease_until=0)
        except InterruptedError:
            pass
