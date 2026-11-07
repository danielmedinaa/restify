"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { Field } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Segmented";
import { Select } from "@/components/ui/Select";
import { TextArea } from "@/components/ui/TextArea";
import { Toggle } from "@/components/ui/Toggle";
import { can, useMe } from "@/features/auth/useMe";
import { bool, FormSheet, txt } from "@/features/crud/crud";
import { api } from "@/lib/api/client";
import { describeError, type ErrorView } from "@/lib/api/errors";
import { CategoriaOut, EstacionOut, InsumoOut, RecetaOut, type Producto } from "@/lib/api/schemas";
import { useUnidades } from "@/features/inventario/useUnidades";
import { parseAmountInput } from "@/lib/money";

/** "16.00" -> "16" · "12.50" -> "12,5" para el campo. */
function alicuotaInicial(v: string | undefined): string {
  return v ? String(Number(v)).replace(".", ",") : "16";
}

/** Datos base del producto (crear o editar). Precio en la moneda principal. */
export function ProductoForm({
  state,
  onOpenChange,
  pending,
  error,
  setError,
  onGuardar,
}: {
  state: { item: Producto | null; key: number; open: boolean };
  onOpenChange: (o: boolean) => void;
  pending: boolean;
  error: ErrorView | null;
  setError: (e: ErrorView | null) => void;
  onGuardar: (v: { id?: number; body: Record<string, unknown> }) => void;
}) {
  const { data: me } = useMe();
  const categorias = useQuery({ queryKey: ["categorias"], queryFn: () => api("/categorias", { schema: z.array(CategoriaOut) }), enabled: can(me, "categorias") });
  const estaciones = useQuery({ queryKey: ["estaciones"], queryFn: () => api("/estaciones", { schema: z.array(EstacionOut) }), enabled: can(me, "categorias") });
  const recetas = useQuery({ queryKey: ["recetas"], queryFn: () => api("/recetas", { schema: z.array(RecetaOut) }), enabled: can(me, "recetas") });
  const insumos = useQuery({ queryKey: ["insumos"], queryFn: () => api("/insumos", { schema: z.array(InsumoOut) }), enabled: can(me, "insumos") });
  const un = useUnidades();
  const p = state.item;
  // Cómo descuenta inventario: por receta (plato), directo de un insumo (Pepsi, agua) o nada (servicio)
  const [modo, setModo] = useState<"receta" | "directo" | "ninguno">(p?.control_stock ?? "ninguno");
  const [insumoSel, setInsumoSel] = useState(p?.insumo_id ? String(p.insumo_id) : "");
  const insumo = insumos.data?.find((i) => String(i.id) === insumoSel);
  return (
    <FormSheet
      key={state.key}
      open={state.open}
      onOpenChange={onOpenChange}
      title={p ? p.nombre : "Nuevo producto"}
      pending={pending}
      error={error}
      onClearError={() => setError(null)}
      onSubmit={async (f) => {
        const precio = parseAmountInput(txt(f, "precio_base") ?? "");
        const cat = txt(f, "categoria_id");
        const rec = txt(f, "receta_id");
        const est = txt(f, "estacion_id");
        const body: Record<string, unknown> = {
          nombre: txt(f, "nombre"),
          codigo_barras: txt(f, "codigo_barras"),
          descripcion: txt(f, "descripcion"),
          categoria_id: cat ? Number(cat) : null,
          receta_id: modo === "receta" && rec ? Number(rec) : null,
          insumo_id: null as number | null,
          cantidad_por_venta: "1",
          estacion_id: est ? Number(est) : null,
          precio_base: precio,
          alicuota_iva: f.get("con_iva") === "no" ? "0" : (parseAmountInput(txt(f, "alicuota_iva") ?? "") ?? ""),
          orden: Number(txt(f, "orden") ?? 0),
          activo: bool(f, "activo"),
        };
        const codigo = txt(f, "codigo")?.toUpperCase();
        if (codigo) body.codigo = codigo; // vacío = lo genera el sistema (PRD-0001)
        if (!body.nombre) return setError({ title: "Ponle un nombre", tone: "warn" });
        if (!precio) return setError({ title: "Escribe un precio válido", tone: "warn" });
        const iva = Number(body.alicuota_iva);
        if (body.alicuota_iva === "" || !(iva >= 0 && iva <= 100)) return setError({ title: "El IVA debe ser un porcentaje entre 0 y 100", tone: "warn" });
        if (modo === "directo") {
          const cant = (txt(f, "cantidad_por_venta") ?? "1").replace(",", ".");
          if (!/^\d+(\.\d{1,3})?$/.test(cant) || Number(cant) <= 0) return setError({ title: "Cuánto descuenta cada venta debe ser mayor que cero", tone: "warn" });
          body.cantidad_por_venta = cant;
          if (insumoSel === "nuevo") {
            // Producto de reventa nuevo: se crea su insumo con el mismo nombre
            const unidad = txt(f, "unidad_nueva") ?? "unidad";
            try {
              const creado = await api("/insumos", { method: "POST", body: { nombre: body.nombre, unidad }, schema: InsumoOut });
              body.insumo_id = creado.id;
            } catch (e) {
              return setError(describeError(e));
            }
          } else if (insumoSel) body.insumo_id = Number(insumoSel);
          else return setError({ title: "Elige el insumo que descuenta este producto", tone: "warn" });
        }
        if (modo === "receta" && !body.receta_id) return setError({ title: "Elige la receta o cambia el control de stock", tone: "warn" });
        if (!can(me, "categorias")) delete body.categoria_id;
        if (!can(me, "recetas")) delete body.receta_id;
        if (!can(me, "categorias")) delete body.estacion_id;
        onGuardar(p ? { id: p.id, body } : { body });
      }}
    >
      <Field name="nombre" label="Nombre" defaultValue={p?.nombre ?? ""} maxLength={120} autoFocus />
      <div className="grid grid-cols-2 gap-4">
        <Field name="codigo" label="Código interno" defaultValue={p?.codigo ?? ""} maxLength={30} placeholder="Automático" />
        <Field name="codigo_barras" label="Código de barras" defaultValue={p?.codigo_barras ?? ""} maxLength={64} inputMode="numeric" placeholder="Opcional" />
      </div>
      <TextArea name="descripcion" label="Descripción" defaultValue={p?.descripcion ?? ""} maxLength={2000} placeholder="Lo que el cliente lee en el menú" />
      <Field name="precio_base" label="Precio base" inputMode="decimal" defaultValue={p?.precio_base.replace(".", ",") ?? ""} hint="En la moneda principal, con IVA incluido. Cada sucursal puede tener su propio precio." />
      <IvaField inicial={p?.alicuota_iva} />
      {can(me, "categorias") && (
        <Select
          name="categoria_id"
          label="Categoría"
          defaultValue={p?.categoria?.id ?? ""}
          onChange={(e) => {
            // Producto nuevo: la estación sigue a la categoría (Bebidas -> Barra) hasta que se cambie a mano
            const est = categorias.data?.find((c) => String(c.id) === e.currentTarget.value)?.estacion_id;
            const campo = e.currentTarget.form?.elements.namedItem("estacion_id");
            if (!p && campo instanceof HTMLSelectElement) campo.value = est ? String(est) : "";
          }}
        >
          <option value="">Sin categoría (Otros)</option>
          {categorias.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nombre}
            </option>
          ))}
        </Select>
      )}
      {can(me, "categorias") && (
        <Select name="estacion_id" label="Se prepara en" defaultValue={p?.estacion?.id ?? ""} hint="La pantalla de esa estación recibe el plato (cocina, barra…).">
          <option value="">Todas las estaciones</option>
          {estaciones.data?.filter((e) => e.activa || e.id === p?.estacion?.id).map((e) => (
            <option key={e.id} value={e.id}>
              {e.nombre}
            </option>
          ))}
        </Select>
      )}
      <fieldset className="flex flex-col gap-3">
        <legend className="eyebrow pb-1">Inventario</legend>
        <Segmented
          label="Cómo descuenta inventario"
          size="sm"
          value={modo}
          onChange={setModo}
          options={[
            { value: "receta", label: "Con receta" },
            { value: "directo", label: "Producto directo" },
            { value: "ninguno", label: "No descuenta" },
          ]}
        />
        {modo === "receta" && can(me, "recetas") && (
          <Select name="receta_id" label="Receta" defaultValue={p?.receta_id ?? ""} hint="Cada venta descuenta los ingredientes de la receta, y el menú limita las porciones según el stock.">
            <option value="">Elige una receta…</option>
            {recetas.data?.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nombre}
              </option>
            ))}
          </Select>
        )}
        {modo === "directo" && (
          <>
            <p className="text-sm text-fg-3">Para lo que se vende tal cual, sin prepararlo (Pepsi, agua, cerveza): cada venta descuenta su propio insumo, sin receta.</p>
            <Select label="Insumo que descuenta" value={insumoSel} onChange={(e) => setInsumoSel(e.target.value)}>
              <option value="">Elige un insumo…</option>
              {!p && <option value="nuevo">➕ Crear un insumo nuevo con el nombre de este producto</option>}
              {insumos.data
                ?.filter((i) => i.activo || String(i.id) === insumoSel)
                .map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.nombre} ({i.unidad_abreviatura})
                  </option>
                ))}
            </Select>
            {insumoSel === "nuevo" && (
              <Select name="unidad_nueva" label="El insumo nuevo se cuenta en" defaultValue="unidad" hint="Después carga su stock en Existencias.">
                {un.lista
                  .filter((u) => u.activa)
                  .map((u) => (
                    <option key={u.codigo} value={u.codigo}>
                      {u.nombre} ({u.abreviatura})
                    </option>
                  ))}
              </Select>
            )}
            <Field
              name="cantidad_por_venta"
              label={`Cuánto descuenta cada venta${insumo ? ` (${insumo.unidad_abreviatura})` : ""}`}
              inputMode="decimal"
              defaultValue={p?.control_stock === "directo" ? String(Number(p.cantidad_por_venta)).replace(".", ",") : "1"}
              hint="1 si vendes la pieza completa; menos si es una porción (ej. 0,25 de una botella)."
            />
          </>
        )}
        {modo === "ninguno" && <p className="text-sm text-fg-3">No toca el inventario ni limita las porciones del menú (servicios, extras, cosas que no llevas en stock).</p>}
      </fieldset>
      <Field name="orden" label="Orden en su categoría" type="number" defaultValue={p?.orden ?? 0} />
      <Toggle name="activo" label="Activo" hint="Los inactivos no se venden en ninguna sucursal." defaultChecked={p?.activo ?? true} />
    </FormSheet>
  );
}

/** "Sin IVA" o "Con IVA" + el porcentaje que sea (16, 8, 12…). */
function IvaField({ inicial }: { inicial: string | undefined }) {
  const [conIva, setConIva] = useState(inicial === undefined || Number(inicial) > 0);
  return (
    <div className="flex flex-col gap-4">
      <input type="hidden" name="con_iva" value={conIva ? "si" : "no"} />
      <div className="flex flex-col gap-1.5">
        <span className="eyebrow">IVA</span>
        <Segmented
          label="IVA del producto"
          size="sm"
          value={conIva ? "si" : "no"}
          onChange={(v) => setConIva(v === "si")}
          options={[
            { value: "si", label: "Con IVA" },
            { value: "no", label: "Sin IVA" },
          ]}
        />
      </div>
      {conIva && (
        <Field
          name="alicuota_iva"
          label="Porcentaje de IVA"
          inputMode="decimal"
          defaultValue={inicial && Number(inicial) > 0 ? alicuotaInicial(inicial) : "16"}
          hint="16 % general, 8 % reducida, o el que corresponda. Según la sucursal, el precio lo incluye o se suma encima."
        />
      )}
    </div>
  );
}
