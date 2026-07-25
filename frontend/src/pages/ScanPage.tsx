import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api, frameToFile } from "../api/client";
import type { ScanResult } from "../api/types";
import { inkOn, isLightColor, withAlpha } from "../lib/format";
import { SHOW_DEV_INFO } from "../config";
import { useCategories } from "../state/CategoriesProvider";

export function ScanPage() {
  const { categories } = useCategories();

  const [preview, setPreview] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [busyText, setBusyText] = useState("");
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);

  const fileInput = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const previewUrl = useRef<string>("");

  const stopCamera = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    setCameraOn(false);
  }, []);

  // Освобождаем objectURL предыдущего снимка и камеру при уходе со страницы.
  useEffect(() => {
    return () => {
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
      stream.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const showPreview = useCallback((file: File | Blob) => {
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = URL.createObjectURL(file);
    setPreview(previewUrl.current);
  }, []);

  const analyze = useCallback(
    async (file: File | Blob) => {
      setBusy(true);
      setBusyText("Отправляем фото на распознавание…");
      setError("");
      setResult(null);

      try {
        setResult(await api.scan(file));
      } catch (cause) {
        const apiError = cause as ApiError;
        setError(apiError.message ?? "Не удалось распознать предмет.");
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const handleFile = useCallback(
    (file: File | null | undefined) => {
      if (!file) return;
      if (!file.type.startsWith("image/")) {
        setError("Нужен файл изображения: JPG, PNG или WEBP.");
        return;
      }
      stopCamera();
      showPreview(file);
      void analyze(file);
    },
    [analyze, showPreview, stopCamera],
  );

  // Вставка из буфера: Cmd/Ctrl+V со скриншотом или скопированным файлом.
  // Слушаем на документе, а не на поле — чтобы не требовать предварительного клика.
  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      const item = Array.from(event.clipboardData?.items ?? []).find((entry) =>
        entry.type.startsWith("image/"),
      );
      if (!item) return;

      event.preventDefault();
      handleFile(item.getAsFile());
    };

    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [handleFile]);

  const startCamera = useCallback(async () => {
    setError("");
    setResult(null);
    setPreview("");
    setCameraOn(true);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      stream.current = media;
      if (video.current) {
        video.current.srcObject = media;
        await video.current.play().catch(() => undefined);
      }
    } catch {
      setCameraOn(false);
      setError("Камера недоступна: браузер не дал доступ. Загрузите фото файлом.");
    }
  }, []);

  const shoot = useCallback(async () => {
    if (!video.current) return;
    const file = await frameToFile(video.current);
    stopCamera();
    showPreview(file);
    void analyze(file);
  }, [analyze, showPreview, stopCamera]);

  const reset = useCallback(() => {
    stopCamera();
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = "";
    setPreview("");
    setResult(null);
    setError("");
  }, [stopCamera]);

  /** Кнопки «Модель ошиблась» и ручного выбора после неудачи. */
  const pickCategory = useCallback(
    async (categoryId: string) => {
      setBusy(true);
      setBusyText("Сохраняем ваш выбор…");
      try {
        let next: ScanResult;
        if (result) {
          try {
            next = await api.correctScan(result.scanId, categoryId);
          } catch (cause) {
            // Скана нет на сервере — например, база пересоздавалась, пока
            // страница была открыта. Намерение пользователя от этого не меняется:
            // записываем выбор как ручное сканирование, а не упираемся в ошибку.
            if ((cause as ApiError).status !== 404) throw cause;
            next = await api.scanManual(categoryId);
          }
        } else {
          next = await api.scanManual(categoryId);
        }
        setResult(next);
        setError("");
      } catch (cause) {
        setError((cause as ApiError).message);
      } finally {
        setBusy(false);
      }
    },
    [result],
  );

  const category = result?.category;
  // На Mac буфер вставляется по Cmd, на остальных — по Ctrl.
  const pasteHint = navigator.platform.toLowerCase().includes("mac") ? "⌘V" : "Ctrl+V";

  return (
    <section className="shell page">
      <h1 className="page__title">Сканер отходов</h1>
      <p className="page__lead">
        Загрузите фото одного предмета — так распознавание точнее. Можно перетащить
        файл, вставить из буфера или снять на камеру. Если модель ошиблась,
        поправьте её: снимок с вашей пометкой сохранится и пойдёт в обучение.
      </p>

      <div className={`scan__grid${result ? " scan__grid--result" : ""}`}>
        <div className="card scan__photo">
          <div
            className={`dropzone${preview || cameraOn ? " dropzone--filled" : ""}${
              dragging ? " dropzone--dragging" : ""
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              handleFile(event.dataTransfer.files?.[0]);
            }}
            onClick={() => !preview && !cameraOn && fileInput.current?.click()}
            role="presentation"
          >
            {!preview && !cameraOn && (
              <div className="dropzone__empty">
                <span className="dropzone__icon" />
                <span className="dropzone__title">Перетащите фото сюда</span>
                <span className="dropzone__hint">
                  нажмите, чтобы выбрать файл, или вставьте из буфера ({pasteHint})
                </span>
                <span className="dropzone__hint">JPG, PNG, WEBP</span>
              </div>
            )}

            {preview && (
              <div className="preview">
                {/* Обёртка ужимается по картинке — на ней держится выравнивание
                    блока с фото по высоте правой колонки. */}
                <span className="preview__frame">
                  <img className="preview__img" src={preview} alt="Загруженное фото" />
                </span>
                {busy && (
                  <div className="preview__busy">
                    <span className="spinner" />
                    <span className="preview__busy-text">{busyText}</span>
                  </div>
                )}
              </div>
            )}

            {cameraOn && (
              <div className="preview">
                <video
                  className="preview__video"
                  ref={video}
                  autoPlay
                  playsInline
                  muted
                />
              </div>
            )}
          </div>

          <div className="scan__controls">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={() => fileInput.current?.click()}
            >
              Выбрать файл
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => (cameraOn ? stopCamera() : void startCamera())}
            >
              {cameraOn ? "Выключить камеру" : "Снять на камеру"}
            </button>
            {cameraOn && (
              <button
                type="button"
                className="btn btn--accent btn--sm"
                onClick={() => void shoot()}
              >
                Снять кадр
              </button>
            )}
            {preview && (
              <button type="button" className="scan__reset" onClick={reset}>
                Сбросить
              </button>
            )}
          </div>

          <input
            type="file"
            accept="image/*"
            ref={fileInput}
            onChange={(event) => {
              handleFile(event.target.files?.[0]);
              event.target.value = "";
            }}
            style={{ display: "none" }}
          />
        </div>

        <>
          {!result && !error && (
            <div className="placeholder">
              <h3 className="placeholder__title">Результат появится здесь</h3>
              <p className="placeholder__text">
                Что сервис умеет узнавать: пластик, стекло, металл, бумагу и картон,
                пищевые и растительные отходы, текстиль и смешанный мусор.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <span className="eyebrow">Совет для точности</span>
                <span style={{ fontSize: 15, color: "var(--ink-soft)", lineHeight: 1.55 }}>
                  Один предмет в кадре, ровный фон, хорошее освещение, этикетка видна.
                </span>
              </div>
            </div>
          )}

          {result && category && (
            <>
              <div
                className="result"
                style={{
                  background: category.color,
                  // На тёмных баках тёмно-зелёный текст сливается с фоном.
                  color: inkOn(category.color),
                }}
              >
                <div className="result__head">
                  <div>
                    <span className="result__object">
                      {result.isManual ? "указано вручную" : `на фото: ${result.objectName}`}
                    </span>
                    <h2 className="result__cat">{category.name}</h2>
                  </div>
                  <span
                    className="result__conf"
                    style={{
                      background: isLightColor(category.color)
                        ? "rgba(49,87,44,.14)"
                        : "rgba(255,255,255,.22)",
                    }}
                  >
                    {result.isManual
                      ? "вручную"
                      : `точность ${Math.round(result.confidence * 100)}%`}
                  </span>
                </div>
                <div
                  className="result__bin"
                  style={{
                    background: isLightColor(category.color)
                      ? "rgba(255,255,255,.55)"
                      : "rgba(0,0,0,.18)",
                  }}
                >
                  <span
                    className="result__bin-dot"
                    style={{
                      background: isLightColor(category.color) ? "#31572C" : "#FAF9F6",
                    }}
                  />
                  <span>{category.binLabel}</span>
                </div>
                <p className="result__hint">{category.hint}</p>
              </div>

              <div className="card" style={{ padding: 26 }}>
                <span className="eyebrow">Подготовь перед выбросом</span>
                <div className="prep">
                  {category.prep.map((step, index) => (
                    <div className="prep__step" key={step}>
                      <span className="prep__num">{index + 1}</span>
                      <span className="prep__text">{step}</span>
                    </div>
                  ))}
                </div>

                <div className="facts-row">
                  <div>
                    <span className="fact__label">Разлагается</span>
                    <span className="fact__value">{category.decay}</span>
                  </div>
                  <div>
                    <span className="fact__label">Станет</span>
                    <span className="fact__value">{category.becomes}</span>
                  </div>
                </div>

                <div className="warn">
                  <span className="warn__title">Не кладите в этот бак</span>
                  <span className="warn__text">{category.avoid}</span>
                </div>
              </div>

              {SHOW_DEV_INFO && (
              <div className="card" style={{ padding: 22 }}>
                <span className="eyebrow">Модель ошиблась? Исправьте</span>
                <div className="chips">
                  {categories.map((option) => {
                    const active = option.id === category.id;
                    return (
                      <button
                        type="button"
                        className="chip"
                        key={option.id}
                        onClick={() => void pickCategory(option.id)}
                        style={
                          active
                            ? {
                                background: option.color,
                                color: inkOn(option.color),
                                borderColor: option.color,
                              }
                            : undefined
                        }
                      >
                        {option.name}
                      </button>
                    );
                  })}
                </div>

                {SHOW_DEV_INFO && result.tech.length > 0 && (
                  <div className="tech">
                    <span className="eyebrow" style={{ display: "block", marginBottom: 10 }}>
                      Что увидела нейросеть
                    </span>
                    {result.tech.map((row) => (
                      <div className="tech__row" key={row.label}>
                        <span className="tech__label">{row.label}</span>
                        <span className="tech__score">{row.score}</span>
                      </div>
                    ))}
                  </div>
                )}

                {error && <p className="scan__inline-error">{error}</p>}

                {result.isManual && (
                  <p className="scan__hint">
                    Исправление сохранено. Этот же снимок теперь сразу определится
                    верно, а сама пометка пойдёт в дообучение модели.
                  </p>
                )}

              </div>
              )}

              <div className="scan__points">
                +{result.pointsAwarded} эко-очков · всего {result.totalPoints}
              </div>
            </>
          )}

          {error && !result && (
            <div className="error-card">
              <h3 className="error-card__title">Не удалось распознать</h3>
              <p className="error-card__text">{error}</p>
              <div className="chips" style={{ marginTop: 0 }}>
                {categories.map((option) => (
                  <button
                    type="button"
                    className="chip"
                    key={option.id}
                    onClick={() => void pickCategory(option.id)}
                    style={{ background: withAlpha(option.color, 0.18) }}
                  >
                    {option.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      </div>
    </section>
  );
}
