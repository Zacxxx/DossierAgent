import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, RefreshCcw, Save, Trash2 } from "lucide-react";

import {
  ApiError,
  getAiProviderSettings,
  updateAiProviderSettings,
  type AiProviderSettingsProvider,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

type ProviderForm = {
  apiKey: string;
  providerPath: string;
  providerMode: string;
};

const providerLabels: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
  codex: "Codex",
};

export function SettingsRoute() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["ai-provider-settings"],
    queryFn: getAiProviderSettings,
  });
  const providers = settingsQuery.data?.providers ?? [];
  const [selectedProviderId, setSelectedProviderId] = useState("openai");
  const [forms, setForms] = useState<Record<string, ProviderForm>>({});

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.id === selectedProviderId) ?? providers[0],
    [providers, selectedProviderId],
  );
  const selectedForm = forms[selectedProvider?.id ?? "openai"] ?? emptyForm();

  useEffect(() => {
    if (!selectedProviderId && providers[0]) setSelectedProviderId(providers[0].id);
  }, [providers, selectedProviderId]);

  const saveMutation = useMutation({
    mutationFn: ({
      provider,
      form,
      clearFields,
    }: {
      provider: AiProviderSettingsProvider;
      form: ProviderForm;
      clearFields?: string[];
    }) =>
      updateAiProviderSettings({
        providerId: provider.id,
        apiKey: form.apiKey,
        providerPath: form.providerPath,
        providerMode: form.providerMode,
        clearFields,
      }),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(["ai-provider-settings"], data);
      void queryClient.invalidateQueries({ queryKey: ["ai-providers"] });
      setForms((current) => ({
        ...current,
        [variables.provider.id]: emptyForm(),
      }));
    },
  });

  function updateSelectedForm(patch: Partial<ProviderForm>) {
    if (!selectedProvider) return;
    setForms((current) => ({
      ...current,
      [selectedProvider.id]: {
        ...emptyForm(),
        ...current[selectedProvider.id],
        ...patch,
      },
    }));
  }

  function saveSelectedProvider(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProvider) return;
    saveMutation.mutate({ provider: selectedProvider, form: selectedForm });
  }

  function clearSelectedProvider(field: string) {
    if (!selectedProvider) return;
    saveMutation.mutate({
      provider: selectedProvider,
      form: emptyForm(),
      clearFields: [field],
    });
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <section className="grid min-w-0 gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Settings</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>AI providers</span>
              <Badge variant="outline">server-side secrets</Badge>
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => settingsQuery.refetch()}
            disabled={settingsQuery.isFetching}
          >
            {settingsQuery.isFetching ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCcw className="size-4" />
            )}
            Refresh
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Provider Secrets</CardTitle>
            <KeyRound className="size-4 text-primary" />
          </CardHeader>
          <CardContent>
            {settingsQuery.isPending ? (
              <div className="grid gap-3">
                <Skeleton className="h-10" />
                <Skeleton className="h-36" />
              </div>
            ) : settingsQuery.isError ? (
              <RouteError error={settingsQuery.error} />
            ) : selectedProvider ? (
              <form className="grid gap-4" onSubmit={saveSelectedProvider}>
                <div className="grid gap-2 md:grid-cols-[220px_1fr]">
                  <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
                    Provider
                    <Select
                      value={selectedProvider.id}
                      onChange={(event) => setSelectedProviderId(event.target.value)}
                    >
                      {providers.map((provider) => (
                        <option key={provider.id} value={provider.id}>
                          {providerLabels[provider.id] ?? provider.id}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <ProviderStatus provider={selectedProvider} />
                </div>

                {selectedProvider.id === "codex" ? (
                  <div className="grid gap-3">
                    <SecretField
                      label="Codex path"
                      value={selectedForm.providerPath}
                      placeholder={configuredLabel(selectedProvider, "provider_path")}
                      onChange={(value) => updateSelectedForm({ providerPath: value })}
                      onClear={() => clearSelectedProvider("provider_path")}
                      canClear={selectedProvider.stored_fields.includes("provider_path")}
                    />
                    <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
                      Mode
                      <Select
                        value={selectedForm.providerMode}
                        onChange={(event) => updateSelectedForm({ providerMode: event.target.value })}
                      >
                        <option value="">Keep current</option>
                        <option value="codex_cli">Codex CLI</option>
                        <option value="json_stdio">JSON stdio</option>
                      </Select>
                    </label>
                  </div>
                ) : (
                  <SecretField
                    label="API key"
                    value={selectedForm.apiKey}
                    placeholder={configuredLabel(selectedProvider, "api_key")}
                    onChange={(value) => updateSelectedForm({ apiKey: value })}
                    onClear={() => clearSelectedProvider("api_key")}
                    canClear={selectedProvider.stored_fields.includes("api_key")}
                  />
                )}

                <div className="flex flex-wrap items-center gap-2 border-t pt-4">
                  <Button
                    type="submit"
                    disabled={saveMutation.isPending || !hasPendingInput(selectedProvider, selectedForm)}
                  >
                    {saveMutation.isPending ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Save className="size-4" />
                    )}
                    Save
                  </Button>
                  {saveMutation.isError ? <RouteError error={saveMutation.error} /> : null}
                </div>
              </form>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <aside className="grid content-start gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Providers</CardTitle>
            <Badge variant="outline">{providers.length}</Badge>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            {providers.map((provider) => (
              <button
                key={provider.id}
                type="button"
                className="grid gap-1 rounded-md border bg-background p-3 text-left hover:bg-muted"
                onClick={() => setSelectedProviderId(provider.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{providerLabels[provider.id] ?? provider.id}</span>
                  <Badge variant={provider.status.configured ? "success" : "warning"}>
                    {provider.status.configured ? "configured" : "missing"}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">
                  {provider.status.models.length} models
                </div>
              </button>
            ))}
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function SecretField({
  label,
  value,
  placeholder,
  onChange,
  onClear,
  canClear,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onClear: () => void;
  canClear: boolean;
}) {
  return (
    <label className="grid gap-1 text-xs font-medium uppercase text-muted-foreground">
      {label}
      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <Input
          type="password"
          autoComplete="off"
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
        <Button type="button" variant="outline" disabled={!canClear} onClick={onClear}>
          <Trash2 className="size-4" />
          Clear
        </Button>
      </div>
    </label>
  );
}

function ProviderStatus({ provider }: { provider: AiProviderSettingsProvider }) {
  return (
    <div className="grid gap-2 rounded-md border bg-background p-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge variant={provider.status.configured ? "success" : "warning"}>
          {provider.status.configured ? "Configured" : "Missing"}
        </Badge>
        {provider.stored_fields.map((field) => (
          <Badge key={field} variant="secondary">
            stored:{field}
          </Badge>
        ))}
        {provider.env_fields.map((field) => (
          <Badge key={field} variant="outline">
            env:{field}
          </Badge>
        ))}
      </div>
      <div className="text-xs text-muted-foreground">
        {provider.status.models.length} models from {provider.status.model_source}
      </div>
      {provider.status.error ? (
        <div className="text-xs text-amber-700">{provider.status.error}</div>
      ) : null}
    </div>
  );
}

function configuredLabel(provider: AiProviderSettingsProvider, field: string) {
  if (provider.env_fields.includes(field)) return "Configured from environment";
  if (provider.stored_fields.includes(field)) return "Stored secret configured";
  return "Not configured";
}

function hasPendingInput(provider: AiProviderSettingsProvider, form: ProviderForm) {
  if (provider.id === "codex") {
    return Boolean(form.providerPath.trim() || form.providerMode.trim());
  }
  return Boolean(form.apiKey.trim());
}

function emptyForm(): ProviderForm {
  return { apiKey: "", providerPath: "", providerMode: "" };
}

function RouteError({ error }: { error: Error }) {
  const message = error instanceof ApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      {message}
    </div>
  );
}
