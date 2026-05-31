import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Radar, RefreshCcw, Save } from "lucide-react";

import {
  ApiError,
  getMarketWatches,
  patchMarketWatch,
  runMarketWatchNow,
  type MarketWatch,
  type RunNowResponse,
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

const watchStatuses = ["active", "paused", "archived"] as const;
const watchFrequencies = ["hourly", "twice_daily", "daily", "weekly"] as const;

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function WatchesRoute() {
  const queryClient = useQueryClient();
  const [selectedWatchId, setSelectedWatchId] = useState<string | undefined>(undefined);
  const [latestRun, setLatestRun] = useState<RunNowResponse | undefined>(undefined);

  const watchesQuery = useQuery({
    queryKey: ["market-watches"],
    queryFn: getMarketWatches,
  });

  const watches = watchesQuery.data?.items ?? [];
  const selectedWatch = useMemo(
    () => watches.find((watch) => watch.id === selectedWatchId) ?? watches[0],
    [watches, selectedWatchId],
  );

  useEffect(() => {
    if (selectedWatchId && !watches.some((watch) => watch.id === selectedWatchId)) {
      setSelectedWatchId(undefined);
    }
  }, [watches, selectedWatchId]);

  const patchMutation = useMutation({
    mutationFn: patchMarketWatch,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["market-watches"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const runMutation = useMutation({
    mutationFn: runMarketWatchNow,
    onSuccess: (run) => {
      setLatestRun(run);
      void queryClient.invalidateQueries({ queryKey: ["market-watches"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (watchesQuery.isPending) {
    return <WatchesSkeleton />;
  }

  if (watchesQuery.isError) {
    return <RouteError error={watchesQuery.error} onRetry={() => watchesQuery.refetch()} />;
  }

  return (
    <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="grid min-w-0 gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Veilles</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{watches.length} veilles</span>
              <Badge variant="outline">API-backed</Badge>
            </div>
          </div>
          <Button variant="outline" size="sm" type="button" onClick={() => watchesQuery.refetch()}>
            <RefreshCcw className="size-4" />
            Refresh
          </Button>
        </div>

        <WatchTable
          watches={watches}
          selectedWatchId={selectedWatch?.id}
          runningWatchId={runMutation.variables?.watchId}
          isRunning={runMutation.isPending}
          onSelect={setSelectedWatchId}
          onRun={(watchId) =>
            runMutation.mutate({
              watchId,
              idempotencyKey: createIdempotencyKey(),
            })
          }
        />
      </section>

      <aside className="grid content-start gap-4">
        <WatchEditor
          watch={selectedWatch}
          isSaving={patchMutation.isPending && patchMutation.variables?.watchId === selectedWatch?.id}
          saveError={patchMutation.error}
          onSave={(payload) => patchMutation.mutate(payload)}
        />
        <RunNowResult result={latestRun} error={runMutation.error} />
      </aside>
    </div>
  );
}

function WatchTable({
  watches,
  selectedWatchId,
  runningWatchId,
  isRunning,
  onSelect,
  onRun,
}: {
  watches: MarketWatch[];
  selectedWatchId: string | undefined;
  runningWatchId: string | undefined;
  isRunning: boolean;
  onSelect: (watchId: string) => void;
  onRun: (watchId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>WatchTable</CardTitle>
        <Radar className="size-4 text-primary" />
      </CardHeader>
      <CardContent>
        {watches.length > 0 ? (
          <div className="overflow-x-auto">
            <Table className="min-w-[760px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Nom</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead>Frequence</TableHead>
                  <TableHead>Prochain run</TableHead>
                  <TableHead>Dernier run</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {watches.map((watch) => {
                  const running = isRunning && runningWatchId === watch.id;
                  return (
                    <TableRow
                      key={watch.id}
                      className={cn("cursor-pointer", selectedWatchId === watch.id && "bg-muted")}
                      onClick={() => onSelect(watch.id)}
                    >
                      <TableCell>
                        <div className="grid gap-1">
                          <span className="font-medium">{watch.name}</span>
                          <span className="text-xs text-muted-foreground">{watch.id}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={watch.status === "active" ? "success" : "outline"}>{watch.status}</Badge>
                      </TableCell>
                      <TableCell>{watch.frequency}</TableCell>
                      <TableCell>{formatDate(watch.next_run_at)}</TableCell>
                      <TableCell>{formatDate(watch.last_run_at)}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          type="button"
                          size="sm"
                          disabled={isRunning}
                          onClick={(event) => {
                            event.stopPropagation();
                            onRun(watch.id);
                          }}
                        >
                          {running ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                          Run now
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
            Aucune veille configuree.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function WatchEditor({
  watch,
  isSaving,
  saveError,
  onSave,
}: {
  watch: MarketWatch | undefined;
  isSaving: boolean;
  saveError: Error | null;
  onSave: (payload: {
    watchId: string;
    name: string;
    status: string;
    frequency: string;
    nextRunAt: string | null;
  }) => void;
}) {
  const [name, setName] = useState("");
  const [status, setStatus] = useState("active");
  const [frequency, setFrequency] = useState("daily");
  const [nextRunAt, setNextRunAt] = useState("");

  useEffect(() => {
    if (!watch) return;
    setName(watch.name);
    setStatus(watch.status);
    setFrequency(watch.frequency);
    setNextRunAt(watch.next_run_at ?? "");
  }, [watch?.id]);

  if (!watch) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>ScheduleEditor</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            Selectionnez une veille.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>ScheduleEditor</CardTitle>
        <Badge variant={status === "active" ? "success" : "outline"}>{status}</Badge>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <Field label="Nom">
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Statut">
            <Select value={status} onChange={(event) => setStatus(event.target.value)}>
              {watchStatuses.map((watchStatus) => (
                <option key={watchStatus} value={watchStatus}>
                  {watchStatus}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Frequence">
            <Select value={frequency} onChange={(event) => setFrequency(event.target.value)}>
              {watchFrequencies.map((watchFrequency) => (
                <option key={watchFrequency} value={watchFrequency}>
                  {watchFrequency}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Prochain run ISO">
          <Input value={nextRunAt} onChange={(event) => setNextRunAt(event.target.value)} />
        </Field>
        <Button
          type="button"
          disabled={isSaving || !name.trim()}
          onClick={() =>
            onSave({
              watchId: watch.id,
              name: name.trim(),
              status,
              frequency,
              nextRunAt: nextRunAt.trim() || null,
            })
          }
        >
          {isSaving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Enregistrer
        </Button>
        {saveError ? <RouteError error={saveError} /> : null}
        <div className="rounded-md border bg-background p-3">
          <div className="text-xs text-muted-foreground">Sources</div>
          <pre className="mt-2 overflow-x-auto text-xs">{JSON.stringify(watch.source_config, null, 2)}</pre>
        </div>
      </CardContent>
    </Card>
  );
}

function RunNowResult({ result, error }: { result: RunNowResponse | undefined; error: Error | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dernier lancement</CardTitle>
        {result ? <Badge variant="success">{result.status}</Badge> : <Badge variant="outline">idle</Badge>}
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {result ? (
          <>
            <Fact label="Run id" value={result.run_id} />
            <Fact label="Replay idempotent" value={result.idempotent_replay ? "Oui" : "Non"} />
            <pre className="overflow-x-auto rounded-md border bg-background p-3 text-xs">
              {JSON.stringify(result.summary, null, 2)}
            </pre>
          </>
        ) : (
          <div className="rounded-md border border-dashed p-4 text-muted-foreground">
            Aucun lancement manuel dans cette session.
          </div>
        )}
        {error ? <RouteError error={error} /> : null}
      </CardContent>
    </Card>
  );
}

function WatchesSkeleton() {
  return (
    <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="grid gap-4">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-96" />
      </section>
      <aside className="grid content-start gap-4">
        <Skeleton className="h-96" />
        <Skeleton className="h-64" />
      </aside>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">
      <span>{label}</span>
      {children}
    </label>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border bg-background p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-sm font-medium">{value}</div>
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

function createIdempotencyKey(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  return dateFormatter.format(new Date(value));
}
