from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Canvas
    canvas_base_url: str = "https://canvas.instructure.com"
    canvas_access_token: str = ""
    canvas_account_id: str = "1"

    # Azure
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # App
    port: int = 3000
    environment: str = "development"


settings = Settings()
