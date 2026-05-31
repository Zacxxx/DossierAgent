import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  BookmarkPlus,
  ExternalLink,
  Loader2,
  RefreshCcw,
  Search,
  Send,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import {
  ApiError,
  getListing,
  getListings,
  listingStatusValues,
  patchListingStatus,
  type ListingDetail,
  type ListingFilters,
  type ListingStatus,
  type ListingSummary,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const currencyFormatter = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

type FilterForm = {
  q: string;
  status: "all" | ListingStatus;
  city: string;
  district: string;
  maxPrice: string;
  minSurface: string;
  minScore: string;
};

const defaultFilterForm: FilterForm = {
  q: "",
  status: "all",
  city: "",
  district: "",
  maxPrice: "",
  minSurface: "",
  minScore: "",
};

const decisionActions: Array<{
  status: ListingStatus;
  label: string;
  icon: typeof BookmarkPlus;
  variant: "default" | "outline" | "secondary" | "ghost";
}> = [
  { status: "saved", label: "Sauver", icon: BookmarkPlus, variant: "default" },
  { status: "rejected", label: "Rejeter", icon: XCircle, variant: "outline" },
  { status: "archived", label: "Archiver", icon: Archive, variant: "secondary" },
];

export function ListingsRoute() {
  const queryClient = useQueryClient();
  const [filterForm, setFilterForm] = useState<FilterForm>(defaultFilterForm);
  const [activeFilters, setActiveFilters] = useState<ListingFilters>(() =>
    formToFilters(defaultFilterForm),
  );
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [selectedListingId, setSelectedListingId] = useState<string | undefined>(undefined);
  const [pendingStatus, setPendingStatus] = useState<ListingStatus | undefined>(undefined);

  const listFilters = useMemo(
    () => ({ ...activeFilters, cursor, limit: 20 }),
    [activeFilters, cursor],
  );
  const listingsQuery = useQuery({
    queryKey: ["listings", listFilters],
    queryFn: () => getListings(listFilters),
  });

  const listingDetailQuery = useQuery({
    queryKey: ["listing", selectedListingId],
    queryFn: () => getListing(selectedListingId as string),
    enabled: selectedListingId !== undefined,
  });

  const decisionMutation = useMutation({
    mutationFn: ({ listingId, status }: { listingId: string; status: ListingStatus }) =>
      patchListingStatus(listingId, status),
    onMutate: ({ status }) => setPendingStatus(status),
    onSuccess: (updatedListing) => {
      queryClient.setQueryData(["listing", updatedListing.id], updatedListing);
      void queryClient.invalidateQueries({ queryKey: ["listings"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onSettled: () => setPendingStatus(undefined),
  });

  useEffect(() => {
    const listings = listingsQuery.data?.items ?? [];
    if (listings.length === 0) {
      setSelectedListingId(undefined);
      return;
    }

    if (!selectedListingId || !listings.some((listing) => listing.id === selectedListingId)) {
      setSelectedListingId(listings[0].id);
    }
  }, [listingsQuery.data?.items, selectedListingId]);

  function submitFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCursor(undefined);
    setSelectedListingId(undefined);
    setActiveFilters(formToFilters(filterForm));
  }

  function resetFilters() {
    setFilterForm(defaultFilterForm);
    setCursor(undefined);
    setSelectedListingId(undefined);
    setActiveFilters(formToFilters(defaultFilterForm));
  }

  function applyDecision(status: ListingStatus) {
    if (selectedListingId === undefined) return;
    decisionMutation.mutate({ listingId: selectedListingId, status });
  }

  const selectedListing = listingDetailQuery.data;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Annonces</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>{listingsQuery.data?.total ?? 0} resultats</span>
            {listingsQuery.data ? <Badge variant="outline">{listingsQuery.data.source}</Badge> : null}
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          type="button"
          onClick={() => {
            void listingsQuery.refetch();
            void listingDetailQuery.refetch();
          }}
        >
          <RefreshCcw className="size-4" />
          Refresh
        </Button>
      </div>

      <form
        className="grid gap-3 rounded-lg border bg-card p-3 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-[minmax(220px,1fr)_150px_150px_130px_120px_120px_110px_auto]"
        onSubmit={submitFilters}
      >
        <FilterField label="Recherche">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filterForm.q}
              onChange={(event) => setFilterForm((value) => ({ ...value, q: event.target.value }))}
              className="pl-9"
              placeholder="Titre, agence, mots cles"
            />
          </div>
        </FilterField>
        <FilterField label="Statut">
          <Select
            value={filterForm.status}
            onChange={(event) =>
              setFilterForm((value) => ({
                ...value,
                status: event.target.value as FilterForm["status"],
              }))
            }
          >
            <option value="all">Tous</option>
            {listingStatusValues.map((status) => (
              <option key={status} value={status}>
                {humanizeStatus(status)}
              </option>
            ))}
          </Select>
        </FilterField>
        <FilterField label="Ville">
          <Input
            value={filterForm.city}
            onChange={(event) => setFilterForm((value) => ({ ...value, city: event.target.value }))}
          />
        </FilterField>
        <FilterField label="Quartier">
          <Input
            value={filterForm.district}
            onChange={(event) =>
              setFilterForm((value) => ({ ...value, district: event.target.value }))
            }
          />
        </FilterField>
        <FilterField label="Budget max">
          <Input
            inputMode="numeric"
            type="number"
            min="0"
            value={filterForm.maxPrice}
            onChange={(event) =>
              setFilterForm((value) => ({ ...value, maxPrice: event.target.value }))
            }
          />
        </FilterField>
        <FilterField label="Surface min">
          <Input
            inputMode="numeric"
            type="number"
            min="0"
            value={filterForm.minSurface}
            onChange={(event) =>
              setFilterForm((value) => ({ ...value, minSurface: event.target.value }))
            }
          />
        </FilterField>
        <FilterField label="Score min">
          <Input
            inputMode="numeric"
            type="number"
            min="0"
            max="100"
            value={filterForm.minScore}
            onChange={(event) =>
              setFilterForm((value) => ({ ...value, minScore: event.target.value }))
            }
          />
        </FilterField>
        <div className="flex items-end gap-2">
          <Button type="submit" className="flex-1 lg:flex-none">
            Filtrer
          </Button>
          <Button type="button" variant="ghost" onClick={resetFilters}>
            Reset
          </Button>
        </div>
      </form>

      <div className="grid min-h-[640px] gap-4 xl:grid-cols-[minmax(560px,1.2fr)_minmax(320px,0.8fr)]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Liste</CardTitle>
            {listingsQuery.isFetching ? (
              <Badge variant="secondary">
                <Loader2 className="mr-1 size-3 animate-spin" />
                Sync
              </Badge>
            ) : (
              <Badge variant="outline">Score desc</Badge>
            )}
          </CardHeader>
          <CardContent>
            {listingsQuery.isPending ? (
              <ListingsSkeleton />
            ) : listingsQuery.isError ? (
              <RouteError error={listingsQuery.error} onRetry={() => listingsQuery.refetch()} />
            ) : listingsQuery.data.items.length === 0 ? (
              <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
                Aucune annonce ne correspond aux filtres.
              </div>
            ) : (
              <div className="grid gap-3">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="min-w-[240px]">Annonce</TableHead>
                      <TableHead>Budget</TableHead>
                      <TableHead>Surface</TableHead>
                      <TableHead>Ville</TableHead>
                      <TableHead>Score</TableHead>
                      <TableHead>Statut</TableHead>
                      <TableHead className="w-12">Lien</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {listingsQuery.data.items.map((listing) => (
                      <ListingTableRow
                        key={listing.id}
                        listing={listing}
                        isSelected={listing.id === selectedListingId}
                        onSelect={() => setSelectedListingId(listing.id)}
                      />
                    ))}
                  </TableBody>
                </Table>
                <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
                  <span>
                    {listingsQuery.data.items.length} affiches sur {listingsQuery.data.total}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={listingsQuery.data.next_cursor === null || listingsQuery.isFetching}
                    onClick={() => setCursor(listingsQuery.data?.next_cursor ?? undefined)}
                  >
                    Page suivante
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <ListingDetailPane
          listing={selectedListing}
          isLoading={listingDetailQuery.isPending && selectedListingId !== undefined}
          error={listingDetailQuery.error}
          onRetry={() => listingDetailQuery.refetch()}
          onDecision={applyDecision}
          pendingStatus={pendingStatus}
          isMutating={decisionMutation.isPending}
          mutationError={decisionMutation.error}
        />
      </div>
    </div>
  );
}

function ListingTableRow({
  listing,
  isSelected,
  onSelect,
}: {
  listing: ListingSummary;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const primaryImageUrl = listing.image_urls[0];
  const sourceUrl = listing.canonical_url ?? listing.source_url;
  return (
    <TableRow className={cn(isSelected && "bg-muted hover:bg-muted")}>
      <TableCell>
        <div className="flex min-w-0 items-center gap-3">
          <ListingThumbnail imageUrl={primaryImageUrl} title={listing.title} className="size-14" />
          <button
            type="button"
            className="grid min-w-0 gap-1 text-left"
            onClick={onSelect}
            aria-pressed={isSelected}
          >
            <span className="truncate font-medium text-foreground">{listing.title}</span>
            <span className="truncate text-xs text-muted-foreground">
              {listing.district ?? listing.watch_id}
            </span>
          </button>
        </div>
      </TableCell>
      <TableCell className="whitespace-nowrap font-medium">
        {formatCurrency(listing.price, listing.currency)}
      </TableCell>
      <TableCell className="whitespace-nowrap">{formatSurface(listing.surface, listing.rooms)}</TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">{listing.city ?? "-"}</TableCell>
      <TableCell>
        <ScoreBadge score={listing.fit_score} />
      </TableCell>
      <TableCell>
        <StatusBadge status={listing.status} />
      </TableCell>
      <TableCell>
        {sourceUrl ? (
          <Button variant="ghost" size="icon" asChild title="Explorer l'annonce">
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="size-4" />
            </a>
          </Button>
        ) : (
          <Button variant="ghost" size="icon" disabled title="Source indisponible">
            <ExternalLink className="size-4" />
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

function ListingDetailPane({
  listing,
  isLoading,
  error,
  onRetry,
  onDecision,
  pendingStatus,
  isMutating,
  mutationError,
}: {
  listing: ListingDetail | undefined;
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
  onDecision: (status: ListingStatus) => void;
  pendingStatus: ListingStatus | undefined;
  isMutating: boolean;
  mutationError: Error | null;
}) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Detail annonce</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-28" />
          <Skeleton className="h-32" />
          <Skeleton className="h-20" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Detail annonce</CardTitle>
          <Badge variant="warning">API</Badge>
        </CardHeader>
        <CardContent>
          <RouteError error={error} onRetry={onRetry} />
        </CardContent>
      </Card>
    );
  }

  if (!listing) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Detail annonce</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">Selectionnez une annonce.</CardContent>
      </Card>
    );
  }

  const primaryImageUrl = listing.image_urls[0];
  const sourceUrl = listing.canonical_url || listing.source_url;

  return (
    <Card className="min-w-0">
      <CardHeader>
        <div className="min-w-0">
          <CardTitle className="truncate">{listing.title}</CardTitle>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <StatusBadge status={listing.status} />
            <ScoreBadge score={listing.fit_score} />
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" asChild title="Explorer l'annonce">
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="size-4" />
              Explorer
            </a>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <section className="grid gap-2">
          <ListingThumbnail
            imageUrl={primaryImageUrl}
            title={listing.title}
            className="h-56 w-full"
          />
          {listing.image_urls.length > 1 ? (
            <div className="grid grid-cols-4 gap-2">
              {listing.image_urls.slice(1, 5).map((imageUrl) => (
                <ListingThumbnail
                  key={imageUrl}
                  imageUrl={imageUrl}
                  title={listing.title}
                  className="h-20 w-full"
                />
              ))}
            </div>
          ) : null}
        </section>

        <div className="grid gap-2 rounded-md border bg-background p-3 sm:grid-cols-2">
          <Fact label="Prix" value={formatCurrency(listing.price, listing.currency)} />
          <Fact label="Surface" value={formatSurface(listing.surface, listing.rooms)} />
          <Fact label="Zone" value={formatLocation(listing)} />
          <Fact label="Agence" value={listing.agency_name ?? "-"} />
          <Fact label="Source" value={listing.source} />
          <Fact label="Premier vu" value={formatDate(listing.first_seen_at)} />
          <Fact label="Dernier vu" value={formatDate(listing.last_seen_at)} />
        </div>

        {listing.description ? (
          <section className="grid gap-2">
            <h3 className="text-xs font-medium uppercase text-muted-foreground">Description</h3>
            <p className="leading-6 text-muted-foreground">{listing.description}</p>
          </section>
        ) : null}

        <section className="grid gap-2">
          <h3 className="text-xs font-medium uppercase text-muted-foreground">Raisons</h3>
          {listing.explanation.length > 0 ? (
            <ul className="grid gap-2">
              {listing.explanation.map((reason) => (
                <li key={reason} className="rounded-md border bg-background px-3 py-2">
                  {reason}
                </li>
              ))}
            </ul>
          ) : (
            <div className="rounded-md border border-dashed p-3 text-muted-foreground">
              Aucune raison disponible.
            </div>
          )}
        </section>

        <section className="grid gap-2">
          <h3 className="flex items-center gap-2 text-xs font-medium uppercase text-muted-foreground">
            <ShieldAlert className="size-4" />
            Risques
          </h3>
          {listing.risk_flags.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {listing.risk_flags.map((risk) => (
                <Badge key={risk} variant="warning">
                  {humanizeStatus(risk)}
                </Badge>
              ))}
            </div>
          ) : (
            <Badge variant="success" className="w-fit">
              Aucun drapeau
            </Badge>
          )}
        </section>

        {mutationError ? <RouteError error={mutationError} /> : null}

        <div className="flex flex-wrap gap-2 border-t pt-4">
          {decisionActions.map((action) => {
            const Icon = action.icon;
            const isPending = pendingStatus === action.status;
            return (
              <Button
                key={action.status}
                type="button"
                variant={action.variant}
                disabled={isMutating || listing.status === action.status}
                onClick={() => onDecision(action.status)}
              >
                {isPending ? <Loader2 className="size-4 animate-spin" /> : <Icon className="size-4" />}
                {action.label}
              </Button>
            );
          })}
          <Button type="button" variant="outline" disabled title="Sprint 5">
            <Send className="size-4" />
            Generer packet
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ListingThumbnail({
  imageUrl,
  title,
  className,
}: {
  imageUrl: string | undefined;
  title: string;
  className?: string;
}) {
  if (!imageUrl) {
    return (
      <div
        className={cn(
          "flex shrink-0 items-center justify-center rounded-md border border-dashed bg-muted text-xs text-muted-foreground",
          className,
        )}
      >
        Image
      </div>
    );
  }

  return (
    <img
      src={imageUrl}
      alt={title}
      className={cn("shrink-0 rounded-md border object-cover", className)}
      loading="lazy"
    />
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
      <span>{label}</span>
      {children}
    </label>
  );
}

function ListingsSkeleton() {
  return (
    <div className="grid gap-2">
      {Array.from({ length: 8 }).map((_, index) => (
        <Skeleton key={index} className="h-14" />
      ))}
    </div>
  );
}

function RouteError({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const message = error instanceof ApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <div className="grid gap-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      <div>{message}</div>
      {onRetry ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-fit bg-card"
          onClick={onRetry}
        >
          <RefreshCcw className="size-4" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) {
    return <Badge variant="outline">-</Badge>;
  }
  return (
    <Badge variant={score >= 80 ? "success" : score >= 60 ? "secondary" : "warning"}>
      {score}
    </Badge>
  );
}

function StatusBadge({ status }: { status: ListingStatus }) {
  const variant =
    status === "recommended" || status === "saved"
      ? "success"
      : status === "rejected" || status === "trash"
        ? "warning"
        : "outline";
  return <Badge variant={variant}>{humanizeStatus(status)}</Badge>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-medium">{value}</div>
    </div>
  );
}

function formToFilters(form: FilterForm): ListingFilters {
  return {
    q: nonEmpty(form.q),
    status: form.status === "all" ? undefined : form.status,
    city: nonEmpty(form.city),
    district: nonEmpty(form.district),
    max_price: optionalNumber(form.maxPrice),
    min_surface: optionalNumber(form.minSurface),
    min_score: optionalNumber(form.minScore),
    limit: 20,
  };
}

function nonEmpty(value: string) {
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

function optionalNumber(value: string) {
  const trimmed = value.trim();
  if (trimmed === "") return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
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

function formatLocation(listing: ListingDetail) {
  return [listing.city, listing.district, listing.postal_code].filter(Boolean).join(" / ") || "-";
}

function formatDate(value: string | null) {
  if (value === null) return "-";
  return dateFormatter.format(new Date(value));
}

function humanizeStatus(value: string) {
  return value.replaceAll("_", " ");
}
