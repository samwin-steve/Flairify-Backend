from functools import lru_cache
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
    embedding_model: str = ""
    try_on_model: str = ""
    image_edit_model: str = ""
    image_edit_location: str = "global"
    allow_sample_try_on: bool = False
    max_daily_image_generations: int = 30
    veo_model: str = ""
    enable_paid_ai: bool = False
    google_photos_client_id: str = ""
    worker_url: str = ""
    task_service_account: str = ""
    tasks_queue: str = "flairify-jobs"
    bigquery_dataset: str = "flairify"
    enable_bigquery: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_upload_mb: int = 10
    max_photos_per_user: int = 30
    max_daily_generations: int = 5
    enable_demo_admin: bool = True
    demo_admin_key: str = ""

    @property
    def ai_ready(self):
        return self.enable_paid_ai and bool(self.gemini_model)


@lru_cache
def settings():
    config = Settings()
    if config.app_mode not in ("demo", "production"):
        raise ValueError("APP_MODE must be demo or production")
    if config.app_mode == "production" and (config.store_backend != "firestore" or not config.media_bucket):
        raise ValueError("Production requires Firestore and a private Cloud Storage bucket")
    return config
