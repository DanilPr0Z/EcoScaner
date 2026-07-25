/** Склонение по числу: plural(2, ["предмет", "предмета", "предметов"]) → "предмета". */
export function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
}

/** «сегодня 14:05» или «25.07 14:05». Время приходит из API в UTC. */
export function formatWhen(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes(),
  ).padStart(2, "0")}`;

  if (date.toDateString() === now.toDateString()) return `сегодня ${time}`;
  return `${date.getDate()}.${String(date.getMonth() + 1).padStart(2, "0")} ${time}`;
}

/**
 * Светлый ли цвет бака — от этого зависит, каким цветом писать поверх него.
 * Порог подобран в дизайне: молочная бумага получает тёмный текст, зелёная
 * органика — светлый.
 */
export function isLightColor(hex: string): boolean {
  const value = Number.parseInt(hex.slice(1), 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return 0.299 * r + 0.587 * g + 0.114 * b > 165;
}

/** Цвет текста, читаемый поверх цвета бака. */
export function inkOn(hex: string): string {
  return isLightColor(hex) ? "#31572C" : "#FAF9F6";
}

/** Первая часть «Жёлтый бак · пластик» — как в дизайне на чипе категории. */
export function binName(binLabel: string): string {
  return binLabel.split(" · ")[0];
}

/** "#E8A317" + прозрачность → "rgba(...)" для мягких подложек. */
export function withAlpha(hex: string, alpha: number): string {
  const value = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}
