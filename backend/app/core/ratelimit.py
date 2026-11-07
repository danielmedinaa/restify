from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.redis import redis_client


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconocido"


async def check_rate_limit(clave: str, limite: int, ventana_seg: int = 60) -> None:
    """Ventana fija sobre Redis. Lanza 429 si se supera el límite."""
    key = f"rl:{clave}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, ventana_seg, nx=True)
        count, _ = await pipe.execute()
    if count > limite:
        # Import diferido: seguridad depende de la BD y ratelimit se importa muy temprano
        from app.services import seguridad

        await seguridad.senal("rate_limit", clave.split(":", 1)[-1], clave=clave.split(":", 1)[0])
        ttl = await redis_client.ttl(key)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiadas solicitudes, intenta más tarde",
            headers={"Retry-After": str(max(ttl, 1))},
        )


def rate_limit(nombre: str, limite: int | Callable[[], int], ventana_seg: int = 60):
    """`limite` puede ser una función para leerlo de la configuración en cada petición."""

    async def dependency(request: Request) -> None:
        tope = limite() if callable(limite) else limite
        await check_rate_limit(f"{nombre}:{client_ip(request)}", tope, ventana_seg)

    return dependency
