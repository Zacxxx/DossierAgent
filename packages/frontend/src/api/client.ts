import { z } from "zod";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const AUTH_STORAGE_KEY = "dossieragent.auth.session";

const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.unknown()),
    trace_id: z.string(),
    retryable: z.boolean(),
  }),
});

const dashboardListingSchema = z.object({
  id: z.string(),
  title: z.string(),
  city: z.string(),
  district: z.string().nullable(),
  price: z.number().nullable(),
  currency: z.string(),
  surface: z.number().nullable(),
  rooms: z.number().nullable(),
  status: z.string(),
  fit_score: z.number().nullable(),
  fit_level: z.string().nullable(),
  risk_flags: z.array(z.string()),
  explanation: z.array(z.string()),
  source_url: z.string().nullable(),
  canonical_url: z.string().nullable(),
  image_urls: z.array(z.string()),
});

export const listingStatusValues = [
  "new",
  "saved",
  "recommended",
  "rejected",
  "duplicate",
  "repost",
  "trash",
  "archived",
] as const;

const listingStatusSchema = z.enum(listingStatusValues);

const listingSummarySchema = z.object({
  id: z.string(),
  watch_id: z.string().nullable(),
  title: z.string(),
  city: z.string().nullable(),
  district: z.string().nullable(),
  price: z.number().nullable(),
  currency: z.string(),
  surface: z.number().nullable(),
  rooms: z.number().nullable(),
  status: listingStatusSchema,
  fit_score: z.number().nullable(),
  fit_level: z.string().nullable(),
  risk_flags: z.array(z.string()),
  explanation: z.array(z.string()),
  source_url: z.string().nullable(),
  canonical_url: z.string().nullable(),
  image_urls: z.array(z.string()),
  first_seen_at: z.string().nullable(),
  last_seen_at: z.string().nullable(),
});

const listingDetailSchema = listingSummarySchema.extend({
  source: z.string(),
  source_url: z.string(),
  canonical_url: z.string(),
  source_listing_id: z.string().nullable(),
  description: z.string().nullable(),
  postal_code: z.string().nullable(),
  agency_name: z.string().nullable(),
  contact_hint: z.string().nullable(),
  duplicate_of_listing_id: z.string().nullable(),
  raw_payload: z.record(z.unknown()),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
});

const listingListSchema = z.object({
  items: z.array(listingSummarySchema),
  next_cursor: z.string().nullable(),
  total: z.number(),
  source: z.string(),
  filters: z.record(z.unknown()),
});

const marketWatchSchema = z.object({
  id: z.string(),
  criteria_id: z.string(),
  name: z.string(),
  status: z.string(),
  frequency: z.string(),
  next_run_at: z.string().nullable(),
  last_run_at: z.string().nullable(),
  source_config: z.record(z.unknown()),
  created_at: z.string(),
  updated_at: z.string(),
});

const marketWatchListSchema = z.object({
  items: z.array(marketWatchSchema),
});

const runNowResponseSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  summary: z.record(z.unknown()),
  idempotent_replay: z.boolean(),
});

const agentRunSchema = z.object({
  id: z.string(),
  watch_id: z.string(),
  trigger_type: z.string(),
  intent: z.string(),
  status: z.string(),
  current_step: z.string(),
  summary: z.record(z.unknown()),
  error: z.unknown().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  completed_at: z.string().nullable(),
});

const agentEventSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  type: z.string(),
  severity: z.string(),
  message: z.string(),
  payload: z.record(z.unknown()),
  created_at: z.string(),
});

const agentEventListSchema = z.object({
  items: z.array(agentEventSchema),
});

const missingDocumentSchema = z.object({
  type: z.string(),
  severity: z.string(),
  reason: z.string(),
});

const dossierReadinessSchema = z.object({
  id: z.string(),
  snapshot_id: z.string(),
  readiness_score: z.number(),
  can_contact: z.boolean(),
  can_send_full_dossier: z.boolean(),
  missing_documents: z.array(z.union([missingDocumentSchema, z.string()])),
  missing_docs: z.array(z.string()),
  valid_documents: z.array(z.string()),
  valid_docs: z.array(z.string()),
  warnings: z.array(z.string()),
  recommendations: z.array(z.string()),
  created_at: z.string(),
});

