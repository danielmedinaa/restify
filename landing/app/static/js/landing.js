/* RESTIFY · Landing. Sin dependencias: aparición al hacer scroll, la sala viva del
   hero, el medidor de stock, el flujo de una comanda y el formulario de demo. */
(() => {
  "use strict";

  const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

  /* ------------------------------------------------------------ navegación */
  const nav = $("[data-nav]");
  const alScroll = () => nav && nav.classList.toggle("nav--solida", window.scrollY > 24);
  alScroll();
  window.addEventListener("scroll", alScroll, { passive: true });

  /* ------------------------------------------------------------ aparición */
  // Solo se ocultan los elementos que al cargar están por debajo del borde
  const bordeInferior = window.innerHeight;
  const observador = new IntersectionObserver(
    (entradas) => {
      for (const e of entradas) {
        if (!e.isIntersecting) continue;
        e.target.classList.remove("oculto");
        e.target.classList.add("visto");
        observador.unobserve(e.target);
      }
    },
    { rootMargin: "0px 0px -8% 0px" },
  );
  $$(".revelar").forEach((el) => {
    if (el.closest(".hero")) return;
    if (!quieto && el.getBoundingClientRect().top > bordeInferior) el.classList.add("oculto");
    observador.observe(el);
  });

  /* Ejecuta fn mientras el elemento esté en pantalla (y se detiene fuera de ella).
     Corre también con movimiento reducido: solo cambia colores y textos, no desplaza. */
  function mientrasVisible(el, fn, cada) {
    if (!el) return;
    let timer = null;
    new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !timer) {
        fn();
        timer = setInterval(fn, cada);
      } else if (!e.isIntersecting && timer) {
        clearInterval(timer);
        timer = null;
      }
    }).observe(el);
  }

  /* ------------------------------------------------------------ sala viva */
  const ESTADOS = {
    libre: "Libre",
    ocupada: "Ocupada",
    servir: "Platos listos",
    pago: "Esperando pago",
  };
  // El ciclo natural de una mesa durante el servicio
  const SIGUIENTE = { libre: "ocupada", ocupada: "servir", servir: "pago", pago: "libre" };
  const INICIAL = ["ocupada", "libre", "servir", "ocupada", "pago", "libre", "ocupada", "libre", "libre", "servir", "ocupada", "libre"];

  const sala = $("[data-sala]");
  const kpiOcupadas = $("[data-kpi-ocupadas]");
  const kpiVentas = $("[data-kpi-ventas]");
  let ventas = 1284;

  function pintarMesa(mesa, estado) {
    mesa.dataset.estado = estado;
    $(".mesa__estado b", mesa).textContent = ESTADOS[estado];
  }

  if (sala) {
    const mesas = $$(".mesa", sala);
    mesas.forEach((m, i) => pintarMesa(m, INICIAL[i] || "libre"));
    const contar = () => {
      if (kpiOcupadas) kpiOcupadas.textContent = mesas.filter((m) => m.dataset.estado !== "libre").length;
    };
    contar();

    mientrasVisible(
      sala,
      () => {
        const mesa = mesas[Math.floor(Math.random() * mesas.length)];
        const nuevo = SIGUIENTE[mesa.dataset.estado];
        mesa.classList.add("mesa--cambio");
        setTimeout(() => {
          pintarMesa(mesa, nuevo);
          mesa.classList.remove("mesa--cambio");
          if (nuevo === "libre" && kpiVentas) {
            ventas += 12 + Math.floor(Math.random() * 40);
            kpiVentas.textContent = ventas.toLocaleString("es-VE");
          }
          contar();
        }, 220);
      },
      1700,
    );
  }

  /* El plato #2 de cocina pasa a listo y vuelve, para que se vea vivo */
  const tiquete = $("[data-tiquete]");
  mientrasVisible(
    tiquete,
    () => {
      const listo = tiquete.toggleAttribute("data-listo");
      $("b", tiquete).textContent = listo ? "Lista" : "Preparando";
    },
    3200,
  );

  /* Timer de la pantalla de cocina */
  const timer = $("[data-timer]");
  if (timer) {
    let seg = 4 * 60 + 12;
    mientrasVisible(
      timer,
      () => {
        seg += 1;
        timer.textContent = `${String(Math.floor(seg / 60)).padStart(2, "0")}:${String(seg % 60).padStart(2, "0")}`;
      },
      1000,
    );
  }

  /* ------------------------------------------------------------ medidor de stock */
  const medidor = $("[data-medidor]");
  if (medidor) {
    const gramos = $("[data-gramos]", medidor);
    const barra = $("[data-barra]", medidor);
    const nota = $("[data-medidor-nota]", medidor);

    const animarCifra = (desde, hasta, ms) => {
      const t0 = performance.now();
      const paso = (t) => {
        const p = Math.min(1, (t - t0) / ms);
        const suave = 1 - Math.pow(1 - p, 3);
        gramos.textContent = Math.round(desde + (hasta - desde) * suave);
        if (p < 1) requestAnimationFrame(paso);
      };
      requestAnimationFrame(paso);
    };

    mientrasVisible(
      medidor,
      () => {
        medidor.classList.remove("medidor--bajo");
        gramos.textContent = "200";
        barra.style.width = "100%";
        nota.textContent = "Se vende una hamburguesa de 150 g…";
        setTimeout(() => {
          barra.style.width = "25%";
          animarCifra(200, 50, 1400);
          setTimeout(() => {
            medidor.classList.add("medidor--bajo");
            nota.textContent = "Quedan 50 g, debajo del mínimo: alerta enviada a caja.";
          }, 1400);
        }, 900);
      },
      6500,
    );
  }

  /* ------------------------------------------------------------ flujo de una comanda */
  const flujo = $("[data-flujo]");
  if (flujo) {
    const pasos = $$(".flujo__paso", flujo);
    const progreso = $("[data-flujo-progreso]", flujo);
    const horizontal = window.matchMedia("(min-width: 900px)");
    let actual = -1;

    const pintar = () => {
      pasos.forEach((p, i) => {
        p.classList.toggle("activo", i === actual);
        p.classList.toggle("hecho", i < actual);
      });
      const pct = `${(Math.max(actual, 0) / (pasos.length - 1)) * 100}%`;
      progreso.style.width = horizontal.matches ? pct : "";
      progreso.style.height = horizontal.matches ? "" : pct;
    };

    mientrasVisible(
      flujo,
      () => {
        actual = (actual + 1) % (pasos.length + 1); // una pausa al final antes de reiniciar
        if (actual === pasos.length) actual = -1;
        pintar();
      },
      2100,
    );
  }

  /* ------------------------------------------------------------ formulario de demo */
  const form = $("[data-formulario]");
  if (form) {
    const enviar = $("[data-enviar]", form);
    const general = $("[data-error-general]", form);
    const textoBoton = enviar.innerHTML;

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      general.textContent = "";
      $$("[data-error]", form).forEach((s) => (s.textContent = ""));
      $$(".campo--error", form).forEach((c) => c.classList.remove("campo--error"));

      const datos = Object.fromEntries(new FormData(form));
      if (!datos.nombre || datos.nombre.trim().length < 2) return marcar({ nombre: "Escribe tu nombre." });
      if (!/^\+?[0-9 ()-]{7,20}$/.test((datos.telefono || "").trim())) {
        return marcar({ telefono: "Escribe un teléfono válido, por ejemplo +58 412 000 0000." });
      }

      enviar.disabled = true;
      enviar.textContent = "Enviando…";
      try {
        const res = await fetch(form.action.split("#")[0], {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": datos.csrf },
          body: JSON.stringify(datos),
          credentials: "same-origin",
        });
        const cuerpo = await res.json().catch(() => ({}));
        if (res.ok) {
          $("[data-campos]", form).hidden = true;
          $("[data-ok]", form).hidden = false;
          return;
        }
        if (cuerpo.errores) return marcar(cuerpo.errores);
        general.textContent = cuerpo.mensaje || "No pudimos enviar tu solicitud. Escríbenos por WhatsApp.";
      } catch {
        general.textContent = "Sin conexión. Revisa tu internet o escríbenos por WhatsApp.";
      } finally {
        enviar.disabled = false;
        enviar.innerHTML = textoBoton;
      }
    });

    function marcar(errores) {
      let primero = null;
      for (const [campo, msg] of Object.entries(errores)) {
        const s = $(`[data-error="${campo}"]`, form);
        if (s) {
          s.textContent = msg;
          s.closest(".campo")?.classList.add("campo--error");
          primero ??= $(`[name="${campo}"]`, form);
        }
      }
      primero?.focus();
    }
  }
})();
