import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, Loader2, RefreshCcw, Send, ShieldCheck, User } from "lucide-react";

import {
  ApiError,
  getAiProviders,
  runAiChat,
  type AiChatResponse,
  type AiProvider,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  response?: AiChatResponse;
};

export function AiChatRoute() {
  const providersQuery = useQuery({
    queryKey: ["ai-providers"],
    queryFn: getAiProviders,
    refetchOnWindowFocus: false,
  });
  const providers = providersQuery.data?.providers ?? [];
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [selectedModelId, setSelectedModelId] = useState("");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.id === selectedProviderId) ?? providers[0],
    [providers, selectedProviderId],
  );
  const modelOptions = selectedProvider?.models ?? [];

  useEffect(() => {
    if (!selectedProviderId && providers[0]) {
      setSelectedProviderId(providers[0].id);
    }
  }, [providers, selectedProviderId]);

  useEffect(() => {
    if (!selectedProvider) return;
    const firstModel = selectedProvider.models[0]?.id ?? "tool-router";
    if (!selectedModelId || !selectedProvider.models.some((model) => model.id === selectedModelId)) {
      setSelectedModelId(firstModel);
    }
  }, [selectedModelId, selectedProvider]);

  const chatMutation = useMutation({
    mutationFn: async (content: string) => {
      const outboundMessages = [...messages, { role: "user" as const, content }];
      return runAiChat({
        provider: selectedProvider?.id ?? "openai",
        model: selectedModelId || "tool-router",
        messages: outboundMessages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
        useTools: true,
      });
    },
    onSuccess: (response, content) => {
      setMessages((current) => [
        ...current,
        { role: "user", content },
        {
          role: "assistant",
          content: response.message.content,
          response,
        },
      ]);
      setDraft("");
    },
  });

  function submitChat(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || chatMutation.isPending) return;
    chatMutation.mutate(content);
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <section className="grid min-w-0 gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">AI Chat</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>Runtime provider registry</span>
              <Badge variant="outline">supervised tools</Badge>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => providersQuery.refetch()}
          >
            <RefreshCcw className="size-4" />
            Refresh
          </Button>
        </div>

        <Card className="min-h-[560px]">
          <CardHeader>
            <CardTitle>Conversation</CardTitle>
            <Badge variant={selectedProvider?.configured ? "success" : "warning"}>
              {selectedProvider?.label ?? "Provider"}
            </Badge>
          </CardHeader>
          <CardContent className="grid min-h-[500px] grid-rows-[1fr_auto] gap-4">
            <div className="grid content-start gap-3 overflow-y-auto rounded-md border bg-background p-3">
              {messages.length === 0 ? (
                <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
                  No messages.
                </div>
              ) : (
                messages.map((message, index) => (
                  <ChatBubble key={`${message.role}-${index}`} message={message} />
                ))
              )}
              {chatMutation.isPending ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  Running
                </div>
              ) : null}
            </div>

            <form className="grid gap-3" onSubmit={submitChat}>
              <div className="grid gap-2 md:grid-cols-[180px_1fr]">
                <Select
                  value={selectedProvider?.id ?? ""}
                  onChange={(event) => {
                    setSelectedProviderId(event.target.value);
                    setSelectedModelId("");
                  }}
                  disabled={providersQuery.isPending}
                >
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.label}
                    </option>
                  ))}
                </Select>
                <Select
                  value={selectedModelId}
                  onChange={(event) => setSelectedModelId(event.target.value)}
                >
                  {modelOptions.length > 0 ? (
                    modelOptions.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.label}
                      </option>
                    ))
                  ) : (
                    <option value="tool-router">Tool router</option>
                  )}
                </Select>
              </div>
              <div className="grid gap-2 md:grid-cols-[1fr_auto]">
                <Input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Message"
                  disabled={chatMutation.isPending}
                />
                <Button type="submit" disabled={!draft.trim() || chatMutation.isPending}>
                  {chatMutation.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Send className="size-4" />
                  )}
                  Send
                </Button>
              </div>
              {chatMutation.error ? <RouteError error={chatMutation.error} /> : null}
            </form>
          </CardContent>
        </Card>
      </section>

      <aside className="grid content-start gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Providers</CardTitle>
            {providersQuery.isFetching ? <Loader2 className="size-4 animate-spin" /> : null}
          </CardHeader>
          <CardContent className="grid gap-2 text-sm">
            {providersQuery.isError ? (
              <RouteError error={providersQuery.error} />
            ) : (
              providers.map((provider) => <ProviderRow key={provider.id} provider={provider} />)
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Guardrails</CardTitle>
            <ShieldCheck className="size-4 text-primary" />
          </CardHeader>
          <CardContent className="grid gap-2 text-sm text-muted-foreground">
            <div>Tool route: supervised</div>
            <div>External contact: blocked</div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isAssistant = message.role === "assistant";
  const Icon = isAssistant ? Bot : User;
  return (
    <div className="grid gap-2 rounded-md border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Icon className="size-4" />
          {isAssistant ? "Assistant" : "User"}
        </div>
        {message.response?.tool_call ? (
          <Badge variant={message.response.tool_call.status === "accepted" ? "success" : "warning"}>
            {message.response.tool_call.intent}
          </Badge>
        ) : null}
      </div>
      <div className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{message.content}</div>
    </div>
  );
}

function ProviderRow({ provider }: { provider: AiProvider }) {
  return (
    <div className="grid gap-1 rounded-md border bg-background p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{provider.label}</span>
        <Badge variant={provider.configured ? "success" : "warning"}>
          {provider.configured ? "configured" : "missing"}
        </Badge>
      </div>
      <div className="text-xs text-muted-foreground">
        {provider.models.length} models from {provider.model_source}
      </div>
      {provider.error ? (
        <div className="text-xs text-amber-700">{provider.error}</div>
      ) : null}
    </div>
  );
}

function RouteError({ error }: { error: Error }) {
  const message = error instanceof ApiError ? `${error.code}: ${error.message}` : error.message;
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
      {message}
    </div>
  );
}
