import { BrowserRouter, Route, Routes } from "react-router-dom";

import { BuildPage } from "./app/BuildPage.tsx";
import { ComparePage } from "./app/ComparePage.tsx";
import { HomePage } from "./app/HomePage.tsx";
import { Layout } from "./app/Layout.tsx";
import { MethodologyPage } from "./app/MethodologyPage.tsx";
import { PlaceholderPage } from "./app/PlaceholderPage.tsx";
import { ResultsPage } from "./app/ResultsPage.tsx";
import { PlannerProvider } from "./state/PlannerProvider.tsx";

export function AppRoutes() {
  return (
    <PlannerProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="build" element={<BuildPage />} />
          <Route
            path="build/:shareId"
            element={
              <PlaceholderPage
                title="Shared build"
                body="Shared builds are not stored in this version. A link will show a saved snapshot only after sharing is turned on."
              />
            }
          />
          <Route path="results" element={<ResultsPage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="about/methodology" element={<MethodologyPage />} />
        </Route>
      </Routes>
    </PlannerProvider>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