const dossierDocumentSchema = z.object({
  id: z.string(),
  document_id: z.string(),
  status: z.string(),
  filename: z.string(),
  mime_type: z.string(),
  file_size: z.number(),
  sha256: z.string(),
  declared_type: z.string().nullable(),
  detected_type: z.string().nullable(),
  detected_owner_type: z.string().nullable(),
  page_count: z.number().nullable(),
  has_extracted_text: z.boolean(),
  analysis_status: z.string(),
  issues: z.array(z.string()),
  warnings: z.array(z.string()),
  created_at: z.string(),
  updated_at: z.string(),
});

const dossierDocumentListSchema = z.object({
  items: z.array(dossierDocumentSchema),
});

const contactPacketSchema = z.object({
  id: z.string(),
  listing_id: z.string(),
  status: z.string(),
  language: z.string(),
  tone: z.string(),
  message_draft: z.string(),
  questions_to_ask: z.array(z.string()),
  dossier_summary: z.record(z.unknown()),
  user_check_id: z.string().optional(),
  used_at: z.string().nullable(),
  used_channel: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

const contactPacketListSchema = z.object({
  items: z.array(contactPacketSchema),
});

const userCheckSchema = z.object({
  id: z.string(),
  type: z.string(),
  resource_type: z.string(),
  resource_id: z.string(),
  title: z.string(),
  summary: z.string(),
  status: z.string(),
  payload: z.record(z.unknown()),
  completed_with: z.string().nullable(),
  completed_note: z.string().nullable(),
  created_at: z.string(),
  completed_at: z.string().nullable(),
});

const userChecksListSchema = z.object({
  items: z.array(userCheckSchema),
});

const notificationSchema = z.object({
  id: z.string(),
  type: z.string(),
  title: z.string(),
  body: z.string(),
  resource_type: z.string().nullable(),
  resource_id: z.string().nullable(),
  read_at: z.string().nullable(),
  created_at: z.string(),
});

const notificationListSchema = z.object({
  items: z.array(notificationSchema),
});

const authUserSchema = z.object({
  provider: z.string(),
  provider_user_id: z.string(),
  app_user_id: z.string(),
  email: z.string().nullable(),
  display_name: z.string().nullable(),
});

const authSessionSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.string(),
  expires_in: z.number().nullable(),
  expires_at: z.number().nullable(),
  user: authUserSchema,
});

const authRegisterResponseSchema = z.object({
  status: z.string(),
  user: authUserSchema.nullable(),
  session: authSessionSchema.nullable(),
});

const authStatusResponseSchema = z.object({
  status: z.string(),
});

const agentCommandResponseSchema = z.object({
  status: z.enum(["accepted", "rejected"]),
  intent: z.string(),
  action: z.string(),
  summary: z.string(),
  parameters: z.record(z.unknown()),
  guardrails: z.array(z.string()),
  result: z.record(z.unknown()).nullable(),
});

const aiProviderModelSchema = z.object({
  id: z.string(),
  label: z.string(),
  owned_by: z.string().optional().nullable(),
  created_at: z.string().optional().nullable(),
  name: z.string().optional().nullable(),
});

const aiProviderSchema = z.object({
  id: z.string(),
  label: z.string(),
  configured: z.boolean(),
  model_source: z.string(),
  models: z.array(aiProviderModelSchema),
  error: z.string().nullable(),
  details: z.record(z.unknown()),
});

const aiProvidersResponseSchema = z.object({
  providers: z.array(aiProviderSchema),
});

const aiProviderSettingsProviderSchema = z.object({
  id: z.string(),
  stored_fields: z.array(z.string()),
  env_fields: z.array(z.string()),
  status: aiProviderSchema,
});

const aiProviderSettingsResponseSchema = z.object({
  providers: z.array(aiProviderSettingsProviderSchema),
});

