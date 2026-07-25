/**
 * Типы ответов BinGo API. Соответствуют схемам pydantic в app/schemas —
 * при изменении схемы на бэкенде правьте и здесь. Актуальный контракт
 * всегда виден в http://localhost:8000/docs
 */

export type CategoryId =
  | "plastic"
  | "glass"
  | "paper"
  | "metal"
  | "organic"
  | "special"
  | "other";

export interface CategoryItem {
  name: string;
  isAccepted: boolean;
  note: string;
}

/** Категория без списка предметов — этого хватает карточке результата сканирования. */
export interface CategoryBase {
  id: CategoryId;
  name: string;
  /** HEX, например "#E8A317" — цвет бака в интерфейсе. */
  color: string;
  /** "Жёлтый бак · пластик" */
  binLabel: string;
  hint: string;
  about: string;
  /** Шаги подготовки к выбросу. */
  prep: string[];
  decay: string;
  becomes: string;
  avoid: string;
}

export interface Category extends CategoryBase {
  items: CategoryItem[];
}

/**
 * Рамка объекта. Координаты — проценты от размеров изображения: сервер фото
 * не хранит, поэтому рамка рисуется поверх локального превью.
 */
export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
  label: string;
}

/** Строка блока «Что увидела нейросеть». */
export interface TechRow {
  label: string;
  score: string;
}

export interface ScanResult {
  scanId: string;
  objectName: string;
  /** 0..1 */
  confidence: number;
  isManual: boolean;
  category: CategoryBase;
  boxes: Box[];
  tech: TechRow[];
  pointsAwarded: number;
  totalPoints: number;
  /** ISO 8601, UTC */
  createdAt: string;
}

/** Где нашлось совпадение у предмета. */
export type ItemMatchField = "name" | "note" | "category";

/** Где нашлось совпадение у категории. */
export type CategoryMatchField =
  | "name"
  | "bin"
  | "about"
  | "hint"
  | "avoid"
  | "prep"
  | "becomes"
  | "decay";

export interface GuideSearchItem {
  name: string;
  note: string;
  isAccepted: boolean;
  categoryId: CategoryId;
  categoryName: string;
  categoryColor: string;
  /** За какие поля строка попала в выдачу. */
  matchedIn: ItemMatchField[];
  /** Вес совпадения. Выдача уже отсортирована по нему. */
  score: number;
}

/**
 * Категория, чей собственный текст отвечает запросу: например, «метан»
 * встречается только в подсказке про органику.
 */
export interface GuideSearchCategory {
  id: CategoryId;
  name: string;
  color: string;
  binLabel: string;
  matchedIn: CategoryMatchField[];
  score: number;
}

export interface GuideSearchResult {
  query: string;
  /** Сколько предметов нашлось всего — до применения limit. */
  total: number;
  items: GuideSearchItem[];
  categories: GuideSearchCategory[];
}

export interface HistoryEntry {
  id: string;
  categoryId: CategoryId;
  categoryName: string;
  categoryColor: string;
  objectName: string;
  confidence: number;
  isManual: boolean;
  createdAt: string;
}

export interface HistoryResponse {
  total: number;
  items: HistoryEntry[];
}

export interface MixEntry {
  categoryId: CategoryId;
  categoryName: string;
  categoryColor: string;
  count: number;
  /** Доля 0..1 — ширина сегмента полосы на профиле. */
  share: number;
}

export type BadgeId =
  | "first_scan"
  | "ten_scans"
  | "all_five_bins"
  | "week_streak"
  | "hazardous";

export interface Badge {
  id: BadgeId;
  name: string;
  description: string;
  achieved: boolean;
}

export interface Profile {
  deviceId: string;
  points: number;
  scanCount: number;
  /** Дней подряд со сканированиями, считая от сегодня. */
  streak: number;
  categoriesUsed: number;
  totalCategories: number;
  mix: MixEntry[];
  badges: Badge[];
}

export interface HealthResponse {
  status: "ok";
  appName: string;
  /** "stub" — заглушка распознавания, "ml" — реальная модель. */
  classifier: string;
}

export interface EpochPoint {
  epoch: number;
  trainLoss?: number | null;
  valLoss?: number | null;
  top1?: number | null;
  top5?: number | null;
}

/** Сводка обучения — то же, что обучение пишет в results.csv. */
/** Ход текущей эпохи обучения. */
export interface TrainingProgress {
  epoch: number;
  epochs: number;
  batch: number;
  batches: number;
  /** Среднее значение потерь по батчам текущей эпохи. Падает — идём верно. */
  meanLoss: number;
}

export interface ModelInfo {
  /** "stub" — заглушка, "ml" — обученная модель. */
  classifier: string;
  trained: boolean;
  /** Обучение идёт прямо сейчас — цифры меняются с каждой эпохой. */
  inProgress: boolean;
  dataset?: string | null;
  model?: string | null;
  /** ISO 8601 */
  trainedAt?: string | null;
  epochs?: number | null;
  classes: string[];
  best?: EpochPoint | null;
  history: EpochPoint[];
  progress?: TrainingProgress | null;
}
