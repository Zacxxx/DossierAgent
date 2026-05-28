import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { DashboardRoute } from "@/routes/dashboard";
import { ListingsRoute } from "@/routes/listings";
import { SectionRoute } from "@/routes/section";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardRoute /> },
      { path: "watches", element: <SectionRoute title="Veilles" /> },
      { path: "listings", element: <ListingsRoute /> },
      { path: "dossier", element: <SectionRoute title="Dossier" /> },
      { path: "contact-packets", element: <SectionRoute title="Paquets" /> },
      { path: "history", element: <SectionRoute title="Historique" /> },
    ],
  },
]);
