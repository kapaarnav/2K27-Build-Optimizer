import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "Home", end: true },
  { to: "/build", label: "Builder", end: true },
  { to: "/results", label: "Results", end: false },
  { to: "/compare", label: "Compare", end: false },
  { to: "/about/methodology", label: "Methodology", end: false },
];

export function Layout() {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm font-semibold">Unofficial 2K27 Build Optimizer</p>
          <nav aria-label="Primary" className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  isActive ? "font-semibold text-stone-950 underline" : "text-stone-600"
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
