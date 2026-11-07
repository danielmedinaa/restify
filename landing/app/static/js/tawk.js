/* Chat de Tawk.to (asistente). Los IDs llegan por data-* desde el servidor (.env):
   así el código no vive en línea y la CSP puede seguir prohibiendo scripts en línea. */
(() => {
  "use strict";
  const yo = document.currentScript;
  const propiedad = yo?.dataset.propiedad;
  const widget = yo?.dataset.widget;
  if (!propiedad || !widget || !/^[a-z0-9]+$/i.test(propiedad) || !/^[a-z0-9]+$/i.test(widget)) return;

  window.Tawk_API = window.Tawk_API || {};
  window.Tawk_LoadStart = new Date();

  // Botón del chat sobre el fondo oscuro de RESTIFY
  window.Tawk_API.customStyle = { visibility: { desktop: { position: "br", xOffset: 20, yOffset: 20 }, mobile: { position: "br", xOffset: 12, yOffset: 12 } } };

  const s = document.createElement("script");
  s.async = true;
  s.src = `https://embed.tawk.to/${propiedad}/${widget}`;
  s.charset = "UTF-8";
  s.setAttribute("crossorigin", "*");
  document.head.appendChild(s);
})();
