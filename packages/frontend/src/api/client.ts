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

async function fetchJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
    },
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
