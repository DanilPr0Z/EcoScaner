/**
 * Клиент BinGo API для TS React фронтенда.
 *
 * Положите этот файл и `api-types.ts` в `src/api/` вашего React-проекта.
 * Базовый адрес берётся из `VITE_API_URL`, по умолчанию — локальный бэкенд.
 *
 * Пользователь анонимный: при первом обращении генерируется UUID, кладётся
 * в localStorage и дальше уходит в заголовке X-Device-Id с каждым запросом.
 */

import type {
  Category,
  GuideSearchResult,
  HealthResponse,
  HistoryResponse,
  Profile,
  ScanResult,
} from "./api-types";
import { API_BASE, DEVICE_ID_HEADER } from "./api-types";

const BASE_URL =
  (import.meta as { env?: Record<string, string> }).env?.VITE_API_URL ?? API_BASE;

const DEVICE_STORAGE_KEY = "bingo.deviceId";

/** UUID этого браузера. Создаётся один раз и переживает перезагрузки. */
export function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_STORAGE_KEY, id);
  }
  return id;
}

/** Ошибка запроса. `message` — текст из поля `detail`, уже на русском:
 *  его можно показывать пользователю как есть. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Предмет на фото не распознан — показываем ручной выбор категории. */
  get isUnrecognized(): boolean {
    return this.status === 422;
  }

  /** Файл не подошёл: не изображение или слишком большой. */
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

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });

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

  category: (id: string) => request<Category>(`/categories/${id}`),

  /** Поиск по всему тексту справочника: названия, примечания, описания категорий. */
  search: (query: string, limit = 50) =>
    request<GuideSearchResult>(
      `/guide/search?q=${encodeURIComponent(query)}&limit=${limit}`,
    ),

  /** Распознать фото. Бросает ApiError с isUnrecognized при 422. */
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

  /** «Модель ошиблась» — перенести скан в верную категорию. */
  correctScan: (scanId: string, categoryId: string) =>
    request<ScanResult>(`/scan/${scanId}/correct`, {
      method: "POST",
      body: JSON.stringify({ categoryId }),
    }),

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
  canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);

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
