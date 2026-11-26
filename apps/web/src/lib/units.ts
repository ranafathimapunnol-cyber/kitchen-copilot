/**
 * Which units an item may be bought or ordered in: its standard unit, or an
 * active unit of the same dimension with an explicit conversion either way.
 * The API applies the same rule to bills and purchase orders.
 */

export type UnitRecord = {
  id: number;
  name: string;
  symbol: string;
  dimension: string;
  is_active: boolean;
};

export type ConversionRecord = { from_unit_id: number; to_unit_id: number };

export type UnitSource = {
  items: { id: number; standard_unit_id: number }[];
  units: UnitRecord[];
  conversions: ConversionRecord[];
};

export function allowedUnits(master: UnitSource, itemId: string): UnitRecord[] {
  const item = master.items.find((row) => String(row.id) === itemId);
  const standard = item && master.units.find((unit) => unit.id === item.standard_unit_id);
  if (!item || !standard) return [];

  return master.units
    .filter(
      (unit) =>
        unit.is_active &&
        unit.dimension === standard.dimension &&
        (unit.id === standard.id ||
          master.conversions.some(
            (c) =>
              (c.from_unit_id === unit.id && c.to_unit_id === standard.id) ||
              (c.from_unit_id === standard.id && c.to_unit_id === unit.id),
          )),
    )
    .sort((a, b) =>
      a.id === standard.id ? -1 : b.id === standard.id ? 1 : a.name.localeCompare(b.name),
    );
}
