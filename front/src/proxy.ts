import { NextResponse, type NextRequest } from "next/server";

/**
 * Guard optimista: sin cookie de sesión, el panel y la cocina mandan al login.
 * La validación real la hace el BFF en cada llamada (y el backend detrás).
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has("rs_session")) return NextResponse.next();
  const login = new URL("/login", request.url);
  const destino = request.nextUrl.pathname + request.nextUrl.search;
  if (destino !== "/panel") login.searchParams.set("next", destino);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/panel/:path*", "/cocina/:path*"],
};
