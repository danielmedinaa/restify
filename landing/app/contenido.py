"""Textos de la landing. Todo lo que dice la página vive aquí: edítalo sin tocar el HTML.

En los textos, *palabra* se muestra resaltada (cursiva en Gagalin).
"""

CINTA = [
    "Pago móvil",
    "Zelle",
    "Binance",
    "Efectivo en $ y Bs",
    "Tasa BCV",
    "Menú QR por mesa",
    "Cocina en vivo",
    "Stock por gramo",
    "Datos para factura SENIAT",
    "Multi-sucursal",
]

HERO = {
    "eyebrow": "Sistema para restaurantes · Venezuela",
    "titulo": "Tu restaurante, *en sincronía*.",
    "texto": (
        "Comandas, cocina, caja e inventario en una sola pantalla. El cliente pide desde el QR de su mesa, "
        "cocina ve cada plato al instante y el stock se descuenta solo, gramo a gramo."
    ),
    "insignias": ["Cobra en $ y Bs a tasa BCV", "Inventario que avisa", "Menú QR por mesa", "Listo para facturar"],
}

PROBLEMAS = [
    {
        "titulo": "Comandas en papel",
        "texto": "Letra ilegible, platos que nunca llegan a cocina y mesas que esperan sin saber por qué.",
    },
    {
        "titulo": "El stock se va sin aviso",
        "texto": "Te enteras de que no hay carne cuando el cliente ya pidió la hamburguesa.",
    },
    {
        "titulo": "Cobrar es un rompecabezas",
        "texto": "Una parte en dólares, otra en pago móvil, la tasa cambió y alguien quiere dividir la cuenta.",
    },
    {
        "titulo": "No sabes cuánto vendiste",
        "texto": "Cerrar el día es sumar tickets a mano y adivinar qué plato se vende más.",
    },
]

FUNCIONES = [
    {
        "clave": "qr",
        "titulo": "Menú QR que se actualiza solo",
        "texto": (
            "Cada mesa tiene su QR. El cliente ve fotos, videos y precios en su moneda, y el menú esconde "
            "lo que ya no puedes preparar."
        ),
    },
    {
        "clave": "cocina",
        "titulo": "Cocina en tiempo real",
        "texto": "Cada plato llega a la pantalla de cocina con su nota. Un toque y queda listo: caja y cliente lo ven al instante.",
    },
    {
        "clave": "stock",
        "titulo": "Inventario por gramo",
        "texto": (
            "Recetas con cantidades exactas. Vendes una hamburguesa de 150 g y se descuentan 150 g; "
            "si queda poco, te avisa."
        ),
    },
    {
        "clave": "caja",
        "titulo": "Caja multimoneda",
        "texto": "Cobra mezclando dólares, bolívares y métodos. Divide la cuenta por partes iguales o por platos.",
    },
    {
        "clave": "ventas",
        "titulo": "Ventas claras",
        "texto": "Por día, mes o año, ticket promedio y lo más vendido. Cada venta conserva su comanda y sus pagos.",
    },
    {
        "clave": "factura",
        "titulo": "Listo para facturar",
        "texto": "Datos fiscales armados con IVA, IGTF y total en Bs a la tasa pagada, más tu libro de ventas en Excel.",
    },
]

EXTRAS = ["Roles y permisos por módulo", "Varias sucursales", "Precios por sucursal", "Registro de clientes", "Auditoría de cada acción", "Funciona en tablet, PC y celular"]

FLUJO = [
    {"paso": "Escanea", "texto": "El cliente pide desde el QR de su mesa. La mesa queda bloqueada para que nadie más pida en ella."},
    {"paso": "Aprueba", "texto": "Caja revisa y envía a cocina. El stock de la receta queda reservado."},
    {"paso": "Prepara", "texto": "Cocina marca cada plato listo y el inventario se descuenta en ese momento."},
    {"paso": "Cobra", "texto": "Caja cobra en las monedas que sean, cierra la mesa y la venta queda registrada."},
]

