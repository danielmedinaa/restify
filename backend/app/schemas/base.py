from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, extra="forbid")


class Pagina(Schema, Generic[T]):
    total: int
    limite: int
    offset: int
    items: list[T]


Nombre = Annotated[str, StringConstraints(min_length=1, max_length=120)]
TextoCorto = Annotated[str, StringConstraints(max_length=255)]
MontoPositivo = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
MontoNoNegativo = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
CantidadPositiva = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
CantidadNoNegativa = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]
