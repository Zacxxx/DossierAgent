import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Send, ShieldAlert, Terminal } from "lucide-react";

import { ApiError, runAgentCommand, type AgentCommandResponse } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const suggestedCommands = [
  "Lance un scan de la veille",
  "Analyse mon dossier",
  "Affiche les annonces recommandees",
];

const invalidatedQueryKeys = [
  ["dashboard"],
  ["listings"],
  ["listing"],
  ["dossier-readiness"],
  ["dossier-documents"],
  ["user-checks"],
  ["contact-packet-listings"],
];

export function CommandComposer() {
  const queryClient = useQueryClient();
  const [command, setCommand] = useState("");
  const [pendingPlan, setPendingPlan] = useState<AgentCommandResponse | null>(null);
  const [lastResponse, setLastResponse] = useState<AgentCommandResponse | null>(null);

  const planMutation = useMutation({
    mutationFn: runAgentCommand,
    onSuccess: (response) => {
      setPendingPlan(response.status === "accepted" ? response : null);
      setLastResponse(response);
    },
  });

  const executeMutation = useMutation({
    mutationFn: runAgentCommand,
    onSuccess: (response) => {
      setPendingPlan(null);
      for (const queryKey of invalidatedQueryKeys) {
        void queryClient.invalidateQueries({ queryKey });
      }
      setLastResponse(response);
      if (response.status === "accepted") setCommand("");
    },
  });

  const isBusy = planMutation.isPending || executeMutation.isPending;
  const canConfirmPlan = pendingPlan?.status === "accepted" && command.trim().length > 0;
  const commandError = planMutation.error ?? executeMutation.error;

  function submitCommand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedCommand = command.trim();
    if (!trimmedCommand || isBusy) return;
    planMutation.mutate({ command: trimmedCommand, execute: false });
  }

  function confirmPlan() {
    const trimmedCommand = command.trim();
    if (!trimmedCommand || !canConfirmPlan || isBusy) return;
    executeMutation.mutate({ command: trimmedCommand, execute: true });
  }

  function applySuggestion(suggestion: string) {
    setPendingPlan(null);
    setCommand(suggestion);
  }

  function updateCommand(value: string) {
    setPendingPlan(null);
    setCommand(value);
  }

  return (
    <div className="grid min-w-0 flex-1 gap-1.5 lg:max-w-3xl">
      <form className="flex min-w-0 items-center gap-2" onSubmit={submitCommand}>
        <div className="relative min-w-0 flex-1">
          <Terminal className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Commande agent"
            className="h-9 pl-9"
            value={command}
            placeholder="Commande supervisee"
            onChange={(event) => updateCommand(event.target.value)}
          />
        </div>
        <Button
          type="submit"
          size="icon"
          disabled={!command.trim() || isBusy}
          title="Interpreter la commande"
        >
          {planMutation.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Send className="size-4" />
          )}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={!canConfirmPlan || isBusy}
          onClick={confirmPlan}
        >
          {executeMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
          Valider
        </Button>
      </form>

      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        {suggestedCommands.map((suggestion) => (
          <Button
            key={suggestion}
            type="button"
            variant="ghost"
            size="sm"
            className="hidden h-7 px-2 text-xs xl:inline-flex"
            onClick={() => applySuggestion(suggestion)}
          >
            {suggestion}
          </Button>
        ))}
        {pendingPlan ? (
          <CommandPlanBadge response={pendingPlan} />
        ) : lastResponse ? (
          <CommandStatusBadge response={lastResponse} />
        ) : null}
        {commandError ? (
          <span className="truncate text-xs text-destructive">
            {formatCommandError(commandError)}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function CommandPlanBadge({ response }: { response: AgentCommandResponse }) {
  return (
    <Badge variant="outline" className="min-w-0 gap-1">
      <CheckCircle2 className="size-3.5 shrink-0 text-primary" />
      <span className="truncate">
        Plan: {response.intent} {formatParameters(response.parameters)}
      </span>
    </Badge>
  );
}

function CommandStatusBadge({ response }: { response: AgentCommandResponse }) {
  const Icon = response.status === "accepted" ? CheckCircle2 : ShieldAlert;
  return (
    <Badge
      variant={response.status === "accepted" ? "success" : "warning"}
      className="ml-auto min-w-0 gap-1"
    >
      <Icon className="size-3.5 shrink-0" />
      <span className="truncate">{statusLabel(response)}</span>
    </Badge>
  );
}

function statusLabel(response: AgentCommandResponse): string {
  if (response.status === "rejected") return `Refusee: ${response.summary}`;
  const resultType = response.result?.type;
  if (resultType === "command_plan") return `Plan: ${response.intent}`;
  if (resultType === "agent_run") return "Run cree";
  if (resultType === "dossier_snapshot") return "Dossier analyse";
  if (resultType === "listing_collection") return "Annonces chargees";
  if (resultType === "market_watch") return "Veille creee";
  return response.summary;
}

function formatParameters(parameters: Record<string, unknown>): string {
  const entries = Object.entries(parameters).filter(([, value]) => value !== null && value !== undefined);
  if (entries.length === 0) return "";
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" / ");
}

function formatCommandError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Commande impossible.";
}
