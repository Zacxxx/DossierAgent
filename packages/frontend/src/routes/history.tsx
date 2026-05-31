import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Clock3, RefreshCcw, Workflow } from "lucide-react";

import {
  ApiError,
  getAgentRun,
  getAgentRunEvents,
  getDashboard,
  type AgentEvent,
  type AgentRun,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function HistoryRoute() {
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>(undefined);

  const dashboardQuery = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
    refetchInterval: 30_000,
    refetchOnMount: "always",
    staleTime: 0,
  });

  const latestRunId = dashboardQuery.data?.latest_run.id;

  useEffect(() => {
    if (latestRunId && latestRunId !== selectedRunId) {
      setSelectedRunId(latestRunId);
    }
  }, [latestRunId, selectedRunId]);

  const runQuery = useQuery({
    queryKey: ["agent-run", selectedRunId],
    queryFn: () => getAgentRun(selectedRunId as string),
    enabled: selectedRunId !== undefined,
    refetchInterval: 15_000,
  });

  const eventsQuery = useQuery({
    queryKey: ["agent-run-events", selectedRunId],
    queryFn: () => getAgentRunEvents(selectedRunId as string),
    enabled: selectedRunId !== undefined,
    refetchInterval: 15_000,
  });

  const loading = dashboardQuery.isPending || (selectedRunId !== undefined && runQuery.isPending);
  const error = dashboardQuery.error ?? runQuery.error ?? eventsQuery.error;

  if (loading) {
    return <HistorySkeleton />;
  }

  if (error) {
    return (
      <RouteError
        error={error}
        onRetry={() => {
          void dashboardQuery.refetch();
          void runQuery.refetch();
          void eventsQuery.refetch();
        }}
      />
    );
  }

  const run = runQuery.data;
  const events = eventsQuery.data?.items ?? [];

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="grid min-w-0 gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Historique</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{selectedRunId ?? "aucun run"}</span>
              {run ? <Badge variant={run.status === "failed" ? "warning" : "success"}>{run.status}</Badge> : null}
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            type="button"
            onClick={() => {
              void dashboardQuery.refetch();
              void runQuery.refetch();
              void eventsQuery.refetch();
            }}
          >
            <RefreshCcw className="size-4" />
            Refresh
          </Button>
        </div>

        <RunEventTimeline run={run} events={events} eventsPending={eventsQuery.isPending} />
      </section>

      <aside className="grid content-start gap-4">
        <RunSummary run={run} latestRunId={latestRunId} onSelectLatest={() => setSelectedRunId(latestRunId)} />
      </aside>
    </div>
  );
}

function RunEventTimeline({
  run,
  events,
  eventsPending,
}: {
  run: AgentRun | undefined;
  events: AgentEvent[];
  eventsPending: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>RunEventTimeline</CardTitle>
        <Workflow className="size-4 text-primary" />
      </CardHeader>
      <CardContent>
        {!run ? (
          <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
            Aucun run disponible.
          </div>
        ) : eventsPending ? (
          <div className="grid gap-3">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : events.length > 0 ? (
          <div className="grid gap-3">
            {events.map((event) => (
              <div key={event.id} className="grid gap-2 rounded-md border bg-background p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {event.severity === "warning" ? (
                      <AlertCircle className="size-4 text-amber-700" />
                    ) : (
                      <CheckCircle2 className="size-4 text-emerald-700" />
                    )}
                    <span className="font-medium">{event.type}</span>
                  </div>
                  <Badge variant={event.severity === "warning" ? "warning" : "outline"}>
                    {event.severity}
                  </Badge>
                </div>
                <div className="text-muted-foreground">{event.message}</div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock3 className="size-3.5" />
                  {formatDate(event.created_at)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
            Aucun evenement pour ce run.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RunSummary({
  run,
  latestRunId,
  onSelectLatest,
}: {
  run: AgentRun | undefined;
  latestRunId: string | undefined;
  onSelectLatest: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Run detail</CardTitle>
        {run ? <Badge variant="outline">{run.current_step}</Badge> : null}
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {run ? (
          <>
            <Fact label="Run id" value={run.id} />
            <Fact label="Watch" value={run.watch_id} />
            <Fact label="Trigger" value={run.trigger_type} />
            <Fact label="Intent" value={run.intent} />
            <Fact label="Cree" value={formatDate(run.created_at)} />
            <Fact label="Complete" value={formatDate(run.completed_at)} />
            <pre className="overflow-x-auto rounded-md border bg-background p-3 text-xs">
              {JSON.stringify(run.summary, null, 2)}
            </pre>
          </>
        ) : (
          <div className="rounded-md border border-dashed p-4 text-muted-foreground">
            Aucun detail disponible.
          </div>
        )}
        {latestRunId ? (
          <Button type="button" variant="outline" onClick={onSelectLatest}>
            Dernier run
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function HistorySkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="grid gap-4">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-96" />
      </section>
      <Skeleton className="h-96" />
    </div>
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

function RouteError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const message = error instanceof ApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Historique indisponible</CardTitle>
        <Badge variant="warning">API</Badge>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="text-muted-foreground">{message}</div>
        <Button type="button" variant="outline" className="w-fit" onClick={onRetry}>
          <RefreshCcw className="size-4" />
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  return dateFormatter.format(new Date(value));
}
