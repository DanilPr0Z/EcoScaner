import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { CategoryItem, GuideSearchResult } from "../api/types";
import { binName, inkOn, plural, withAlpha } from "../lib/format";
import { useCategories } from "../state/CategoriesProvider";

/** Через столько выбор предмета сбрасывается сам — как было задумано в дизайне. */
const PICK_TIMEOUT_MS = 15_000;

/** Пауза перед запросом поиска, чтобы не дёргать сервер на каждую букву. */
const SEARCH_DEBOUNCE_MS = 250;

const MATCH_LABELS: Record<string, string> = {
  name: "в названии",
  note: "в примечании",
  category: "в названии категории",
  bin: "в названии бака",
  about: "в описании",
  hint: "в подсказке",
  avoid: "в списке исключений",
  prep: "в подготовке",
  becomes: "в том, чем станет",
  decay: "в сроке разложения",
};

export function GuidePage() {
  const navigate = useNavigate();
  const { categoryId } = useParams();
  const { categories, byId, loading, error, reload } = useCategories();

  const [query, setQuery] = useState("");
  const [found, setFound] = useState<GuideSearchResult | null>(null);
  const [picked, setPicked] = useState<CategoryItem | null>(null);
  const pickTimer = useRef<number | undefined>(undefined);

  const current = (categoryId && byId[categoryId]) || categories[0];
  const searching = query.trim().length > 0;

  // Поиск на сервере: он умеет словоформы, опечатки и ищет по описаниям категорий.
  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setFound(null);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .search(text, 50, controller.signal)
        .then(setFound)
        .catch(() => undefined);
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  // Смена категории сбрасывает выбранный предмет.
  useEffect(() => {
    setPicked(null);
  }, [categoryId]);

  useEffect(() => () => window.clearTimeout(pickTimer.current), []);

  const pickItem = (item: CategoryItem) => {
    window.clearTimeout(pickTimer.current);
    pickTimer.current = window.setTimeout(() => setPicked(null), PICK_TIMEOUT_MS);
    setPicked(item);
  };

  const openCategory = (id: string) => {
    setQuery("");
    setFound(null);
    navigate(`/guide/${id}`);
  };

  if (loading) return <p className="notice">Загружаем справочник…</p>;
  if (error) {
    return (
      <div className="notice notice--error">
        {error}
        <div className="notice__retry">
          <button type="button" className="btn btn--primary btn--md" onClick={reload}>
            Повторить
          </button>
        </div>
      </div>
    );
  }
  if (!current) return <p className="notice">Справочник пуст.</p>;

  const accepted = current.items.filter((item) => item.isAccepted);
  const rejected = current.items.filter((item) => !item.isAccepted);

  return (
    <section className="shell guide">
      <div className="guide__grid">
        <div className="guide__rail">
          <h1 className="guide__rail-title">Справочник</h1>
          <input
            className="guide__search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти предмет…"
            aria-label="Поиск по справочнику"
          />
          <div className="guide__nav">
            {categories.map((category) => {
              const active = category.id === current.id && !searching;
              return (
                <button
                  type="button"
                  key={category.id}
                  className={`guide__nav-btn${active ? " guide__nav-btn--active" : ""}`}
                  onClick={() => openCategory(category.id)}
                >
                  <span
                    className="guide__nav-dot"
                    style={{ background: category.color }}
                  />
                  <span className="guide__nav-label">{category.name}</span>
                  <span className="guide__nav-count">{category.items.length}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          {searching ? (
            <div>
              <span className="eyebrow">
                {found
                  ? `${found.total} ${plural(found.total, [
                      "предмет",
                      "предмета",
                      "предметов",
                    ])} по запросу «${found.query}»`
                  : "Ищем…"}
              </span>

              {found && found.categories.length > 0 && (
                <div className="found__cats">
                  {found.categories.map((category) => (
                    <button
                      type="button"
                      className="found__cat-btn"
                      key={category.id}
                      onClick={() => openCategory(category.id)}
                    >
                      <span
                        className="guide__nav-dot"
                        style={{ background: category.color, opacity: 1 }}
                      />
                      {category.name}
                      <span className="found__cat-where">
                        {MATCH_LABELS[category.matchedIn[0]] ?? "в описании"}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              <div className="found">
                {found?.items.map((row) => (
                  <div className="found__row" key={`${row.categoryId}-${row.name}`}>
                    <span
                      className="found__dot"
                      style={{ background: row.categoryColor }}
                    />
                    <span style={{ flex: 1, minWidth: 0 }}>
                      <span className="found__name">{row.name}</span>
                      <span className="found__note">{row.note}</span>
                    </span>
                    <span
                      className="found__cat"
                      style={{ color: row.isAccepted ? "var(--ink-soft)" : "var(--danger)" }}
                    >
                      {row.categoryName}
                    </span>
                  </div>
                ))}
              </div>

              {found && found.total === 0 && found.categories.length === 0 && (
                <p
                  style={{
                    fontSize: 17,
                    color: "var(--ink-soft)",
                    lineHeight: 1.6,
                    margin: "22px 0 0",
                    maxWidth: "44ch",
                  }}
                >
                  По этому слову ничего нет. Попробуйте другое название — или
                  отсканируйте предмет на фото, модель определит тип сама.
                </p>
              )}
            </div>
          ) : (
            <div>
              <span
                className="bin-chip"
                style={{ background: current.color, color: inkOn(current.color) }}
              >
                {binName(current.binLabel)}
              </span>
              <h2 className="guide__name">{current.name}</h2>
              <p className="guide__about">{current.about}</p>

              <div className="guide__facts">
                <span>
                  <span className="fact__label">Разлагается</span>
                  <span className="guide__fact-value">{current.decay}</span>
                </span>
                <span>
                  <span className="fact__label">Станет</span>
                  <span className="guide__fact-value">{current.becomes}</span>
                </span>
                <span>
                  <span className="fact__label">Подготовка</span>
                  <span className="guide__fact-value">{current.prep[0]}</span>
                </span>
              </div>

              <div className="guide__body">
                <div className="guide__lists">
                  <div>
                    <span className="guide__list-title guide__list-title--ok">
                      Принимают
                    </span>
                    <div className="guide__list">
                      {accepted.map((item) => (
                        <button
                          type="button"
                          key={item.name}
                          className={`guide__item${
                            picked?.name === item.name ? " guide__item--active" : ""
                          }`}
                          style={
                            picked?.name === item.name
                              ? { background: withAlpha(current.color, 0.1) }
                              : undefined
                          }
                          onMouseEnter={() => pickItem(item)}
                          onClick={() => pickItem(item)}
                        >
                          <span className="guide__item-name">{item.name}</span>
                          <span className="guide__item-note">{item.note}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {rejected.length > 0 && (
                    <div>
                      <span className="guide__list-title guide__list-title--bad">
                        Не принимают
                      </span>
                      <div className="guide__list">
                        {rejected.map((item) => (
                          <button
                            type="button"
                            key={item.name}
                            className={`guide__item${
                              picked?.name === item.name ? " guide__item--active" : ""
                            }`}
                            style={
                              picked?.name === item.name
                                ? { background: withAlpha(current.color, 0.1) }
                                : undefined
                            }
                            onMouseEnter={() => pickItem(item)}
                            onClick={() => pickItem(item)}
                          >
                            <span className="guide__item-name guide__item-name--bad">
                              {item.name}
                            </span>
                            <span className="guide__item-note">{item.note}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {rejected.length === 0 && (
                    <p
                      style={{
                        margin: 0,
                        fontSize: 15,
                        color: "var(--muted)",
                        lineHeight: 1.55,
                        borderTop: "1px solid var(--line-soft)",
                        paddingTop: 15,
                      }}
                    >
                      {current.avoid}
                    </p>
                  )}
                </div>

                <div className="guide__preview-wrap">
                  <div
                    className="guide__preview"
                    style={
                      picked
                        ? {
                            background: withAlpha(current.color, 0.12),
                            borderColor: withAlpha(current.color, 0.25),
                          }
                        : undefined
                    }
                  >
                    {picked && (
                      <div>
                        <span className="guide__preview-name">{picked.name}</span>
                        <span className="guide__preview-note">{picked.note}</span>
                        <span
                          className="guide__preview-verdict"
                          style={{
                            color: picked.isAccepted ? "var(--accent)" : "var(--danger)",
                          }}
                        >
                          {picked.isAccepted ? "Принимают" : "Не принимают"}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
