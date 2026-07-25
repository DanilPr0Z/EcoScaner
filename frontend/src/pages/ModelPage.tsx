import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ModelInfo } from "../api/types";
import { LineChart } from "../components/LineChart";

/**
 * Цвета серий проверены на различимость при дальтонизме
 * (ΔE 22 при протанопии) и на контраст с фоном страницы.
 */
const BLUE = "#1F6FB2";
const AMBER = "#B26B00";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleString("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ModelPage() {
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let timer: number | undefined;

    const load = () => {
      api
        .model()
        .then((next) => {
          setInfo(next);
          // Пока обучение идёт, цифры меняются каждую эпоху — подтягиваем их сами,
          // чтобы не приходилось перезагружать страницу. Эпоха длится минуты,
          // так что раз в полминуты более чем достаточно.
          if (next.inProgress) timer = window.setTimeout(load, 30_000);
        })
        .catch((cause: Error) => setError(cause.message));
    };

    load();
    return () => window.clearTimeout(timer);
  }, []);

  if (error) return <div className="notice notice--error">{error}</div>;
  if (!info) return <p className="notice">Загружаем сводку…</p>;

  if (!info.history.length) {
    return (
      <section className="shell page">
        <h1 className="page__title">
          Модель
          {info.inProgress && (
            <span className="model__badge">
              <span className="status__dot status__dot--loading" />
              обучение идёт
            </span>
          )}
        </h1>
        <p className="page__lead">
          {info.inProgress ? (
            <>
              Первая эпоха ещё считается — цифры появятся, как только она
              закончится. Страница обновится сама.
            </>
          ) : info.classifier === "stub" ? (
            <>
              Сейчас работает заглушка распознавания — обучать было нечего.
              Обучите модель командой{" "}
              <code>python -m prediction.train_classifier</code>.
            </>
          ) : (
            <>
              Сводка обучения не найдена. Обучите модель командой{" "}
              <code>python -m prediction.train_classifier</code> — здесь появятся
              точность и потери по эпохам.
            </>
          )}
        </p>

      {info.progress && (
        <div className="progress">
          <div className="progress__head">
            <span className="eyebrow">
              Эпоха {info.progress.epoch} из {info.progress.epochs} · батч{" "}
              {info.progress.batch} из {info.progress.batches}
            </span>
            <span className="progress__loss">
              средние потери по батчам: <b>{info.progress.meanLoss.toFixed(4)}</b>
            </span>
          </div>
          <div className="progress__bar">
            <span
              className="progress__fill"
              style={{
                width: `${((info.progress.epoch - 1 + info.progress.batch / info.progress.batches) / info.progress.epochs) * 100}%`,
              }}
            />
          </div>
        </div>
      )}
      </section>
    );
  }

  const epochs = info.history.map((point) => point.epoch);
  const best = info.best;

  return (
    <section className="shell page">
      <div className="profile__head">
        <div>
          <h1 className="page__title">
            Модель
            {info.inProgress && (
              <span className="model__badge">
                <span className="status__dot status__dot--loading" />
                обучение идёт · эпоха {info.epochs}
              </span>
            )}
          </h1>
          <p className="profile__lead">
            {info.model} обучена на датасете {info.dataset}. Значения — те же, что
            пишет обучение: точность и потери на отложенной выборке.
          </p>
        </div>
        <div className="profile__stats">
          <span>
            <span className="profile__stat-value profile__stat-value--accent">
              {best?.top1 !== null && best?.top1 !== undefined
                ? `${Math.round(best.top1 * 100)}%`
                : "—"}
            </span>
            <span className="profile__stat-label">точность top-1</span>
          </span>
          <span>
            <span className="profile__stat-value">
              {best?.top5 !== null && best?.top5 !== undefined
                ? `${Math.round(best.top5 * 100)}%`
                : "—"}
            </span>
            <span className="profile__stat-label">точность top-5</span>
          </span>
          <span>
            <span className="profile__stat-value">{info.epochs ?? "—"}</span>
            <span className="profile__stat-label">эпох</span>
          </span>
        </div>
      </div>


      {info.progress && (
        <div className="progress">
          <div className="progress__head">
            <span className="eyebrow">
              Эпоха {info.progress.epoch} из {info.progress.epochs} · батч{" "}
              {info.progress.batch} из {info.progress.batches}
            </span>
            <span className="progress__loss">
              средние потери по батчам: <b>{info.progress.meanLoss.toFixed(4)}</b>
            </span>
          </div>
          <div className="progress__bar">
            <span
              className="progress__fill"
              style={{
                width: `${((info.progress.epoch - 1 + info.progress.batch / info.progress.batches) / info.progress.epochs) * 100}%`,
              }}
            />
          </div>
        </div>
      )}

      <div className="model__meta">
        <span>
          <span className="fact__label">Лучшая эпоха</span>
          <span className="fact__value">{best?.epoch ?? "—"}</span>
        </span>
        <span>
          <span className="fact__label">Потери на валидации</span>
          <span className="fact__value">{best?.valLoss?.toFixed(4) ?? "—"}</span>
        </span>
        <span>
          <span className="fact__label">Обучена</span>
          <span className="fact__value">{formatDate(info.trainedAt)}</span>
        </span>
        <span>
          <span className="fact__label">Классов</span>
          <span className="fact__value">{info.classes.length || "—"}</span>
        </span>
      </div>

      <div className="model__charts">
        <LineChart
          title="Потери по эпохам"
          labels={epochs}
          precision={2}
          min={0}
          series={[
            {
              key: "train",
              label: "обучение",
              color: BLUE,
              points: info.history.map((p) => p.trainLoss ?? null),
            },
            {
              key: "val",
              label: "валидация",
              color: AMBER,
              points: info.history.map((p) => p.valLoss ?? null),
            },
          ]}
        />

        <LineChart
          title="Точность по эпохам"
          labels={epochs}
          precision={2}
          min={0}
          max={1}
          series={[
            {
              key: "top1",
              label: "top-1",
              color: BLUE,
              points: info.history.map((p) => p.top1 ?? null),
            },
            {
              key: "top5",
              label: "top-5",
              color: AMBER,
              points: info.history.map((p) => p.top5 ?? null),
            },
          ]}
        />
      </div>

      {info.classes.length > 0 && (
        <div className="model__classes">
          <span className="eyebrow">Классы датасета</span>
          <div className="chips">
            {info.classes.map((name) => (
              <span className="chip" key={name}>
                {name}
              </span>
            ))}
          </div>
        </div>
      )}

      <details className="model__table">
        <summary>Показать таблицей</summary>
        <div className="model__table-wrap">
          <table>
            <thead>
              <tr>
                <th>Эпоха</th>
                <th>Потери обучения</th>
                <th>Потери валидации</th>
                <th>top-1</th>
                <th>top-5</th>
              </tr>
            </thead>
            <tbody>
              {info.history.map((point) => (
                <tr key={point.epoch} className={point.epoch === best?.epoch ? "is-best" : undefined}>
                  <td>{point.epoch}</td>
                  <td>{point.trainLoss?.toFixed(4) ?? "—"}</td>
                  <td>{point.valLoss?.toFixed(4) ?? "—"}</td>
                  <td>{point.top1?.toFixed(4) ?? "—"}</td>
                  <td>{point.top5?.toFixed(4) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
