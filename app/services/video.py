from google.genai import types
from ..config import settings
from ..store import store
from . import ai, media
from .try_on import CapabilityUnavailable


def generate(owner, job, persist):
    cfg = settings()
    if not cfg.enable_paid_ai or not cfg.veo_model:
        raise CapabilityUnavailable("Motion previews are unavailable right now.")
    source = store().get("jobs", owner, job["payload"].get("source_job_id"))
    if (
        not source
        or source["kind"] != "try_on"
        or source["status"] != "succeeded"
        or not source.get("result", {}).get("accepted")
    ):
        raise ValueError("Accept a successful try-on preview first")
    if not cfg.media_bucket:
        raise CapabilityUnavailable("Private Cloud Storage is required for Veo outputs")
    if job.get("operation"):
        with ai.client() as provider:
            operation = provider.operations.get(types.GenerateVideosOperation(name=job["operation"]))
    else:
        raw, mime = media.read(owner, source["result"]["media_id"])
        with ai.client() as provider:
            operation = provider.models.generate_videos(
                model=cfg.veo_model,
                source=types.GenerateVideosSource(
                    prompt="A gentle natural pose change, mostly front-facing. Preserve this adult person’s face, clothing design and proportions. Static camera. No spin, no new objects, no changes of clothing.",
                    image=types.Image(image_bytes=raw, mime_type=mime),
                ),
                config=types.GenerateVideosConfig(
                    number_of_videos=1,
                    duration_seconds=job["payload"].get("duration", 4),
                    aspect_ratio="9:16",
                    output_gcs_uri=f"gs://{cfg.media_bucket}/{owner}/veo/{job['id']}/",
                    person_generation="allow_adult",
                ),
            )
        persist(operation.name)
    if not operation.done:
        return None
    if operation.error:
        raise ValueError("The video provider could not complete this request")
    response = operation.response
    if not response or not response.generated_videos:
        raise ValueError("The video provider returned no video")
    video = response.generated_videos[0].video
    if video.video_bytes:
        raw = video.video_bytes
    elif video.uri and video.uri.startswith(f"gs://{cfg.media_bucket}/{owner}/"):
        from google.cloud import storage

        blob = (
            storage.Client(project=cfg.google_cloud_project)
            .bucket(cfg.media_bucket)
            .blob(video.uri.split("/", 3)[3])
        )
        raw = blob.download_as_bytes()
        blob.delete()
    else:
        raise ValueError("Video provider returned an unexpected storage location")
    return {
        "media_id": media.save(owner, raw, "video/mp4"),
        "provider": "veo",
        "label": "AI-generated video. Review face, garment and proportions. This is not interactive AR.",
        "review_required": True,
        "consistency_check": "Customer review required; not measured automatically",
    }
