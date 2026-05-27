import {
  ClipboardList,
  FileText,
  History,
  Home,
  Layers3,
  Radar,
  Search,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const navigationItems = [
  { label: "Dashboard", to: "/", icon: Home },
  { label: "Veilles", to: "/watches", icon: Radar },
  { label: "Annonces", to: "/listings", icon: Search },
  { label: "Dossier", to: "/dossier", icon: FileText },
  { label: "Paquets", to: "/contact-packets", icon: ClipboardList },
  { label: "Historique", to: "/history", icon: History },
];

export function AppShell() {
  return (
    <div className="min-h-screen bg-background">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[232px_minmax(0,1fr)]">
        <aside className="border-b bg-card lg:border-b-0 lg:border-r">
          <div className="flex h-16 items-center justify-between border-b px-4">
            <div>
              <div className="text-base font-semibold">DossierAgent</div>
              <div className="text-xs text-muted-foreground">Command center</div>
            </div>
            <Badge variant="secondary">MVP</Badge>
          </div>
          <nav className="grid gap-1 p-3">
            {navigationItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground",
                    "hover:bg-muted hover:text-foreground",
                    isActive && "bg-muted text-foreground",
                  )
                }
              >
                <item.icon className="size-4" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        <div className="min-w-0">
          <header className="flex h-16 items-center justify-between gap-3 border-b bg-card px-4 lg:px-6">
            <div className="flex min-w-0 items-center gap-2">
              <Layers3 className="size-4 text-primary" />
              <span className="truncate text-sm font-medium">Supervised housing workflow</span>
            </div>
            <Badge variant="outline">API-backed</Badge>
          </header>
          <main className="min-w-0 p-4 lg:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
