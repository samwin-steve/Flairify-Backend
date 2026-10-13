from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_mode: str = "demo"
    store_backend: str = "sqlite"
    data_dir: str = ".data"
    google_cloud_project: str = "data-workshops"
    google_cloud_location: str = "us-central1"
    gemini_location: str = ""
    allow_firebase_in_demo: bool = False
    seed_sample_catalog: bool = False
    firestore_database: str = "(default)"
    media_bucket: str = ""
    gemini_model: str = ""
    live_model: str = ""
    live_location: str = "us-central1"
    live_voice: str = "Aoede"
    live_api_url: str = ""
    max_live_seconds: int = Field(default=300, ge=30, le=600)
    embedding_model: str = "gemini-embedding-2"
    embedding_location: str = "global"
    embedding_dimensions: int = Field(default=768, ge=128, le=2048)
    max_daily_embeddings: int = 1500
    enable_catalogue_enrichment: bool = True
    max_daily_catalogue_enrichments: int = Field(default=600, ge=1, le=10000)
    try_on_model: str = ""
    image_edit_model: str = ""
    image_edit_location: str = "global"
    allow_sample_try_on: bool = False
    max_daily_image_generations: int = 30
    enable_garment_images: bool = True
    max_daily_garment_images: int = 12
    veo_model: str = ""
    enable_paid_ai: bool = False
    google_photos_client_id: str = ""
    worker_url: str = ""
    task_service_account: str = ""
    tasks_queue: str = "flairify-jobs"
    bigquery_dataset: str = "flairify"
    enable_bigquery: bool = False
    max_daily_graph_queries: int = 300
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_upload_mb: int = 10
    max_photos_per_user: int = 30
    max_daily_generations: int = 5
    enable_demo_admin: bool = True
    demo_admin_key: str = ""

    @property
    def ai_ready(self):
        return self.enable_paid_ai and bool(self.gemini_model)

    @property
    def voice_ready(self):
        return self.ai_ready and bool(self.live_model)


@lru_cache
def settings():
    config = Settings()
    if config.app_mode not in ("demo", "production"):
        raise ValueError("APP_MODE must be demo or production")
    if config.app_mode == "production" and (config.store_backend != "firestore" or not config.media_bucket):
        raise ValueError("Production requires Firestore and a private Cloud Storage bucket")
    return config
