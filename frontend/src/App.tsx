import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useEffect } from "react";

import { Header } from "./components/Header";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { ProfilePage } from "./pages/ProfilePage";
import { ScanPage } from "./pages/ScanPage";
import { CategoriesProvider } from "./state/CategoriesProvider";

/** При переходе между экранами возвращаем страницу наверх. */
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <CategoriesProvider>
      <div className="app">
        <ScrollToTop />
        <Header />
        <main className="app__main">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/scan" element={<ScanPage />} />
            <Route path="/guide" element={<GuidePage />} />
            <Route path="/guide/:categoryId" element={<GuidePage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </CategoriesProvider>
  );
}
