/**
 * Клиент BinGo API.
 *
 * В разработке запросы идут на относительный /api/v1 — Vite проксирует их
 * на FastAPI (см. vite.config.ts), поэтому CORS не участвует. Для сборки под
 * отдельный домен задайте VITE_API_URL.
 *
 * Пользователь анонимный: при первом обращении генерируется UUID, кладётся
 * в localStorage и уходит в заголовке X-Device-Id с каждым запросом.
 */

import type {
  Category,
  GuideSearchResult,
  HealthResponse,
  HistoryResponse,
  ModelInfo,
  Profile,
  ScanResult,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api/v1";
const DEVICE_ID_HEADER = "X-Device-Id";
const DEVICE_STORAGE_KEY = "bingo.deviceId";

/**
 * Генерирует UUID v4.
 *
 * `crypto.randomUUID` существует только в защищённом контексте — по HTTPS
 * или на localhost. На сервере, открытом по обычному HTTP, его нет, и вызов
 * ронял вообще всё: без идентификатора устройства не уходил ни один запрос,
 * а значит не грузились ни справочник, ни картинки.
 *
 * `crypto.getRandomValues` доступен и без защищённого контекста, поэтому
 * собираем UUID из него. Math.random остаётся на совсем древний случай:
 * такой идентификатор менее случаен, но он всего лишь различает браузеры.
 */
function randomUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }

  // Версия 4 и вариант RFC 4122 — иначе бэкенд не примет строку как UUID.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

/** UUID этого браузера. Создаётся один раз и переживает перезагрузки. */
export function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_STORAGE_KEY);
  if (!id) {
    id = randomUuid();
    localStorage.setItem(DEVICE_STORAGE_KEY, id);
  }
  return id;
}

/**
 * Ошибка запроса. `message` — текст из поля `detail`, уже на русском:
 * его можно показывать пользователю как есть.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Предмет на фото не распознан — предлагаем выбрать категорию вручную. */
  get isUnrecognized(): boolean {
    return this.status === 422;
  }

  /** Файл не подошёл: не изображение, пустой или слишком большой. */
  get isBadImage(): boolean {
    return this.status === 415 || this.status === 413 || this.status === 400;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set(DEVICE_ID_HEADER, getDeviceId());
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Сервер недоступен. Проверьте, запущен ли бэкенд.");
  }

  if (!response.ok) {
    let detail = `Запрос не удался (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // тело не JSON — оставляем текст по умолчанию
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  /** Статус сервиса и активная модель распознавания. */
  health: () => request<HealthResponse>("/health"),

  /** Весь справочник: 7 категорий с предметами. Грузится один раз при старте. */
  categories: () => request<Category[]>("/categories"),

  /** Поиск по всему тексту справочника: названия, примечания, описания категорий. */
  search: (query: string, limit = 50, signal?: AbortSignal) =>
    request<GuideSearchResult>(
      `/guide/search?q=${encodeURIComponent(query)}&limit=${limit}`,
      { signal },
    ),

  /** Распознать фото. При 422 бросает ApiError с isUnrecognized. */
  scan: (file: File | Blob) => {
    const form = new FormData();
    form.append("file", file);
    return request<ScanResult>("/scan", { method: "POST", body: form });
  },

  /** Ручной выбор категории — когда распознавание не сработало. */
  scanManual: (categoryId: string) =>
    request<ScanResult>("/scan/manual", {
      method: "POST",
      body: JSON.stringify({ categoryId }),
    }),

  /** «Модель ошиблась» — перенести уже сделанный скан в верную категорию. */
  correctScan: (scanId: string, categoryId: string) =>
    request<ScanResult>(`/scan/${scanId}/correct`, {
      method: "POST",
      body: JSON.stringify({ categoryId }),
    }),

  /** Сводка обучения: точность и потери по эпохам. */
  model: () => request<ModelInfo>("/model"),

  profile: () => request<Profile>("/profile"),

  history: (limit = 12) => request<HistoryResponse>(`/profile/history?limit=${limit}`),

  clearHistory: () => request<void>("/profile/history", { method: "DELETE" }),
};

/**
 * Кадр с камеры в файл для api.scan().
 * Заменяет canvas.toDataURL() из прототипа: на сервер уходит бинарник, а не base64.
 */
export function frameToFile(video: HTMLVideoElement): Promise<File> {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;

  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("Браузер не дал доступ к canvas"));
  context.drawImage(video, 0, 0, canvas.width, canvas.height);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) =>
        blob
          ? resolve(new File([blob], "frame.jpg", { type: "image/jpeg" }))
          : reject(new Error("Не удалось получить кадр с камеры")),
      "image/jpeg",
      0.92,
    );
  });
}