const aiChatMessageSchema = z.object({
  role: z.string(),
  content: z.string(),
});

const aiToolCallSchema = z.object({
  status: z.string(),
  intent: z.string(),
  action: z.string(),
  summary: z.string(),
  parameters: z.record(z.unknown()),
  guardrails: z.array(z.string()),
  result: z.record(z.unknown()).nullable(),
});

const aiChatResponseSchema = z.object({
  id: z.string(),
  provider: z.string(),
  model: z.string(),
  message: aiChatMessageSchema,
  tool_call: aiToolCallSchema.nullable(),
  usage: z.record(z.unknown()).nullable(),
});

export const dashboardSchema = z.object({
  current_watch: z.object({
    id: z.string(),
    name: z.string(),
    status: z.string(),
    next_run_at: z.string().nullable(),
    last_run_at: z.string().nullable(),
  }),
  latest_run: z.object({
    id: z.string(),
    status: z.string(),
    stats: z.record(z.unknown()),
    completed_at: z.string().nullable(),
  }),
  dossier: z.object({
    readiness_score: z.number(),
    can_contact: z.boolean(),
    can_send_full_dossier: z.boolean(),
    missing_docs: z.array(z.string()),
    valid_docs: z.array(z.string()),
    recommendations: z.array(z.string()),
  }),
  pending_checks: z.number(),
  notifications_unread: z.number(),
  recommended_listings: z.array(dashboardListingSchema),
});

export type Dashboard = z.infer<typeof dashboardSchema>;
export type DashboardListing = z.infer<typeof dashboardListingSchema>;
export type ListingStatus = z.infer<typeof listingStatusSchema>;
export type ListingSummary = z.infer<typeof listingSummarySchema>;
export type ListingDetail = z.infer<typeof listingDetailSchema>;
export type ListingList = z.infer<typeof listingListSchema>;
export type MarketWatch = z.infer<typeof marketWatchSchema>;
export type RunNowResponse = z.infer<typeof runNowResponseSchema>;
export type AgentRun = z.infer<typeof agentRunSchema>;
export type AgentEvent = z.infer<typeof agentEventSchema>;
export type DossierReadiness = z.infer<typeof dossierReadinessSchema>;
export type DossierDocument = z.infer<typeof dossierDocumentSchema>;
export type MissingDocument = z.infer<typeof missingDocumentSchema>;
export type ContactPacket = z.infer<typeof contactPacketSchema>;
export type UserCheck = z.infer<typeof userCheckSchema>;
export type Notification = z.infer<typeof notificationSchema>;
export type AuthUser = z.infer<typeof authUserSchema>;
export type AuthSession = z.infer<typeof authSessionSchema>;
export type AuthRegisterResponse = z.infer<typeof authRegisterResponseSchema>;
export type AgentCommandResponse = z.infer<typeof agentCommandResponseSchema>;
export type AiProvider = z.infer<typeof aiProviderSchema>;
export type AiProviderModel = z.infer<typeof aiProviderModelSchema>;
export type AiProviderSettingsProvider = z.infer<typeof aiProviderSettingsProviderSchema>;
export type AiChatResponse = z.infer<typeof aiChatResponseSchema>;

export type ListingFilters = {
  q?: string;
  status?: ListingStatus;
  city?: string;
  district?: string;
  watch_id?: string;
  max_price?: number;
  min_price?: number;
  min_surface?: number;
  min_score?: number;
  limit?: number;
  cursor?: string;
};

export class ApiError extends Error {
  code: string;
  traceId: string;
  retryable: boolean;

  constructor(payload: z.infer<typeof errorEnvelopeSchema>) {
    super(payload.error.message);
    this.name = "ApiError";
    this.code = payload.error.code;
    this.traceId = payload.error.trace_id;
    this.retryable = payload.error.retryable;
  }
}

export function getStoredAuthSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const rawSession = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!rawSession) return null;
  try {
    const parsedSession = authSessionSchema.safeParse(JSON.parse(rawSession));
    if (parsedSession.success) return parsedSession.data;
  } catch {
    // Invalid local storage should not break the app shell.
  }
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  return null;
}

