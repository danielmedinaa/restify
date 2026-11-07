from sqlalchemy import func, select

from app.cli import sembrar_demo
from app.core.database import SessionLocal
from app.models import Categoria, Estacion, Insumo, Inventario, Producto, ProductoMedio

API = "/api/v1"


async def test_sembrar_demo_crea_menu_con_estaciones_fotos_y_stock(admin, datos):
    c, d = admin, datos
    # BD limpia de negocio pero con sucursal y estaciones, como queda tras la limpieza
    async with SessionLocal() as s:
        for t in ("comanda_items", "comandas", "receta_insumos", "productos", "recetas", "categorias", "inventario", "insumos"):
            await s.execute(__import__("sqlalchemy").text(f"TRUNCATE {t} RESTART IDENTITY CASCADE"))
        await s.commit()
    await c.post(f"{API}/estaciones", json={"nombre": "Cocina"})
    await c.post(f"{API}/estaciones", json={"nombre": "Barra", "orden": 1})

    await sembrar_demo()

    async with SessionLocal() as s:
        productos = list((await s.scalars(select(Producto))).unique().all())
        assert len(productos) == 10
        por_nombre = {p.nombre: p for p in productos}
        assert por_nombre["Pepsi"].estacion.nombre == "Barra" and por_nombre["Hamburguesa doble"].estacion.nombre == "Cocina"
        con_foto = [p for p in productos if p.medios]
        assert len(con_foto) == 9 and not por_nombre["Tequeños (6)"].medios
        assert all(m.url.startswith("https://") and m.es_portada for p in con_foto for m in p.medios)
        # Los ingredientes se pueden quitar solo donde corresponde
        clasica = por_nombre["Hamburguesa clásica"].receta
        quitables = {ri.insumo.nombre for ri in clasica.ingredientes if ri.removible}
        assert quitables == {"Queso amarillo", "Lechuga", "Tomate", "Cebolla", "Salsa de la casa"}
        assert await s.scalar(select(func.count()).select_from(Inventario)) == 19
        assert (await s.scalar(select(Categoria).where(Categoria.nombre == "Bebidas"))).estacion_id == por_nombre["Pepsi"].estacion_id

    # Y no se vuelve a sembrar encima de datos existentes
    import pytest

    with pytest.raises(SystemExit):
        await sembrar_demo()
