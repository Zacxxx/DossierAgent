import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Clipboard,
  Copy,
  Loader2,
  MailCheck,
  RefreshCcw,
  Save,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import {
  ApiError,
  completeUserCheck,
  createContactPacket,
  getContactPackets,
  getListings,
  getUserChecks,
  markContactPacketUsed,
  patchContactPacket,
  type ContactPacket,
  type ListingSummary,
  type UserCheck,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const packetStatuses = ["ready_for_review", "approved", "rejected", "used", "archived"] as const;

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

type PacketPatchForm = {
  packetId: string;
  language: string;
  tone: string;
  status: string;
  messageDraft: string;
  questionsToAsk: string[];
};

export function ContactPacketsRoute() {
  const queryClient = useQueryClient();
  const [selectedListingId, setSelectedListingId] = useState<string>("");
  const [selectedPacketId, setSelectedPacketId] = useState<string | undefined>(undefined);
  const [latestCompletedCheck, setLatestCompletedCheck] = useState<UserCheck | undefined>(undefined);

  const listingsQuery = useQuery({
    queryKey: ["contact-packet-listings"],
    queryFn: () => getListings({ status: "recommended", limit: 10 }),
  });
  const packetsQuery = useQuery({
    queryKey: ["contact-packets"],
    queryFn: getContactPackets,
  });
  const checksQuery = useQuery({
    queryKey: ["user-checks"],
    queryFn: getUserChecks,
    refetchInterval: 30_000,
  });

  const listings = listingsQuery.data?.items ?? [];
  const packets = packetsQuery.data?.items ?? [];

  useEffect(() => {
    if (!selectedListingId && listings.length > 0) {
      setSelectedListingId(listings[0].id);
    }
  }, [listings, selectedListingId]);

  useEffect(() => {
    if (packets.length === 0) {
      setSelectedPacketId(undefined);
      return;
    }
    if (!selectedPacketId || !packets.some((packet) => packet.id === selectedPacketId)) {
      setSelectedPacketId(packets[0].id);
    }
  }, [packets, selectedPacketId]);

  const selectedListing = useMemo(
    () => listings.find((listing) => listing.id === selectedListingId),
    [listings, selectedListingId],
  );
  const selectedPacket = useMemo(
    () => packets.find((packet) => packet.id === selectedPacketId),
    [packets, selectedPacketId],
  );

  const packetMutation = useMutation({
    mutationFn: () => createContactPacket({ listingId: selectedListingId }),
    onSuccess: (packet) => {
      setSelectedPacketId(packet.id);
      upsertPacket(queryClient, packet);
      void queryClient.invalidateQueries({ queryKey: ["contact-packets"] });
      void queryClient.invalidateQueries({ queryKey: ["user-checks"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const patchMutation = useMutation({
    mutationFn: (form: PacketPatchForm) =>
      patchContactPacket({
        packetId: form.packetId,
        language: form.language,
        tone: form.tone,
        status: form.status,
        messageDraft: form.messageDraft,
        questionsToAsk: form.questionsToAsk,
      }),
    onSuccess: (packet) => {
      upsertPacket(queryClient, packet);
      void queryClient.invalidateQueries({ queryKey: ["contact-packets"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const markUsedMutation = useMutation({
    mutationFn: ({ packetId }: { packetId: string }) =>
      markContactPacketUsed({ packetId, channel: "manual_copy" }),
    onSuccess: (packet) => {
      upsertPacket(queryClient, packet);
      void queryClient.invalidateQueries({ queryKey: ["contact-packets"] });
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
    void packetsQuery.refetch();
    void checksQuery.refetch();
  }

  const pendingChecks = checksQuery.data?.items ?? [];
  const loading = listingsQuery.isPending || packetsQuery.isPending || checksQuery.isPending;
  const error = listingsQuery.error ?? packetsQuery.error ?? checksQuery.error;

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
              <Badge variant="outline">{packets.length} paquets</Badge>
              <Badge variant="outline">{pendingChecks.length} checks en attente</Badge>
            </div>
          </div>
          <Button variant="outline" size="sm" type="button" onClick={refreshAll}>
            <RefreshCcw className="size-4" />
            Refresh
          </Button>
        </div>

        <GenerationCard
          listings={listings}
          selectedListingId={selectedListingId}
          selectedListing={selectedListing}
          isPending={packetMutation.isPending}
          error={packetMutation.error}
          onListingChange={setSelectedListingId}
          onGenerate={() => packetMutation.mutate()}
        />

        <PacketWorkspace
          packets={packets}
          selectedPacket={selectedPacket}
          selectedPacketId={selectedPacketId}
          savingPacketId={patchMutation.variables?.packetId}
          markingPacketId={markUsedMutation.variables?.packetId}
          isSaving={patchMutation.isPending}
          isMarkingUsed={markUsedMutation.isPending}
          saveError={patchMutation.error}
          markUsedError={markUsedMutation.error}
          onSelect={setSelectedPacketId}
          onSave={(form) => patchMutation.mutate(form)}
          onMarkUsed={(packetId) => markUsedMutation.mutate({ packetId })}
        />
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

function GenerationCard({
  listings,
  selectedListingId,
  selectedListing,
  isPending,
  error,
  onListingChange,
  onGenerate,
}: {
  listings: ListingSummary[];
  selectedListingId: string;
  selectedListing: ListingSummary | undefined;
  isPending: boolean;
  error: Error | null;
  onListingChange: (listingId: string) => void;
  onGenerate: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Generation</CardTitle>
        <Badge variant="secondary">Supervise</Badge>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
          <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
            <span>Annonce</span>
            <Select value={selectedListingId} onChange={(event) => onListingChange(event.target.value)}>
              {listings.map((listing) => (
                <option key={listing.id} value={listing.id}>
                  {listing.title} - {listing.city ?? "ville inconnue"}
                </option>
              ))}
            </Select>
          </label>
          <Button type="button" disabled={!selectedListingId || isPending} onClick={onGenerate}>
            {isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            Generer paquet
          </Button>
        </div>
        {selectedListing ? (
          <div className="text-xs text-muted-foreground">
            {selectedListing.title} / {selectedListing.city ?? "-"} / score {selectedListing.fit_score ?? "-"}
          </div>
        ) : null}
        {error ? <RouteError error={error} /> : null}
      </CardContent>
    </Card>
  );
}

function PacketWorkspace({
  packets,
  selectedPacket,
  selectedPacketId,
  savingPacketId,
  markingPacketId,
  isSaving,
  isMarkingUsed,
  saveError,
  markUsedError,
  onSelect,
  onSave,
  onMarkUsed,
}: {
  packets: ContactPacket[];
  selectedPacket: ContactPacket | undefined;
  selectedPacketId: string | undefined;
  savingPacketId: string | undefined;
  markingPacketId: string | undefined;
  isSaving: boolean;
  isMarkingUsed: boolean;
  saveError: Error | null;
  markUsedError: Error | null;
  onSelect: (packetId: string) => void;
  onSave: (form: PacketPatchForm) => void;
  onMarkUsed: (packetId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>PacketEditor</CardTitle>
        {selectedPacket ? <Badge variant={packetStatusVariant(selectedPacket.status)}>{selectedPacket.status}</Badge> : null}
      </CardHeader>
      <CardContent>
        {packets.length > 0 ? (
          <div className="grid min-h-[560px] gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
            <div className="grid content-start gap-2">
              {packets.map((packet) => (
                <button
                  key={packet.id}
                  type="button"
                  className={cn(
                    "grid gap-2 rounded-md border bg-background p-3 text-left text-sm transition-colors",
                    "hover:bg-muted",
                    packet.id === selectedPacketId && "border-primary bg-muted",
                  )}
                  onClick={() => onSelect(packet.id)}
                >
                  <div className="flex min-w-0 items-center justify-between gap-2">
                    <span className="truncate font-medium">{packet.id}</span>
                    <Badge variant={packetStatusVariant(packet.status)}>{packet.status}</Badge>
                  </div>
                  <div className="line-clamp-2 text-xs text-muted-foreground">{packet.message_draft}</div>
                  <div className="text-xs text-muted-foreground">{formatDate(packet.updated_at)}</div>
                </button>
              ))}
            </div>
            {selectedPacket ? (
              <PacketEditor
                packet={selectedPacket}
                isSaving={isSaving && savingPacketId === selectedPacket.id}
                isMarkingUsed={isMarkingUsed && markingPacketId === selectedPacket.id}
                saveError={saveError}
                markUsedError={markUsedError}
                onSave={onSave}
                onMarkUsed={() => onMarkUsed(selectedPacket.id)}
              />
            ) : null}
          </div>
        ) : (
          <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
            Generez un paquet depuis une annonce recommandee pour creer la validation utilisateur.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PacketEditor({
  packet,
  isSaving,
  isMarkingUsed,
  saveError,
  markUsedError,
  onSave,
  onMarkUsed,
}: {
  packet: ContactPacket;
  isSaving: boolean;
  isMarkingUsed: boolean;
  saveError: Error | null;
  markUsedError: Error | null;
  onSave: (form: PacketPatchForm) => void;
  onMarkUsed: () => void;
}) {
  const [language, setLanguage] = useState(packet.language);
  const [tone, setTone] = useState(packet.tone);
  const [status, setStatus] = useState(packet.status);
  const [messageDraft, setMessageDraft] = useState(packet.message_draft);
  const [questionsDraft, setQuestionsDraft] = useState(packet.questions_to_ask.join("\n"));
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<Error | null>(null);

  useEffect(() => {
    setLanguage(packet.language);
    setTone(packet.tone);
    setStatus(packet.status);
    setMessageDraft(packet.message_draft);
    setQuestionsDraft(packet.questions_to_ask.join("\n"));
    setCopied(false);
    setCopyError(null);
  }, [packet.id]);

  const questions = splitQuestions(questionsDraft);

  function savePacket() {
    onSave({
      packetId: packet.id,
      language,
      tone,
      status,
      messageDraft,
      questionsToAsk: questions,
    });
  }

  async function copyPacket() {
    try {
      await copyTextToClipboard(formatPacketCopy(messageDraft, questions));
      setCopied(true);
      setCopyError(null);
    } catch (error) {
      setCopyError(error instanceof Error ? error : new Error("Copie impossible."));
    }
  }

  return (
    <div className="grid content-start gap-4">
      <div className="grid gap-3 rounded-md border bg-background p-3 md:grid-cols-2">
        <Fact label="Packet id" value={packet.id} />
        <Fact label="Listing" value={packet.listing_id} />
        <Fact label="Utilise" value={packet.used_at ? formatDate(packet.used_at) : "-"} />
        <Fact label="Canal" value={packet.used_channel ?? "-"} />
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Field label="Langue">
          <Select value={language} onChange={(event) => setLanguage(event.target.value)}>
            <option value="fr">fr</option>
            <option value="en">en</option>
          </Select>
        </Field>
        <Field label="Ton">
          <Select value={tone} onChange={(event) => setTone(event.target.value)}>
            <option value="polite_direct">polite_direct</option>
            <option value="warm">warm</option>
            <option value="formal">formal</option>
          </Select>
        </Field>
        <Field label="Statut">
          <Select value={status} onChange={(event) => setStatus(event.target.value)}>
            {packetStatuses.map((packetStatus) => (
              <option key={packetStatus} value={packetStatus}>
                {packetStatus}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <Field label="Message">
        <textarea
          aria-label="Message brouillon"
          className={textareaClassName}
          rows={10}
          value={messageDraft}
          onChange={(event) => setMessageDraft(event.target.value)}
        />
      </Field>

      <Field label="Questions">
        <textarea
          aria-label="Questions a poser"
          className={textareaClassName}
          rows={5}
          value={questionsDraft}
          onChange={(event) => setQuestionsDraft(event.target.value)}
        />
      </Field>

      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={isSaving} onClick={savePacket}>
          {isSaving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Enregistrer
        </Button>
        <Button type="button" variant="outline" onClick={copyPacket}>
          {copied ? <CheckCircle2 className="size-4" /> : <Copy className="size-4" />}
          {copied ? "Copie" : "Copier"}
        </Button>
        <Button type="button" variant="secondary" disabled={isMarkingUsed} onClick={onMarkUsed}>
          {isMarkingUsed ? <Loader2 className="size-4 animate-spin" /> : <MailCheck className="size-4" />}
          Marquer utilise
        </Button>
      </div>

      {copied ? (
        <div className="flex items-center gap-2 text-sm text-emerald-700">
          <Clipboard className="size-4" />
          Message copie pour envoi manuel.
        </div>
      ) : null}
      {copyError ? <RouteError error={copyError} /> : null}
      {saveError ? <RouteError error={saveError} /> : null}
      {markUsedError ? <RouteError error={markUsedError} /> : null}
    </div>
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
        <Skeleton className="h-[560px]" />
      </section>
      <Skeleton className="h-96" />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid content-start gap-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      {children}
    </label>
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
        <Button type="button" variant="outline" size="sm" className="w-fit bg-card" onClick={onRetry}>
          <RefreshCcw className="size-4" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function upsertPacket(
  queryClient: ReturnType<typeof useQueryClient>,
  packet: ContactPacket,
): void {
  queryClient.setQueryData<{ items: ContactPacket[] }>(["contact-packets"], (current) => {
    if (!current) return { items: [packet] };
    const existing = current.items.filter((item) => item.id !== packet.id);
    return { items: [packet, ...existing] };
  });
}

function packetStatusVariant(status: string): "success" | "warning" | "secondary" | "outline" {
  if (status === "approved" || status === "used") return "success";
  if (status === "ready_for_review") return "warning";
  if (status === "archived") return "secondary";
  return "outline";
}

function splitQuestions(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function formatPacketCopy(messageDraft: string, questions: string[]): string {
  if (questions.length === 0) return messageDraft;
  return `${messageDraft}\n\nQuestions:\n${questions.map((question) => `- ${question}`).join("\n")}`;
}

async function copyTextToClipboard(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back to the legacy copy path when browser permissions deny clipboard writes.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.focus();
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Copie impossible.");
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  return dateFormatter.format(new Date(value));
}

const textareaClassName = cn(
  "min-h-28 w-full rounded-md border border-input bg-card px-3 py-2 text-sm shadow-sm",
  "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
  "disabled:cursor-not-allowed disabled:opacity-50",
);