export function storeAuthSession(session: AuthSession): void {
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event("dossieragent-auth-changed"));
}

export function clearAuthSession(): void {
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  window.dispatchEvent(new Event("dossieragent-auth-changed"));
}

export async function loginWithPassword({
  email,
  password,
}: {
  email: string;
  password: string;
}): Promise<AuthSession> {
  const session = await fetchJson("/auth/login", authSessionSchema, {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipAuth: true,
  });
  storeAuthSession(session);
  return session;
}

export async function registerWithPassword({
  email,
  password,
  displayName,
  redirectTo,
}: {
  email: string;
  password: string;
  displayName?: string;
  redirectTo?: string;
}): Promise<AuthRegisterResponse> {
  const result = await fetchJson("/auth/register", authRegisterResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      display_name: displayName,
      redirect_to: redirectTo,
    }),
    skipAuth: true,
  });
  if (result.session) storeAuthSession(result.session);
  return result;
}

export async function refreshAuthSession(refreshToken?: string): Promise<AuthSession> {
  const token = refreshToken ?? getStoredAuthSession()?.refresh_token;
  if (!token) throw new Error("Missing refresh token.");
  const session = await fetchJson("/auth/refresh", authSessionSchema, {
    method: "POST",
    body: JSON.stringify({ refresh_token: token }),
    skipAuth: true,
  });
  storeAuthSession(session);
  return session;
}

export async function requestPasswordReset({
  email,
  redirectTo,
}: {
  email: string;
  redirectTo?: string;
}): Promise<{ status: string }> {
  return fetchJson("/auth/password/forgot", authStatusResponseSchema, {
    method: "POST",
    body: JSON.stringify({ email, redirect_to: redirectTo }),
    skipAuth: true,
  });
}

export async function logoutSession(): Promise<{ status: string }> {
  try {
    return await fetchJson("/auth/logout", authStatusResponseSchema, {
      method: "POST",
    });
  } finally {
    clearAuthSession();
  }
}

export async function getMe(): Promise<AuthUser> {
  return fetchJson("/me", authUserSchema);
}

export async function getDashboard(): Promise<Dashboard> {
  return fetchJson("/dashboard", dashboardSchema);
}

export async function runAgentCommand({
  command,
  context = {},
  execute = true,
}: {
  command: string;
  context?: Record<string, unknown>;
  execute?: boolean;
}): Promise<AgentCommandResponse> {
  return fetchJson("/agent/commands", agentCommandResponseSchema, {
    method: "POST",
    body: JSON.stringify({ command, context, execute }),
  });
}

export async function getAiProviders(): Promise<{ providers: AiProvider[] }> {
  return fetchJson("/ai/providers", aiProvidersResponseSchema);
}

export async function getAiProviderSettings(): Promise<{ providers: AiProviderSettingsProvider[] }> {
  return fetchJson("/ai/provider-settings", aiProviderSettingsResponseSchema);
}

export async function updateAiProviderSettings({
  providerId,
  apiKey,
  providerPath,
  providerMode,
  clearFields = [],
}: {
  providerId: string;
  apiKey?: string;
  providerPath?: string;
  providerMode?: string;
  clearFields?: string[];
}): Promise<{ providers: AiProviderSettingsProvider[] }> {
  return fetchJson(`/ai/provider-settings/${encodeURIComponent(providerId)}`, aiProviderSettingsResponseSchema, {
    method: "PATCH",
    body: JSON.stringify({
      api_key: apiKey,
      provider_path: providerPath,
      provider_mode: providerMode,
      clear_fields: clearFields,
    }),
  });
}

export async function runAiChat({
  provider,
  model,
  messages,
  context = {},
  useTools = true,
}: {
  provider: string;
  model: string;
  messages: Array<{ role: string; content: string }>;
  context?: Record<string, unknown>;
  useTools?: boolean;
}): Promise<AiChatResponse> {
  return fetchJson("/ai/chat", aiChatResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      provider,
      model,
      messages,
      context,
      use_tools: useTools,
    }),
  });
}

