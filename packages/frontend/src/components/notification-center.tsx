import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, Loader2, RefreshCcw } from "lucide-react";

import {
  ApiError,
  getNotifications,
  markNotificationRead,
  type Notification,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function NotificationCenter({
  unreadOnly = false,
  limit = 20,
}: {
  unreadOnly?: boolean;
  limit?: number;
}) {
  const queryClient = useQueryClient();
  const notificationsQuery = useQuery({
    queryKey: ["notifications", { unreadOnly, limit }],
    queryFn: () => getNotifications({ unreadOnly, limit }),
    refetchInterval: 30_000,
  });

  const markReadMutation = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const notifications = notificationsQuery.data?.items ?? [];
  const unreadCount = notifications.filter((notification) => notification.read_at === null).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Notifications</CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant={unreadCount > 0 ? "warning" : "outline"}>{unreadCount} non lues</Badge>
          <Bell className="size-4 text-primary" />
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {notificationsQuery.isPending ? (
          <NotificationSkeleton />
        ) : notificationsQuery.isError ? (
          <NotificationError
            error={notificationsQuery.error}
            onRetry={() => notificationsQuery.refetch()}
          />
        ) : notifications.length > 0 ? (
          notifications.map((notification) => (
            <NotificationItem
              key={notification.id}
              notification={notification}
              isMutating={
                markReadMutation.isPending && markReadMutation.variables === notification.id
              }
              onMarkRead={() => markReadMutation.mutate(notification.id)}
            />
          ))
        ) : (
          <div className="rounded-md border border-dashed p-4 text-muted-foreground">
            Aucune notification.
          </div>
        )}
        {markReadMutation.error ? <NotificationError error={markReadMutation.error} /> : null}
      </CardContent>
    </Card>
  );
}

function NotificationItem({
  notification,
  isMutating,
  onMarkRead,
}: {
  notification: Notification;
  isMutating: boolean;
  onMarkRead: () => void;
}) {
  const isRead = notification.read_at !== null;
  return (
    <div className="grid gap-2 rounded-md border bg-background p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium">{notification.title}</div>
          <div className="mt-1 text-xs text-muted-foreground">{notification.body}</div>
        </div>
        <Badge variant={isRead ? "outline" : "warning"}>{isRead ? "Lue" : "Non lue"}</Badge>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{notification.type}</span>
        <span>{formatDate(notification.created_at)}</span>
      </div>
      {notification.resource_type ? (
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{notification.resource_type}</Badge>
          {notification.resource_id ? <Badge variant="secondary">{notification.resource_id}</Badge> : null}
        </div>
      ) : null}
      {!isRead ? (
        <Button type="button" size="sm" variant="outline" disabled={isMutating} onClick={onMarkRead}>
          {isMutating ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
          Marquer lue
        </Button>
      ) : null}
    </div>
  );
}

function NotificationSkeleton() {
  return (
    <div className="grid gap-3">
      <Skeleton className="h-24" />
      <Skeleton className="h-24" />
    </div>
  );
}

function NotificationError({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const message = error instanceof ApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <div className="grid gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-amber-900">
      <div>{message}</div>
      {onRetry ? (
        <Button type="button" variant="outline" size="sm" className="w-fit bg-card" onClick={onRetry}>
          <RefreshCcw className="size-4" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function formatDate(value: string): string {
  return dateFormatter.format(new Date(value));
}