# Precios de ejemplo: ajústalos a tu oferta real antes de publicar.
PLANES = [
    {
        "nombre": "Esencial",
        "precio": "29",
        "periodo": "/mes",
        "desde": True,
        "para": "Para cafés y locales pequeños.",
        "incluye": [
            "1 sucursal · hasta 15 mesas",
            "Comandas y caja multimoneda",
            "Menú QR por mesa",
            "Inventario con alertas",
            "3 usuarios",
        ],
        "cta": "Empezar",
    },
    {
        "nombre": "Restaurante",
        "precio": "59",
        "periodo": "/mes",
        "desde": True,
        "destacado": True,
        "para": "El sistema completo para un local.",
        "incluye": [
            "1 sucursal · mesas ilimitadas",
            "Pantalla de cocina en vivo",
            "Recetas y stock por gramo",
            "Roles y permisos",
            "Datos para facturar + libro de ventas",
            "Usuarios ilimitados",
        ],
        "cta": "Lo quiero",
    },
    {
        "nombre": "Cadena",
        "precio": "99",
        "periodo": "/mes",
        "desde": True,
        "para": "Para marcas con varias sedes.",
        "incluye": [
            "Hasta 3 sucursales",
            "Precios e inventario por sucursal",
            "Reportes de todas las sedes",
            "Usuarios por sucursal",
            "Soporte prioritario",
        ],
        "cta": "Lo quiero",
    },
    {
        "nombre": "A medida",
        "precio": None,
        "para": "Cuando necesitas algo más.",
        "incluye": [
            "Sucursales ilimitadas",
            "Facturación digital con imprenta autorizada",
            "Integraciones a tu medida",
            "Servidor dedicado",
        ],
        "cta": "Cotizar",
    },
]

NOTAS_PLANES = [
    "Implementación y carga de tu menú, recetas e inventario: pago único, según el tamaño del local.",
    "Puedes pagar en bolívares a la tasa BCV del día.",
]

PROCESO = [
    {"tiempo": "Día 01", "titulo": "Conversamos", "texto": "Te mostramos RESTIFY con tu menú en mente y vemos qué plan te sirve."},
    {"tiempo": "Días 02–04", "titulo": "Cargamos todo", "texto": "Menú, fotos, recetas, inventario, mesas y usuarios. Tú solo revisas."},
    {"tiempo": "Día 05", "titulo": "Capacitamos", "texto": "Una sesión con caja, meseros y cocina. Imprimimos los QR de tus mesas."},
    {"tiempo": "Día 06", "titulo": "Abres con RESTIFY", "texto": "Te acompañamos el primer servicio y quedamos a un mensaje de distancia."},
]

RAZONES = [
    {"titulo": "Seguro de verdad", "texto": "Accesos por rol, sesiones cifradas, auditoría de cada acción. Tus números son tuyos."},
    {"titulo": "En tiempo real", "texto": "Caja, cocina y salón ven lo mismo en el mismo segundo. Sin recargar la página."},
    {"titulo": "Pensado para Venezuela", "texto": "Varias monedas, tasa BCV, pago móvil, IGTF e IVA desde el primer día."},
    {"titulo": "Soporte directo", "texto": "Hablas con quien construye el sistema. Respuesta en menos de 24 horas."},
]

FAQS = [
    {
        "p": "¿Tengo que instalar algo?",
        "r": "No. RESTIFY funciona en el navegador de cualquier PC, tablet o celular. Para cocina recomendamos una tablet o una TV con navegador.",
    },
    {
        "p": "¿Mis clientes tienen que descargar una app?",
        "r": "No. Escanean el QR de la mesa con la cámara y el menú abre en su navegador. El QR es opcional: caja también puede tomar los pedidos.",
    },
    {
        "p": "¿Puedo cobrar en dólares y bolívares a la vez?",
        "r": "Sí. Cargas tus monedas con su tasa y cobras mezclando monedas y métodos. Cada pago guarda la tasa con la que se hizo.",
    },
    {
        "p": "¿Emite factura fiscal?",
        "r": (
            "RESTIFY arma los datos para tu factura (IVA, IGTF y total en Bs) y te da el libro de ventas. La factura la emites con tu "
            "talonario o máquina fiscal. En el plan A medida lo integramos con una imprenta digital autorizada."
        ),
    },
    {
        "p": "¿Qué pasa si se acaba un ingrediente?",
        "r": "El menú deja de ofrecer los platos que ya no puedes preparar y te llega una alerta cuando un insumo baja de su mínimo.",
    },
    {
        "p": "¿Funciona sin internet?",
        "r": "Necesita conexión, como un punto de venta. Con datos móviles de respaldo es suficiente para seguir operando.",
    },
    {
        "p": "¿Cuánto tarda en estar listo?",
        "r": "Alrededor de una semana, desde que nos pasas el menú hasta tu primer servicio con RESTIFY.",
    },
]

CIERRE = {
    "titulo": "Tu próxima noche llena, *sin caos*.",
    "texto": "Agenda una demo de 20 minutos. Te mostramos RESTIFY funcionando con un menú como el tuyo.",
}
