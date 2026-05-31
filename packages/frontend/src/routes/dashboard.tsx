import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  FileWarning,
  Home,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";

import { ApiError, getDashboard, type DashboardListing } from "@/api/client";
import { NotificationCenter } from "@/components/notification-center";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const currencyFormatter = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function DashboardRoute() {
  const dashboardQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
    refetchInterval: 30_000,
  });

  if (dashboardQuery.isPending) {
    return <DashboardSkeleton />;
  }

  if (dashboardQuery.isError) {
    return (
      <DashboardError error={dashboardQuery.error} onRetry={() => dashboardQuery.refetch()} />
    );
  }

  const dashboard = dashboardQuery.data;
  const runStats = Object.entries(dashboard.latest_run.stats);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="grid min-w-0 gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Tableau de bord</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{dashboard.current_watch.name}</span>
              <Badge variant={dashboard.current_watch.status === "active" ? "success" : "outline"}>
                {dashboard.current_watch.status}
              </Badge>
            </div>
          </div>
          <Button variant="outline" size="sm" type="button" onClick={() => dashboardQuery.refetch()}>
            <RefreshCcw className="size-4" />
            Refresh
          </Button>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile
            label="Dernier run"
            value={dashboard.latest_run.status}
            detail={formatDate(dashboard.latest_run.completed_at)}
            icon={RefreshCcw}
          />
          <MetricTile
            label="Score dossier"
            value={`${dashboard.dossier.readiness_score}%`}
            detail={dashboard.dossier.can_contact ? "Contact possible" : "Contact bloque"}
            icon={ShieldCheck}
          />
          <MetricTile
            label="Checks"
            value={String(dashboard.pending_checks)}
            detail="Validations utilisateur"
            icon={CheckCircle2}
          />
          <MetricTile
            label="Notifications"
            value={String(dashboard.notifications_unread)}
            detail="Non lues"
            icon={AlertCircle}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Recommandations</CardTitle>
            <Badge variant="secondary">{dashboard.recommended_listings.length}</Badge>
          </CardHeader>
          <CardContent>
            {dashboard.recommended_listings.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-separate border-spacing-0 text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-muted-foreground">
                      <th className="border-b pb-2 font-medium">Annonce</th>
                      <th className="border-b pb-2 font-medium">Zone</th>
                      <th className="border-b pb-2 font-medium">Budget</th>
                      <th className="border-b pb-2 font-medium">Surface</th>
                      <th className="border-b pb-2 font-medium">Score</th>
                      <th className="border-b pb-2 font-medium">Statut</th>
                      <th className="border-b pb-2 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.recommended_listings.map((listing) => (
                      <ListingRow key={listing.id} listing={listing} />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
                Aucune annonce recommandee.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Run summary</CardTitle>
            <Badge variant="outline">{dashboard.latest_run.id}</Badge>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-5">
              {runStats.map(([key, value]) => (
                <div key={key} className="rounded-md border bg-background p-3">
                  <div className="text-xs text-muted-foreground">{humanizeKey(key)}</div>
                  <div className="mt-1 text-lg font-semibold">{String(value)}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <aside className="grid content-start gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Veille active</CardTitle>
            <Home className="size-4 text-primary" />
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <Fact label="Prochain scan" value={formatDate(dashboard.current_watch.next_run_at)} />
            <Fact label="Dernier scan" value={formatDate(dashboard.current_watch.last_run_at)} />
            <Fact label="Watch id" value={dashboard.current_watch.id} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Dossier</CardTitle>
            <FileWarning className="size-4 text-amber-700" />
          </CardHeader>
          <CardContent className="grid gap-3">
            <Fact label="Pieces valides" value={String(dashboard.dossier.valid_docs.length)} />
            <Fact label="Pieces manquantes" value={String(dashboard.dossier.missing_docs.length)} />
            <div className="grid gap-2">
              {dashboard.dossier.missing_docs.map((doc) => (
                <Badge key={doc} variant="warning" className="w-fit">
                  {doc}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        <NotificationCenter unreadOnly limit={5} />

      </aside>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="grid gap-4">
        <Skeleton className="h-12 w-72" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-80" />
      </section>
      <aside className="grid content-start gap-4">
        <Skeleton className="h-44" />
        <Skeleton className="h-44" />
      </aside>
    </div>
  );
}

function DashboardError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const message =
    error instanceof ApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dashboard unavailable</CardTitle>
        <Badge variant="warning">API</Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm text-muted-foreground">
        <p>{message}</p>
        <Button className="w-fit" variant="outline" type="button" onClick={onRetry}>
          <RefreshCcw className="size-4" />
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}

function MetricTile({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: typeof RefreshCcw;
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-medium uppercase text-muted-foreground">{label}</div>
        <Icon className="size-4 text-primary" />
      </div>
      <div className="mt-3 text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}

function ListingRow({ listing }: { listing: DashboardListing }) {
  const primaryImageUrl = listing.image_urls[0];
  const sourceUrl = listing.canonical_url ?? listing.source_url;

  return (
    <tr className="align-top">
      <td className="border-b py-3 pr-4">
        <div className="flex min-w-0 items-center gap-3">
          {primaryImageUrl ? (
            <img
              src={primaryImageUrl}
              alt={listing.title}
              className="size-14 shrink-0 rounded-md border object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex size-14 shrink-0 items-center justify-center rounded-md border border-dashed bg-muted text-xs text-muted-foreground">
              Image
            </div>
          )}
          <div className="min-w-0">
            <div className="truncate font-medium">{listing.title}</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {listing.risk_flags.map((risk) => (
                <Badge key={risk} variant="warning">
                  {risk}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </td>
      <td className="border-b py-3 pr-4 text-muted-foreground">
        {listing.city}
        {listing.district ? ` / ${listing.district}` : ""}
      </td>
      <td className="border-b py-3 pr-4">{formatCurrency(listing.price, listing.currency)}</td>
      <td className="border-b py-3 pr-4">{formatSurface(listing.surface, listing.rooms)}</td>
      <td className="border-b py-3 pr-4">
        <Badge variant="secondary">{listing.fit_score ?? "-"}</Badge>
      </td>
      <td className="border-b py-3 pr-4">{listing.status}</td>
      <td className="border-b py-3 pr-4">
        {sourceUrl ? (
          <Button variant="ghost" size="sm" asChild title="Explorer l'annonce">
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="size-4" />
              Explorer
            </a>
          </Button>
        ) : (
          <Button variant="ghost" size="sm" disabled title="Source indisponible">
            <ExternalLink className="size-4" />
            Explorer
          </Button>
        )}
      </td>
    </tr>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b pb-2 last:border-b-0 last:pb-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-medium">{value}</span>
    </div>
  );
}

function formatCurrency(value: number | null, currency: string) {
  if (value === null) return "-";
  if (currency === "EUR") return currencyFormatter.format(value);
  return `${value} ${currency}`;
}

function formatSurface(surface: number | null, rooms: number | null) {
  const parts = [];
  if (surface !== null) parts.push(`${surface} m2`);
  if (rooms !== null) parts.push(`${rooms} pieces`);
  return parts.length > 0 ? parts.join(" / ") : "-";
}

function formatDate(value: string | null) {
  if (value === null) return "-";
  return dateFormatter.format(new Date(value));
}

function humanizeKey(value: string) {
  return value.replaceAll("_", " ");
}