export async function getListings(filters: ListingFilters = {}): Promise<ListingList> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  const queryString = params.toString();
  return fetchJson(`/listings${queryString ? `?${queryString}` : ""}`, listingListSchema);
}

export async function getListing(listingId: string): Promise<ListingDetail> {
  return fetchJson(`/listings/${encodeURIComponent(listingId)}`, listingDetailSchema);
}

export async function getMarketWatches(): Promise<{ items: MarketWatch[] }> {
  return fetchJson("/market-watches", marketWatchListSchema);
}

export async function patchMarketWatch({
  watchId,
  name,
  status,
  frequency,
  nextRunAt,
  sourceConfig,
}: {
  watchId: string;
  name?: string;
  status?: string;
  frequency?: string;
  nextRunAt?: string | null;
  sourceConfig?: Record<string, unknown>;
}): Promise<MarketWatch> {
  return fetchJson(`/market-watches/${encodeURIComponent(watchId)}`, marketWatchSchema, {
    method: "PATCH",
    body: JSON.stringify({
      name,
      status,
      frequency,
      next_run_at: nextRunAt,
      source_config: sourceConfig,
    }),
  });
}

export async function runMarketWatchNow({
  watchId,
  idempotencyKey,
}: {
  watchId: string;
  idempotencyKey: string;
}): Promise<RunNowResponse> {
  return fetchJson(`/market-watches/${encodeURIComponent(watchId)}/run-now`, runNowResponseSchema, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
    },
  });
}

export async function getAgentRun(runId: string): Promise<AgentRun> {
  return fetchJson(`/agent-runs/${encodeURIComponent(runId)}`, agentRunSchema);
}

export async function getAgentRunEvents(runId: string): Promise<{ items: AgentEvent[] }> {
  return fetchJson(`/agent-runs/${encodeURIComponent(runId)}/events`, agentEventListSchema);
}

