// Nombre del ambiente para el banner fijo ("DESARROLLO", "PRE PRODUCCION"). Vacío en producción.
// Se lee al ARRANCAR el contenedor (BANNER_ENTORNO en front.env), no al compilar: la misma imagen sirve para los 3 ambientes.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ banner: process.env.BANNER_ENTORNO ?? "" }, { headers: { "Cache-Control": "no-store" } });
}
