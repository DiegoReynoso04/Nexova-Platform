// Preselección del activo en los formularios de entrada y salida, a partir del
// `?asset_id=` con el que enlaza cada fila de /inventory/products. Módulo puro:
// lo usan las páginas (lectura del parámetro), las vistas y los tests.

import type { Asset } from '@/types/inventory';

/** El `?asset_id=` de la URL: ausente, o presente con un id válido o no (`null`). */
export type AssetIdParam = { requested: false } | { requested: true; id: number | null };

/**
 * Lee `?asset_id=` tal como lo entrega Next (`searchParams`). Solo un entero
 * positivo escrito en dígitos es un id; cualquier otra cosa (texto, lista, 0)
 * cuenta como pedido pero inválido, para avisar al usuario.
 */
export function parseAssetIdParam(value: string | string[] | undefined): AssetIdParam {
  if (value === undefined) return { requested: false };
  if (typeof value !== 'string' || !/^\d+$/.test(value.trim())) return { requested: true, id: null };
  const id = Number(value.trim());
  return { requested: true, id: Number.isSafeInteger(id) && id > 0 ? id : null };
}

export type Preselection =
  /** Sin `?asset_id=`: el selector empieza vacío. */
  | { status: 'none' }
  /** Hay `?asset_id=`, pero los activos aún no se han cargado. */
  | { status: 'pending' }
  /** El activo existe: se preselecciona. */
  | { status: 'found'; assetId: number }
  /** El id no es válido o no está en el inventario: sin preselección y con un aviso. */
  | { status: 'missing' };

/** `assets = null` mientras no se haya recibido el listado. */
export function resolvePreselection(param: AssetIdParam, assets: readonly Asset[] | null): Preselection {
  if (!param.requested) return { status: 'none' };
  if (param.id === null) return { status: 'missing' };
  if (assets === null) return { status: 'pending' };
  const id = param.id;
  return assets.some((asset) => asset.id === id) ? { status: 'found', assetId: id } : { status: 'missing' };
}

/**
 * Activo con el que se monta el formulario: el de la URL, si existe. Vale
 * también tras una entrada o salida correcta, cuando el formulario se vuelve
 * a montar limpio (`key = formKey`): el activo del enlace sigue elegido.
 */
export function formInitialAssetId(preselection: Preselection): number | null {
  return preselection.status === 'found' ? preselection.assetId : null;
}

/** Texto de cada opción del selector: nunca el id (hay nombres repetidos, por eso el SKU y la oficina). */
export function assetOptionLabel(asset: Pick<Asset, 'name' | 'sku' | 'office'>): string {
  return `${asset.name} — ${asset.sku} (${asset.office})`;
}
