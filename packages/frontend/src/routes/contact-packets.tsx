import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, RefreshCcw, Send, ShieldCheck, XCircle } from "lucide-react";

import {
  ApiError,
  completeUserCheck,
  createContactPacket,
  getListings,
  getUserChecks,
  type ContactPacket,
  type ListingSummary,
  type UserCheck,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

export function ContactPacketsRoute() {
  const queryClient = useQueryClient();
  const [selectedListingId, setSelectedListingId] = useState<string>("");
  const [latestPacket, setLatestPacket] = useState<ContactPacket | undefined>(undefined);
  const [latestCompletedCheck, setLatestCompletedCheck] = useState<UserCheck | undefined>(undefined);

  const listingsQuery = useQuery({
    queryKey: ["contact-packet-listings"],
    queryFn: () => getListings({ status: "recommended", limit: 10 }),
  });
  const checksQuery = useQuery({
    queryKey: ["user-checks"],
    queryFn: getUserChecks,
    refetchInterval: 30_000,
  });

  const listings = listingsQuery.data?.items ?? [];

  useEffect(() => {
    if (!selectedListingId && listings.length > 0) {
      setSelectedListingId(listings[0].id);
    }
  }, [listings, selectedListingId]);

  const selectedListing = useMemo(
    () => listings.find((listing) => listing.id === selectedListingId),
    [listings, selectedListingId],
  );

  const packetMutation = useMutation({
    mutationFn: () => createContactPacket({ listingId: selectedListingId }),
    onSuccess: (packet) => {
      setLatestPacket(packet);
      void queryClient.invalidateQueries({ queryKey: ["user-checks"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const completeMutation = useMutation({
    mutationFn: ({ checkId, decision }: { checkId: string; decision: "approved" | "rejected" }) =>
      completeUserCheck({
        checkId,
        decision,
        note: "Decision prise depuis l interface de demonstration.",
      }),
    onSuccess: (check) => {
      setLatestCompletedCheck(check);
      void queryClient.invalidateQueries({ queryKey: ["user-checks"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  function refreshAll() {
    void listingsQuery.refetch();
    void checksQuery.refetch();
  }

  const pendingChecks = checksQuery.data?.items ?? [];
  const loading = listingsQuery.isPending || checksQuery.isPending;
  const error = listingsQuery.error ?? checksQuery.error;

  if (loading) {
    return <ContactPacketsSkeleton />;
  }

  if (error) {
    return <RouteError error={error} onRetry={refreshAll} />;
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="grid min-w-0 gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Paquets</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{listings.length} annonces eligibles</span>
              <Badge variant="outline">{pendingChecks.length} checks en attente</Badge>
            </div>
          </div>
          <Button variant="outline" size="sm" type="button" onClick={refreshAll}>
            <RefreshCcw className="size-4" />
            Refresh
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Generation</CardTitle>
            <Badge variant="secondary">Supervise</Badge>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
            <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
              <span>Annonce</span>
              <Select
                value={selectedListingId}
                onChange={(event) => setSelectedListingId(event.target.value)}
              >
                {listings.map((listing) => (
                  <option key={listing.id} value={listing.id}>
                    {listing.title} - {listing.city ?? "ville inconnue"}
                  </option>
                ))}
              </Select>
            </label>
            <Button
              type="button"
              disabled={!selectedListingId || packetMutation.isPending}
              onClick={() => packetMutation.mutate()}
            >
              {packetMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
              Generer paquet
            </Button>
          </CardContent>
        </Card>

        <PacketPreview packet={latestPacket} listing={selectedListing} />
      </section>

      <aside className="grid content-start gap-4">
        <PendingChecksPanel
          checks={pendingChecks}
          latestCompletedCheck={latestCompletedCheck}
          pendingCheckId={completeMutation.variables?.checkId}
          error={completeMutation.error}
          isMutating={completeMutation.isPending}
          onComplete={(checkId, decision) => completeMutation.mutate({ checkId, decision })}
        />
      </aside>
    </div>
  );
}

function PacketPreview({
  packet,
  listing,
}: {
  packet: ContactPacket | undefined;
  listing: ListingSummary | undefined;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Paquet courant</CardTitle>
        {packet ? <Badge variant="success">{packet.status}</Badge> : <Badge variant="outline">A creer</Badge>}
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {packet ? (
          <>
            <div className="grid gap-2 rounded-md border bg-background p-3 md:grid-cols-2">
              <Fact label="Packet id" value={packet.id} />
              <Fact label="Check id" value={packet.user_check_id ?? "-"} />
              <Fact label="Annonce" value={listing?.title ?? packet.listing_id} />
              <Fact label="Langue" value={packet.language} />
            </div>
            <section className="grid gap-2">
              <h2 className="text-xs font-medium uppercase text-muted-foreground">Message</h2>
              <div className="whitespace-pre-wrap rounded-md border bg-background p-3 leading-6">
                {packet.message_draft}
              </div>
            </section>
            <section className="grid gap-2">
              <h2 className="text-xs font-medium uppercase text-muted-foreground">Questions</h2>
              <div className="grid gap-2">
                {packet.questions_to_ask.map((question) => (
                  <div key={question} className="rounded-md border bg-background px-3 py-2">
                    {question}
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : (
          <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
            Generez un paquet depuis une annonce recommandee pour creer la validation utilisateur.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PendingChecksPanel({
  checks,
  latestCompletedCheck,
  pendingCheckId,
  error,
  isMutating,
  onComplete,
}: {
  checks: UserCheck[];
  latestCompletedCheck: UserCheck | undefined;
  pendingCheckId: string | undefined;
  error: Error | null;
  isMutating: boolean;
  onComplete: (checkId: string, decision: "approved" | "rejected") => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Checks</CardTitle>
        <ShieldCheck className="size-4 text-primary" />
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {latestCompletedCheck ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-emerald-900">
            <div className="font-medium">Derniere validation</div>
            <div className="mt-1">
              {latestCompletedCheck.id} - {latestCompletedCheck.completed_with}
            </div>
          </div>
        ) : null}
        {error ? <RouteError error={error} /> : null}
        {checks.length > 0 ? (
          checks.map((check) => {
            const isPending = isMutating && pendingCheckId === check.id;
            return (
              <div key={check.id} className="grid gap-3 rounded-md border bg-background p-3">
                <div>
                  <div className="font-medium">{check.title}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{check.summary}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{check.resource_type}</Badge>
                  <Badge variant="warning">{check.status}</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={isMutating}
                    onClick={() => onComplete(check.id, "approved")}
                  >
                    {isPending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                    Approuver
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={isMutating}
                    onClick={() => onComplete(check.id, "rejected")}
                  >
                    <XCircle className="size-4" />
                    Rejeter
                  </Button>
                </div>
              </div>
            );
          })
        ) : (
          <div className="rounded-md border border-dashed p-4 text-muted-foreground">
            Aucun check en attente.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ContactPacketsSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="grid gap-4">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-28" />
        <Skeleton className="h-96" />
      </section>
      <Skeleton className="h-96" />
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-medium">{value}</div>
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
