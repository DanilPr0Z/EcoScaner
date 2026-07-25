import { createContext, use, useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api/client";
import type { Category, CategoryId } from "../api/types";

/** Пять баков, которые показываем на главной. Порядок — как в справочнике. */
export const MAIN_CATEGORY_IDS: CategoryId[] = [
  "plastic",
  "glass",
  "paper",
  "metal",
  "organic",
];

interface CategoriesState {
  categories: Category[];
  byId: Record<string, Category | undefined>;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

const CategoriesContext = createContext<CategoriesState | null>(null);

/**
 * Справочник грузится с бэкенда один раз на всё приложение: он нужен главной,
 * справочнику, модалке и кнопкам ручного выбора на сканере.
 */
export function CategoriesProvider({ children }: { children: ReactNode }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .categories()
      .then(setCategories)
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byId: Record<string, Category | undefined> = {};
  for (const category of categories) byId[category.id] = category;

  return (
    <CategoriesContext value={{ categories, byId, loading, error, reload: load }}>
      {children}
    </CategoriesContext>
  );
}

export function useCategories(): CategoriesState {
  const state = use(CategoriesContext);
  if (!state) throw new Error("useCategories вызван вне CategoriesProvider");
  return state;
}
