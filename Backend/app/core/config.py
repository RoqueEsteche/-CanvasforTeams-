import logging
import warnings

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "changeme-please-set-a-secret"


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
    azure_sku_students: str = "STANDARDWOFFPACK_STUDENT"
    azure_sku_teachers: str = "STANDARDWOFFPACK_FACULTY"

    # App
    port: int = 3000
    environment: str = "development"
    site_url: str = "http://localhost:3000"
    secret_key: str = _DEFAULT_SECRET
    auth_cookie_name: str = "usil_auth"

    # Institutional domain & defaults
    institutional_domain: str = "usil.edu.py"
    usage_location: str = "PY"
    teams_url: str = "https://teams.microsoft.com"

    # Email (Graph API – smtp_from debe ser un buzón válido del tenant)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@usil.edu.py"
    smtp_from_name: str = "Roque Esteche"
    # CC separados por coma, ej: "director@usil.edu.py,rectorado@usil.edu.py"
    email_cc: str = ""

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == _DEFAULT_SECRET:
            msg = (
                "SECRET_KEY usa el valor por defecto inseguro. "
                "Establece SECRET_KEY en el archivo .env antes de desplegar en producción."
            )
            warnings.warn(msg, stacklevel=2)
            logger.warning(msg)
        return v

    @property
    def is_insecure_secret(self) -> bool:
        return self.secret_key == _DEFAULT_SECRET


settings = Settings()
