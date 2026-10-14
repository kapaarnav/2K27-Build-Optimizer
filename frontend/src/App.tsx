import { BrowserRouter, Route, Routes } from "react-router-dom";

import { HomePage } from "./app/HomePage.tsx";
import { Layout } from "./app/Layout.tsx";
import { MethodologyPage } from "./app/MethodologyPage.tsx";
import { PlaceholderPage } from "./app/PlaceholderPage.tsx";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route
            path="build"
            element={
              <PlaceholderPage
                title="Builder"
                body="The builder form arrives after a verified ruleset can describe legal inputs. Nothing entered here would be recommended yet."
              />
            }
          />
          <Route
            path="build/:shareId"
            element={
              <PlaceholderPage
                title="Shared build"
                body="Shared builds are not stored in this version. A link will show a saved snapshot only after sharing is turned on."
              />
            }
          />
          <Route
            path="results"
            element={
              <PlaceholderPage
                title="Results"
                body="Results stay on this device after a search. There is no verified search to run yet."
              />
            }
          />
          <Route
            path="compare"
            element={
              <PlaceholderPage
                title="Compare"
                body="Comparison of up to three generated builds arrives with the results view."
              />
            }
          />
          <Route path="about/methodology" element={<MethodologyPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
