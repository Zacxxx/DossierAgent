import { z } from "zod";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

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
    stats: z.record(z.union([z.string(), z.number(), z.boolean(), z.null()])),
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
export type DossierReadiness = z.infer<typeof dossierReadinessSchema>;
export type DossierDocument = z.infer<typeof dossierDocumentSchema>;
export type MissingDocument = z.infer<typeof missingDocumentSchema>;
export type ContactPacket = z.infer<typeof contactPacketSchema>;
export type UserCheck = z.infer<typeof userCheckSchema>;

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

export async function getDashboard(): Promise<Dashboard> {
  return fetchJson("/dashboard", dashboardSchema);
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

export async function getUserChecks(): Promise<{ items: UserCheck[] }> {
  return fetchJson("/user-checks", userChecksListSchema);
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

async function fetchJson<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
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
