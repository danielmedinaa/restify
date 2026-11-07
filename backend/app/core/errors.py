from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder


class NoEncontrado(HTTPException):
    def __init__(self, recurso: str = "Recurso"):
        super().__init__(status.HTTP_404_NOT_FOUND, f"{recurso} no encontrado")


class Conflicto(HTTPException):
    def __init__(self, detalle: str | dict | list):
        super().__init__(status.HTTP_409_CONFLICT, jsonable_encoder(detalle))


class Prohibido(HTTPException):
    def __init__(self, detalle: str = "No tienes permiso para esta acción"):
        super().__init__(status.HTTP_403_FORBIDDEN, detalle)


class NoAutenticado(HTTPException):
    def __init__(self, detalle: str = "No autenticado"):
        super().__init__(status.HTTP_401_UNAUTHORIZED, detalle, headers={"WWW-Authenticate": "Bearer"})


class MesaBloqueada(HTTPException):
    def __init__(self):
        super().__init__(status.HTTP_423_LOCKED, "La mesa ya tiene una comanda abierta")


class Invalido(HTTPException):
    def __init__(self, detalle: str | dict | list):
        super().__init__(status.HTTP_422_UNPROCESSABLE_CONTENT, jsonable_encoder(detalle))
