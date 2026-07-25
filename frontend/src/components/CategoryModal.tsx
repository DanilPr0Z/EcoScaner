import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import type { Category } from "../api/types";
import { binName, inkOn, withAlpha } from "../lib/format";

interface Props {
  category: Category;
  onClose: () => void;
}

/** Модалка типа отхода: слева текст, справа список предметов поверх цвета бака. */
export function CategoryModal({ category, onClose }: Props) {
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal__scrim" onClick={onClose} role="presentation">
      <div
        className="modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={category.name}
      >
        <button type="button" className="modal__close" onClick={onClose} aria-label="Закрыть">
          ×
        </button>

        <div className="modal__grid">
          <div className="modal__pad">
            <span
              className="bin-chip"
              style={{ background: category.color, color: inkOn(category.color) }}
            >
              {binName(category.binLabel)}
            </span>
            <h2 className="modal__name">{category.name}</h2>
            <p className="modal__about">{category.about}</p>

            <div className="modal__prep">
              <span className="eyebrow">Как подготовить</span>
              {category.prep.map((step, index) => (
                <div className="modal__prep-step" key={step}>
                  <span
                    className="modal__prep-num"
                    style={{ background: withAlpha(category.color, 0.2) }}
                  >
                    {index + 1}
                  </span>
                  <span className="modal__prep-text">{step}</span>
                </div>
              ))}
            </div>

            <div className="modal__facts">
              <span>
                <span className="fact__label">Разлагается</span>
                <span className="fact__value">{category.decay}</span>
              </span>
              <span>
                <span className="fact__label">Станет</span>
                <span className="fact__value">{category.becomes}</span>
              </span>
            </div>

            <div className="modal__actions">
              <button
                type="button"
                className="btn btn--primary btn--md"
                onClick={() => navigate(`/guide/${category.id}`)}
              >
                Весь список в справочнике
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--md"
                onClick={() => navigate("/scan")}
              >
                Сканировать предмет
              </button>
            </div>
          </div>

          <div className="modal__side" style={{ background: withAlpha(category.color, 0.12) }}>
            {category.imageUrl && (
              <img className="modal__photo" src={category.imageUrl} alt={category.name} />
            )}
            <div className="modal__avoid">
              <span>{category.avoid}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
