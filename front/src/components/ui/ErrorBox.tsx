import type { ErrorView } from "@/lib/api/errors";

/** Error legible en línea, con sus detalles (faltantes de stock, productos, etc.). */
export function ErrorBox({ error, onClose }: { error: ErrorView; onClose?: () => void }) {
  return (
    <div role="alert" className="mb-4 flex items-start justify-between gap-4 border-l-2 border-err py-1 pl-4">
      <div className="flex flex-col gap-1">
        <p className="text-base font-medium">{error.title}</p>
        {error.description && <p className="text-sm text-fg-2">{error.description}</p>}
        {error.items && error.items.length > 0 && (
          <ul className="flex flex-col gap-0.5 pt-1 text-sm text-fg-2">
            {error.items.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        )}
      </div>
      {onClose && (
        <button type="button" onClick={onClose} className="text-sm text-fg-3 hover:text-fg">
          Cerrar
        </button>
      )}
    </div>
  );
}
