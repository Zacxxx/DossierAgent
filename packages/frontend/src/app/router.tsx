import { createBrowserRouter } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { AiChatRoute } from "@/routes/ai-chat";
import { AuthRoute } from "@/routes/auth";
import { ContactPacketsRoute } from "@/routes/contact-packets";
import { DashboardRoute } from "@/routes/dashboard";
import { DossierRoute } from "@/routes/dossier";
import { HistoryRoute } from "@/routes/history";
import { ListingsRoute } from "@/routes/listings";
import { NotificationsRoute } from "@/routes/notifications";
import { SettingsRoute } from "@/routes/settings";
import { WatchesRoute } from "@/routes/watches";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardRoute /> },
      { path: "auth", element: <AuthRoute /> },
      { path: "ai-chat", element: <AiChatRoute /> },
      { path: "watches", element: <WatchesRoute /> },
      { path: "listings", element: <ListingsRoute /> },
      { path: "dossier", element: <DossierRoute /> },
      { path: "contact-packets", element: <ContactPacketsRoute /> },
      { path: "notifications", element: <NotificationsRoute /> },
      { path: "history", element: <HistoryRoute /> },
      { path: "settings", element: <SettingsRoute /> },
    ],
  },
]);
