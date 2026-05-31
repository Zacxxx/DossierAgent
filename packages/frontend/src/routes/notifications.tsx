import { NotificationCenter } from "@/components/notification-center";

export function NotificationsRoute() {
  return (
    <div className="grid gap-4">
      <div>
        <h1 className="text-xl font-semibold">Notifications</h1>
        <div className="mt-1 text-sm text-muted-foreground">Alertes, scans et validations recentes</div>
      </div>
      <NotificationCenter limit={100} />
    </div>
  );
}
