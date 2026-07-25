import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { HistoryResponse, Profile } from "../api/types";
import { formatWhen } from "../lib/format";

const HISTORY_LIMIT = 12;

export function ProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [error, setError] = useState<string>("");

  const load = useCallback(() => {
    setError("");
    Promise.all([api.profile(), api.history(HISTORY_LIMIT)])
      .then(([nextProfile, nextHistory]) => {
        setProfile(nextProfile);
        setHistory(nextHistory);
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const clear = useCallback(async () => {
    await api.clearHistory();
    load();
  }, [load]);

  if (error) {
    return (
      <div className="notice notice--error">
        {error}
        <div className="notice__retry">
          <button type="button" className="btn btn--primary btn--md" onClick={load}>
            Повторить
          </button>
        </div>
      </div>
    );
  }

  if (!profile || !history) return <p className="notice">Загружаем профиль…</p>;

  const hasHistory = history.total > 0;

  return (
    <section className="shell page">
      <div className="profile__head">
        <div>
          <h1 className="page__title">Профиль</h1>
          <p className="profile__lead">
            История сканирований и прогресс хранятся на сервере и привязаны к этому
            браузеру.
          </p>
        </div>
        <div className="profile__stats">
          <span>
            <span className="profile__stat-value profile__stat-value--accent">
              {profile.points}
            </span>
            <span className="profile__stat-label">эко-очков</span>
          </span>
          <span>
            <span className="profile__stat-value">{profile.scanCount}</span>
            <span className="profile__stat-label">сканирований</span>
          </span>
          <span>
            <span className="profile__stat-value">{profile.streak}</span>
            <span className="profile__stat-label">дней подряд</span>
          </span>
        </div>
      </div>

      <div className="profile__mix">
        <div className="profile__mix-head">
          <span className="eyebrow">Что вы сортируете</span>
          <span className="profile__mix-count">
            {profile.categoriesUsed} из {profile.totalCategories} типов открыто
          </span>
        </div>
        <div className="profile__bar">
          {profile.mix.map((entry) => (
            <span
              key={entry.categoryId}
              style={{ flex: entry.share, background: entry.categoryColor }}
            />
          ))}
        </div>
        <div className="profile__legend">
          {profile.mix.map((entry) => (
            <span className="profile__legend-item" key={entry.categoryId}>
              <span
                className="profile__legend-dot"
                style={{ background: entry.categoryColor }}
              />
              <span className="profile__legend-name">{entry.categoryName}</span>
              <span className="profile__legend-count">{entry.count}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="profile__grid">
        <div>
          <div className="profile__section-head">
            <h2 className="profile__section-title">История</h2>
            {hasHistory && (
              <button type="button" className="profile__clear" onClick={() => void clear()}>
                Очистить
              </button>
            )}
          </div>

          <div className="history">
            {history.items.map((entry) => (
              <div className="history__row" key={entry.id}>
                <span
                  className="history__dot"
                  style={{ background: entry.categoryColor }}
                />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="history__object">{entry.objectName}</span>
                  <span className="history__meta">
                    {entry.categoryName} · {formatWhen(entry.createdAt)}
                  </span>
                </span>
                <span className="history__conf">
                  {entry.isManual ? "—" : `${Math.round(entry.confidence * 100)}%`}
                </span>
              </div>
            ))}

            {!hasHistory && (
              <div className="history__empty">
                <p>
                  Пока пусто. Отсканируйте первый предмет — он появится здесь вместе
                  с очками.
                </p>
                <button
                  type="button"
                  className="btn btn--primary btn--md"
                  style={{ marginTop: 20 }}
                  onClick={() => navigate("/scan")}
                >
                  К сканеру
                </button>
              </div>
            )}
          </div>
        </div>

        <div>
          <h2 className="profile__section-title">Достижения</h2>
          <div className="badges">
            {profile.badges.map((badge) => (
              <div className="badge" key={badge.id}>
                <span
                  className={`badge__icon${badge.achieved ? " badge__icon--done" : ""}`}
                >
                  {badge.achieved ? "✓" : ""}
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span
                    className={`badge__name${badge.achieved ? " badge__name--done" : ""}`}
                  >
                    {badge.name}
                  </span>
                  <span className="badge__desc">{badge.description}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
