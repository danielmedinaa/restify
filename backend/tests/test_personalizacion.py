"""Personalización: logo, colores y tipografía. Solo en planes que la incluyen."""

import io

from app.services import licencia
from app.services import personalizacion as srv
from tests.test_licencia import panel  # noqa: F401  (fixture que simula al panel)

API = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_contraste_y_colores():
    assert srv.contraste("#ffffff", "#000000") > 20
    assert srv.validar_colores({"fondo": "#1A1819", "texto": None, "acento": "#C0392B"}) == {"fondo": "#1a1819", "acento": "#c0392b"}
    for malo in ({"fondo": "red"}, {"fondo": "#fff"}, {"fondo": "#1a1819", "texto": "#222222"}, {"fondo": "#1a1819", "acento": "#1b1a1a"}):
        try:
            srv.validar_colores(malo)
        except Exception as e:
            assert getattr(e, "status_code", None) == 422
        else:
            raise AssertionError(malo)


def test_parsea_css_de_google_solo_latin():
    css = """
/* cyrillic */
@font-face { font-family: 'X'; font-style: normal; font-weight: 400; src: url(https://fonts.gstatic.com/s/x/cyr.woff2) format('woff2'); unicode-range: U+0301; }
/* latin */
@font-face { font-family: 'X'; font-style: normal; font-weight: 400; src: url(https://fonts.gstatic.com/s/x/lat.woff2) format('woff2'); unicode-range: U+0000-00FF, U+0131; }
/* latin */
@font-face { font-family: 'X'; font-style: italic; font-weight: 700; src: url(https://evil.example/a.woff2) format('woff2'); }
"""
    caras = srv.parsear_css_google(css)
    assert [c["url"] for c in caras] == ["https://fonts.gstatic.com/s/x/lat.woff2"]
    assert caras[0]["rango"] == "U+0000-00FF, U+0131"


async def test_sin_el_plan_no_se_puede_y_lo_publico_queda_por_defecto(admin, panel):  # noqa: F811
    licencia.reiniciar()
    estado = (await admin.get(f"{API}/personalizacion")).json()
    assert estado["disponible"] is False and estado["plan"] == "Básico"
    r = await admin.put(f"{API}/personalizacion/colores", json={"acento": "#c0392b"})
    assert r.status_code == 402 and r.json()["detail"]["codigo"] == "caracteristica_plan"
    r = await admin.post(f"{API}/personalizacion/logo", files={"archivo": ("l.png", PNG, "image/png")})
    assert r.status_code == 402


async def test_flujo_completo_con_el_plan(admin, panel, tmp_path, monkeypatch):  # noqa: F811
    from app.core.config import settings

    monkeypatch.setattr(settings, "media_dir", tmp_path)
    panel["caracteristicas"]["personalizacion"] = True
    licencia.reiniciar()

    r = await admin.put(f"{API}/personalizacion/colores", json={"acento": "#c0392b", "fondo": "#101010"})
    assert r.status_code == 200 and r.json()["tema"]["colores"]["acento"] == "#c0392b"
    assert (await admin.put(f"{API}/personalizacion/colores", json={"fondo": "#101010", "texto": "#111111"})).status_code == 422

    # Logo: PNG sí, SVG y disfrazados no
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    assert (await admin.post(f"{API}/personalizacion/logo", files={"archivo": ("l.svg", svg, "image/svg+xml")})).status_code == 422
    r = await admin.post(f"{API}/personalizacion/logo", files={"archivo": ("l.png", io.BytesIO(PNG), "image/png")})
    assert r.status_code == 200
    url = r.json()["tema"]["logo_url"]
    assert url.startswith("/media/marca-") and (tmp_path / url.rsplit("/", 1)[1]).exists()
    viejo = url.rsplit("/", 1)[1]
    r = await admin.post(f"{API}/personalizacion/logo", files={"archivo": ("l2.png", io.BytesIO(PNG), "image/png")})
    assert not (tmp_path / viejo).exists()  # el logo anterior se borra

    # Fuente propia: WOFF2 sí, cualquier otra cosa no
    woff2 = b"wOF2" + b"0" * 64
    assert (await admin.post(f"{API}/personalizacion/fuente/titulo/archivo", data={"familia": "Mi Fuente"}, files={"archivo": ("f.woff2", woff2, "font/woff2")})).status_code == 200
    r = await admin.post(f"{API}/personalizacion/fuente/texto/archivo", data={"familia": "Mala"}, files={"archivo": ("f.woff2", b"MZ" + b"0" * 64, "font/woff2")})
    assert r.status_code == 422

    # Restablecer todo: vuelve al tema original y borra los archivos
    guardados = {p.name for p in tmp_path.iterdir()}
    assert guardados
    r = await admin.delete(f"{API}/personalizacion")
    assert r.status_code == 200 and r.json()["tema"]["logo_url"] is None and r.json()["tema"]["titulo"] is None
    assert not any(tmp_path.iterdir())
    await admin.put(f"{API}/personalizacion/colores", json={"acento": "#c0392b"})
    await admin.post(f"{API}/personalizacion/logo", files={"archivo": ("l.png", io.BytesIO(PNG), "image/png")})
    await admin.post(f"{API}/personalizacion/fuente/titulo/archivo", data={"familia": "Mi Fuente"}, files={"archivo": ("f.woff2", woff2, "font/woff2")})

    # Lo ve cualquiera sin sesión (carta pública, login), pero solo mientras el plan la incluya
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost", headers={"X-API-Key": admin.headers["X-API-Key"]}) as anon:
        t = (await anon.get(f"{API}/public/tema")).json()
        assert t["logo_url"] and t["titulo"]["familia"] == "Mi Fuente" and t["colores"]["acento"] == "#c0392b"
        panel["caracteristicas"]["personalizacion"] = False
        licencia.reiniciar()
        t = (await anon.get(f"{API}/public/tema")).json()
        assert t["logo_url"] is None and t["titulo"] is None and not any(t["colores"].values())