export async function patchListingStatus(
  listingId: string,
  status: ListingStatus,
): Promise<ListingDetail> {
  return fetchJson(`/listings/${encodeURIComponent(listingId)}`, listingDetailSchema, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function getDossierReadiness(): Promise<DossierReadiness> {
  return fetchJson("/dossier/readiness", dossierReadinessSchema);
}

export async function analyzeDossier(): Promise<DossierReadiness> {
  return fetchJson("/dossier/analyze", dossierReadinessSchema, {
    method: "POST",
  });
}

export async function getDossierDocuments(): Promise<{ items: DossierDocument[] }> {
  return fetchJson("/dossier/documents", dossierDocumentListSchema);
}

export async function getDossierDocumentPreview(documentId: string): Promise<Blob> {
  return fetchBlob(`/dossier/documents/${encodeURIComponent(documentId)}/preview`, {
    headers: {
      Accept: "application/pdf,application/octet-stream",
    },
  });
}

export async function deleteDossierDocument(documentId: string): Promise<DossierDocument> {
  return fetchJson(`/dossier/documents/${encodeURIComponent(documentId)}`, dossierDocumentSchema, {
    method: "DELETE",
  });
}

export async function uploadDossierDocument({
  file,
  declaredType,
  ownerType,
}: {
  file: File;
  declaredType: string;
  ownerType: string;
}): Promise<DossierDocument> {
  const formData = new FormData();
  formData.set("file", file);
  formData.set("declared_type", declaredType);
  formData.set("owner_type", ownerType);
  return fetchJson("/dossier/documents", dossierDocumentSchema, {
    method: "POST",
    body: formData,
  });
}

export async function createContactPacket({
  listingId,
  language = "fr",
  tone = "polite_direct",
  includeDossierSummary = true,
}: {
  listingId: string;
  language?: string;
  tone?: string;
  includeDossierSummary?: boolean;
}): Promise<ContactPacket> {
  return fetchJson("/contact-packets", contactPacketSchema, {
    method: "POST",
    body: JSON.stringify({
      listing_id: listingId,
      language,
      tone,
      include_dossier_summary: includeDossierSummary,
    }),
  });
}

export async function getContactPackets(): Promise<{ items: ContactPacket[] }> {
  return fetchJson("/contact-packets", contactPacketListSchema);
}

export async function getContactPacket(packetId: string): Promise<ContactPacket> {
  return fetchJson(`/contact-packets/${encodeURIComponent(packetId)}`, contactPacketSchema);
}

export async function patchContactPacket({
  packetId,
  language,
  tone,
  status,
  messageDraft,
  questionsToAsk,
  dossierSummary,
}: {
  packetId: string;
  language?: string;
  tone?: string;
  status?: string;
  messageDraft?: string;
  questionsToAsk?: string[];
  dossierSummary?: Record<string, unknown>;
}): Promise<ContactPacket> {
  return fetchJson(`/contact-packets/${encodeURIComponent(packetId)}`, contactPacketSchema, {
    method: "PATCH",
    body: JSON.stringify({
      language,
      tone,
      status,
      message_draft: messageDraft,
      questions_to_ask: questionsToAsk,
      dossier_summary: dossierSummary,
    }),
  });
}

export async function markContactPacketUsed({
  packetId,
  channel = "manual_copy",
}: {
  packetId: string;
  channel?: string;
}): Promise<ContactPacket> {
  return fetchJson(`/contact-packets/${encodeURIComponent(packetId)}/mark-used`, contactPacketSchema, {
    method: "POST",
    body: JSON.stringify({ channel }),
  });
}

export async function getUserChecks(): Promise<{ items: UserCheck[] }> {
  return fetchJson("/user-checks", userChecksListSchema);
}

export async function getNotifications({
  unreadOnly = false,
  limit = 100,
}: {
  unreadOnly?: boolean;
  limit?: number;
} = {}): Promise<{ items: Notification[] }> {
  const params = new URLSearchParams();
  if (unreadOnly) params.set("unread_only", "true");
  params.set("limit", String(limit));
  return fetchJson(`/notifications?${params.toString()}`, notificationListSchema);
}

export async function markNotificationRead(notificationId: string): Promise<Notification> {
  return fetchJson(`/notifications/${encodeURIComponent(notificationId)}/read`, notificationSchema, {
    method: "POST",
  });
}

export async function completeUserCheck({
  checkId,
  decision,
  note,
}: {
  checkId: string;
  decision: "approved" | "rejected";
  note?: string;
}): Promise<UserCheck> {
  return fetchJson(`/user-checks/${encodeURIComponent(checkId)}/complete`, userCheckSchema, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
}

type FetchJsonInit = RequestInit & {
  skipAuth?: boolean;
};

async function fetchJson<T>(
  path: string,
  schema: z.ZodType<T>,
  init: FetchJsonInit = {},
): Promise<T> {
  const { skipAuth = false, ...requestInit } = init;
  const headers = new Headers(requestInit.headers);
  headers.set("Accept", "application/json");
  if (
    requestInit.body !== undefined &&
    !(requestInit.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }
  if (!skipAuth && !headers.has("Authorization")) {
    const session = getStoredAuthSession();
    if (session) headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...requestInit,
    headers,
  });
  const payload: unknown = await response.json();

  if (!response.ok) {
    const parsedError = errorEnvelopeSchema.safeParse(payload);
    if (parsedError.success) {
      throw new ApiError(parsedError.data);
    }
    throw new Error(`API request failed with status ${response.status}`);
  }

  return schema.parse(payload);
}

async function fetchBlob(path: string, init: FetchJsonInit = {}): Promise<Blob> {
  const { skipAuth = false, ...requestInit } = init;
  const headers = new Headers(requestInit.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/octet-stream");
  if (!skipAuth && !headers.has("Authorization")) {
    const session = getStoredAuthSession();
    if (session) headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...requestInit,
    headers,
  });

  if (!response.ok) {
    const payload: unknown = await response.json();
    const parsedError = errorEnvelopeSchema.safeParse(payload);
    if (parsedError.success) {
      throw new ApiError(parsedError.data);
    }
    throw new Error(`API request failed with status ${response.status}`);
  }

  return response.blob();
}
