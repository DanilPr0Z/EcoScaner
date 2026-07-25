import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { CategoryModal } from "../components/CategoryModal";
import type { Category } from "../api/types";
import { MAIN_CATEGORY_IDS, useCategories } from "../state/CategoriesProvider";

/** «Жёлтый бак · пластик» → «жёлтый». */
function binWord(binLabel: string): string {
  return binLabel.split(" ")[0].toLowerCase();
}

const STEPS = [
  {
    n: "01",
    title: "Снимаешь предмет",
    text: "Файл, галерея или камера телефона прямо в браузере.",
  },
  {
    n: "02",
    title: "Нейросеть определяет материал",
    text: "Классификатор обучен на снимках реальных отходов и различает десять видов.",
  },
  {
    n: "03",
    title: "Видишь свой бак",
    text: "Цвет контейнера, подготовка отхода и срок разложения.",
  },
];

export function HomePage() {
  const navigate = useNavigate();
  const { byId, loading, error, reload } = useCategories();
  const [opened, setOpened] = useState<Category | null>(null);

  const mainCategories = MAIN_CATEGORY_IDS.map((id) => byId[id]).filter(
    (category): category is Category => Boolean(category),
  );
  // В карточке-примере показываем реальный снимок вместо нарисованного макета.
  const hero = byId["plastic"];

  return (
    <>
      <section className="shell hero">
        <div className="hero__grid">
          <div>
            <h1 className="hero__title">Сними мусор — узнай, в какой бак</h1>
            <p className="hero__lead">
              Нейросеть определяет предмет на фото, относит его к одному из типов отходов
              и объясняет, как подготовить его к переработке.
            </p>
            <div className="hero__actions">
              <button
                type="button"
                className="btn btn--primary btn--lg"
                onClick={() => navigate("/scan")}
              >
                Загрузить фото
              </button>
              <button
                type="button"
                className="btn btn--outline btn--lg"
                onClick={() => navigate("/guide")}
              >
                Открыть справочник
              </button>
            </div>
          </div>

          <div className="hero__card">
            <div className="hero__frame">
              {hero?.imageUrl && (
                <img className="hero__photo" src={hero.imageUrl} alt={hero.name} />
              )}
              <span className="hero__scanline" />
            </div>
            <div className="hero__card-foot">
              <span>{hero ? `Бак: ${binWord(hero.binLabel)}` : "Бак определяется по фото"}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="shell steps">
        <div className="steps__grid">
          {STEPS.map((step) => (
            <div className="step" key={step.n}>
              <span className="step__num">{step.n}</span>
              <h3 className="step__title">{step.title}</h3>
              <p className="step__text">{step.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="shell bins">
        <div className="bins__head">
          <h2 className="bins__title">Пять баков, которые нужно различать</h2>
          <span className="bins__hint">нажмите строку — откроется справочник</span>
        </div>

        {loading && <p className="notice">Загружаем справочник…</p>}
        {error && (
          <div className="notice notice--error">
            {error}
            <div className="notice__retry">
              <button type="button" className="btn btn--primary btn--md" onClick={reload}>
                Повторить
              </button>
            </div>
          </div>
        )}

        <div className="bins__list">
          {mainCategories.map((category) => (
            <button
              type="button"
              className="bin-row"
              key={category.id}
              onClick={() => setOpened(category)}
            >
              <span className="bin-row__bar" style={{ background: category.color }} />
              <span className="bin-row__name">{category.name}</span>
              <span className="bin-row__examples">
                {category.items
                  .filter((item) => item.isAccepted)
                  .slice(0, 3)
                  .map((item) => item.name.toLowerCase())
                  .join(" · ")}
              </span>
              <span className="bin-row__bin">{category.binLabel}</span>
              <span className="bin-row__arrow" style={{ color: category.color }}>
                →
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="facts">
        <div className="facts__inner">
          <p className="facts__claim">
            Верно отсортированный мусор перестаёт быть мусором.
          </p>
          <div className="facts__nums">
            <span>
              <span className="facts__num">60%</span>
              <span className="facts__label">
                бытовых отходов можно переработать при верной сортировке
              </span>
            </span>
            <span>
              <span className="facts__num">400</span>
              <span className="facts__label">лет пластиковая бутылка лежит в земле</span>
            </span>
          </div>
        </div>
      </section>

      {opened && <CategoryModal category={opened} onClose={() => setOpened(null)} />}
    </>
  );
}
