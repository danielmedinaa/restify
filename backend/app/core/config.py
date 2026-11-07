from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Restify API"
    environment: Literal["development", "production", "test"] = "development"

    database_url: str
    redis_url: str

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    cors_origins: list[str] = []
    trusted_hosts: list[str] = ["*"]

    public_menu_base_url: str = "http://localhost:3000/mesa"
    public_tracking_base_url: str = "http://localhost:3000/pedido"

    timezone: str = "UTC"

    # Impuesto a las Grandes Transacciones Financieras sobre pagos en divisas (%)
    igtf_porcentaje: Decimal = Decimal(3)

    # Pedidos por QR que nadie confirma en estos minutos se cancelan solos (0 = nunca)
    qr_vencimiento_min: int = 15

    # Consulta opcional de cédulas (api.cedula.com.ve). Vacío = desactivada.
    cedula_api_app_id: str = ""
    cedula_api_token: str = ""

    # Control de la suscripción desde el panel de RESTIFY. Vacío = sin restricciones (desarrollo).
    # panel_url es la URL completa del endpoint, ej: https://panel.restify.com.ve/api/v1/estado
    panel_url: str = ""
    panel_token: str = ""
    # Subdominio de esta instancia; si se define, el token del panel debe ser de esa instancia
    instancia_subdominio: str = ""
    licencia_cache_segundos: int = 30
    panel_timeout_segundos: float = 3.0

    login_max_attempts: int = 5
    login_lock_minutes: int = 15
    public_rate_limit_per_minute: int = 60

    media_dir: Path = Path("/app/media")
    media_url_prefix: str = "/media"
    max_image_mb: int = 5
    max_video_mb: int = 50

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
