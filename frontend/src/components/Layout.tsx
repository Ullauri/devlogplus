import { Outlet, NavLink } from "react-router-dom";
import {
  BookOpen,
  Brain,
  HelpCircle,
  Library,
  FolderGit2,
  AlertTriangle,
  Settings,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "/journal", label: "Journal", icon: BookOpen },
  { to: "/profile", label: "Profile", icon: Brain },
  { to: "/quiz", label: "Quiz", icon: HelpCircle },
  { to: "/readings", label: "Readings", icon: Library },
  { to: "/projects", label: "Projects", icon: FolderGit2 },
  { to: "/triage", label: "Triage", icon: AlertTriangle },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export default function Layout() {
  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <nav className="flex w-56 flex-col border-r border-gray-200 bg-white">
        <div className="flex h-14 items-center border-b border-gray-200 px-4">
          <span className="text-lg font-bold text-brand-700">DevLog+</span>
        </div>
        <ul className="flex-1 space-y-1 p-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-brand-50 text-brand-700"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  }`
                }
              >
                <Icon size={18} />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-5xl p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
