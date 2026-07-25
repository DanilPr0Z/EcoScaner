import { NavLink, useNavigate } from "react-router-dom";

import { SHOW_DEV_INFO } from "../config";

const LINKS = [
  { to: "/scan", label: "Сканер" },
  { to: "/guide", label: "Справочник" },
  { to: "/profile", label: "Профиль" },
  // Служебная страница: показывается только при включённой отладке.
  ...(SHOW_DEV_INFO ? [{ to: "/model", label: "Модель" }] : []),
];

export function Header() {
  const navigate = useNavigate();

  return (
    <header className="header">
      <div className="header__inner">
        <button type="button" className="logo" onClick={() => navigate("/")}>
          <span className="logo__mark">
            <span className="logo__corner logo__corner--tl" />
            <span className="logo__corner logo__corner--tr" />
            <span className="logo__corner logo__corner--bl" />
            <span className="logo__corner logo__corner--br" />
            <span className="logo__leaf" />
          </span>
          <span className="logo__word">BinGo</span>
        </button>

        <div className="header__right">
          <nav className="nav">
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  isActive ? "nav__link nav__link--active" : "nav__link"
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            className="btn btn--primary header__cta"
            onClick={() => navigate("/scan")}
          >
            Сканировать
          </button>
        </div>
      </div>
    </header>
  );
}
