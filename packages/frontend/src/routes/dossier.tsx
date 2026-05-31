import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCcw,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";

import {
  ApiError,
  analyzeDossier,
  deleteDossierDocument,
  getDossierDocumentPreview,
  getDossierDocuments,
  getDossierReadiness,
  uploadDossierDocument,
  type DossierDocument,
  type DossierReadiness,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

const documentTypes = [
  { value: "payslip", label: "Fiche de paie" },
  { value: "identity", label: "Identite" },
  { value: "employment_contract", label: "Contrat" },
  { value: "tax_notice", label: "Avis impot" },
  { value: "proof_of_address", label: "Domicile" },
] as const;

const ownerTypes = [
  { value: "user", label: "Locataire" },
  { value: "guarantor", label: "Garant" },
  { value: "co_tenant", label: "Colocataire" },
] as const;

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "medium",
  timeStyle: "short",
});

const fileSizeFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 1,
});

type PreviewState = {
  documentId: string;
  url: string;
  filename: string;
};

export function DossierRoute() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [declaredType, setDeclaredType] = useState<(typeof documentTypes)[number]["value"]>("payslip");
  const [ownerType, setOwnerType] = useState<(typeof ownerTypes)[number]["value"]>("user");
  const [dragActive, setDragActive] = useState(false);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | undefined>(undefined);
  const [preview, setPreview] = useState<PreviewState | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["dossier-documents"],
    queryFn: getDossierDocuments,
  });
  const readinessQuery = useQuery({
    queryKey: ["dossier-readiness"],
    queryFn: getDossierReadiness,
  });
  const documents = documentsQuery.data?.items ?? [];

  const uploadMutation = useMutation({
    mutationFn: uploadDossierDocument,
    onSuccess: (document) => {
      setSelectedDocumentId(document.document_id);
      void queryClient.invalidateQueries({ queryKey: ["dossier-documents"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const previewMutation = useMutation({
    mutationFn: getDossierDocumentPreview,
    onSuccess: (blob, documentId) => {
      const url = URL.createObjectURL(blob);
      const matchedDocument = documents.find((document) => document.document_id === documentId);
      setPreview({
        documentId,
        url,
        filename: matchedDocument?.filename ?? "document.pdf",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDossierDocument,
    onSuccess: (document) => {
      if (preview?.documentId === document.document_id) setPreview(null);
      if (selectedDocumentId === document.document_id) setSelectedDocumentId(undefined);
      void queryClient.invalidateQueries({ queryKey: ["dossier-documents"] });
      void queryClient.invalidateQueries({ queryKey: ["dossier-readiness"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: analyzeDossier,
    onSuccess: (readiness) => {
      queryClient.setQueryData(["dossier-readiness"], readiness);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const selectedDocument = useMemo(
    () => documents.find((document) => document.document_id === selectedDocumentId) ?? documents[0],
    [documents, selectedDocumentId],
  );

  useEffect(() => {
    return () => {
      if (preview?.url) URL.revokeObjectURL(preview.url);
    };
  }, [preview?.url]);

  useEffect(() => {
    if (selectedDocumentId && !documents.some((document) => document.document_id === selectedDocumentId)) {
      setSelectedDocumentId(undefined);
    }
  }, [documents, selectedDocumentId]);

  function handleFile(file: File | undefined) {
    if (!file) return;
    uploadMutation.mutate({ file, declaredType, ownerType });
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function refreshAll() {
    void documentsQuery.refetch();
    void readinessQuery.refetch();
  }

  const loading = documentsQuery.isPending || readinessQuery.isPending;
  const error = documentsQuery.error ?? readinessQuery.error;

  if (loading) {
    return <DossierSkeleton />;
  }

  if (error) {
    return <DossierError error={error} onRetry={refreshAll} />;
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="grid min-w-0 gap-4">
        <div className="grid gap-3 2xl:grid-cols-[minmax(0,1fr)_auto] 2xl:items-center">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">Dossier</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{documents.length} pieces</span>
              {readinessQuery.data ? (
                <Badge variant={readinessQuery.data.can_contact ? "success" : "warning"}>
                  {readinessQuery.data.can_contact ? "Contact possible" : "Contact bloque"}
                </Badge>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap gap-2 2xl:justify-end">
            <Button variant="outline" size="sm" type="button" onClick={refreshAll}>
              <RefreshCcw className="size-4" />
              Refresh
            </Button>
            <Button
              size="sm"
              type="button"
              onClick={() => analyzeMutation.mutate()}
              disabled={analyzeMutation.isPending}
            >
              {analyzeMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
              Analyser
            </Button>
          </div>
        </div>

        <UploadPanel
          declaredType={declaredType}
          ownerType={ownerType}
          dragActive={dragActive}
          inputRef={inputRef}
          uploadPending={uploadMutation.isPending}
          uploadError={uploadMutation.error}
          onDeclaredTypeChange={(value) => setDeclaredType(value)}
          onOwnerTypeChange={(value) => setOwnerType(value)}
          onDragActiveChange={setDragActive}
          onFile={handleFile}
        />

        <DocumentList
          documents={documents}
          selectedDocumentId={selectedDocument?.document_id}
          onSelect={setSelectedDocumentId}
          onPreview={(documentId) => previewMutation.mutate(documentId)}
          previewingDocumentId={previewMutation.isPending ? previewMutation.variables : undefined}
        />
      </section>

      <aside className="grid content-start gap-4">
        <ReadinessCard readiness={readinessQuery.data} analyzing={analyzeMutation.isPending} />
        <MissingDocsChecklist readiness={readinessQuery.data} />
        <DocumentPreviewPane
          document={selectedDocument}
          preview={preview?.documentId === selectedDocument?.document_id ? preview : null}
          previewPending={
            previewMutation.isPending && previewMutation.variables === selectedDocument?.document_id
          }
          previewError={previewMutation.error}
          deletePending={
            deleteMutation.isPending && deleteMutation.variables === selectedDocument?.document_id
          }
          deleteError={deleteMutation.error}
          onPreview={() => {
            if (selectedDocument) previewMutation.mutate(selectedDocument.document_id);
          }}
          onOpenPreview={() => {
            if (preview?.documentId === selectedDocument?.document_id) {
              window.open(preview.url, "_blank", "noopener,noreferrer");
            }
          }}
          onDelete={() => {
            if (selectedDocument) deleteMutation.mutate(selectedDocument.document_id);
          }}
        />
      </aside>
    </div>
  );
}

function UploadPanel({
  declaredType,
  ownerType,
  dragActive,
  inputRef,
  uploadPending,
  uploadError,
  onDeclaredTypeChange,
  onOwnerTypeChange,
  onDragActiveChange,
  onFile,
}: {
  declaredType: (typeof documentTypes)[number]["value"];
  ownerType: (typeof ownerTypes)[number]["value"];
  dragActive: boolean;
  inputRef: React.MutableRefObject<HTMLInputElement | null>;
  uploadPending: boolean;
  uploadError: Error | null;
  onDeclaredTypeChange: (value: (typeof documentTypes)[number]["value"]) => void;
  onOwnerTypeChange: (value: (typeof ownerTypes)[number]["value"]) => void;
  onDragActiveChange: (value: boolean) => void;
  onFile: (file: File | undefined) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload</CardTitle>
        <Badge variant="outline">PDF</Badge>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="grid gap-3 md:grid-cols-[1fr_180px_180px]">
          <button
            type="button"
            className={cn(
              "flex min-h-32 items-center justify-center rounded-md border border-dashed bg-background px-4 text-left transition-colors",
              dragActive ? "border-primary bg-muted" : "border-border hover:bg-muted",
            )}
            onClick={() => inputRef.current?.click()}
            onDragEnter={(event) => {
              event.preventDefault();
              onDragActiveChange(true);
            }}
            onDragOver={(event) => {
              event.preventDefault();
              onDragActiveChange(true);
            }}
            onDragLeave={(event) => {
              event.preventDefault();
              onDragActiveChange(false);
            }}
            onDrop={(event) => {
              event.preventDefault();
              onDragActiveChange(false);
              onFile(event.dataTransfer.files[0]);
            }}
            disabled={uploadPending}
          >
            <span className="flex items-center gap-3">
              {uploadPending ? <Loader2 className="size-5 animate-spin text-primary" /> : <Upload className="size-5 text-primary" />}
              <span>
                <span className="block text-sm font-medium">Deposer un PDF</span>
                <span className="block text-xs text-muted-foreground">Extraction locale puis analyse supervisee</span>
              </span>
            </span>
          </button>
          <Field label="Type declare">
            <Select
              value={declaredType}
              onChange={(event) =>
                onDeclaredTypeChange(event.target.value as (typeof documentTypes)[number]["value"])
              }
            >
              {documentTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Titulaire">
            <Select
              value={ownerType}
              onChange={(event) => onOwnerTypeChange(event.target.value as (typeof ownerTypes)[number]["value"])}
            >
              {ownerTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <input
          ref={inputRef}
          className="hidden"
          type="file"
          accept="application/pdf,.pdf"
          onChange={(event) => onFile(event.target.files?.[0])}
        />
        {uploadError ? <ErrorLine error={uploadError} /> : null}
      </CardContent>
    </Card>
  );
}

function DocumentList({
  documents,
  selectedDocumentId,
  onSelect,
  onPreview,
  previewingDocumentId,
}: {
  documents: DossierDocument[];
  selectedDocumentId: string | undefined;
  onSelect: (documentId: string) => void;
  onPreview: (documentId: string) => void;
  previewingDocumentId: string | undefined;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
        <Badge variant="secondary">{documents.length}</Badge>
      </CardHeader>
      <CardContent>
        {documents.length > 0 ? (
          <div className="overflow-x-auto">
            <Table className="min-w-[760px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Fichier</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Pages</TableHead>
                  <TableHead>Taille</TableHead>
                  <TableHead>Ajout</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((document) => (
                  <TableRow
                    key={document.document_id}
                    className={cn(
                      "cursor-pointer",
                      selectedDocumentId === document.document_id && "bg-muted",
                    )}
                    onClick={() => onSelect(document.document_id)}
                  >
                    <TableCell>
                      <div className="grid gap-1">
                        <span className="font-medium">{document.filename}</span>
                        <span className="truncate text-xs text-muted-foreground">{document.sha256.slice(0, 16)}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(document.status)}>{humanizeStatus(document.status)}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="grid gap-1 text-sm">
                        <span>{humanizeDocumentType(document.detected_type)}</span>
                        <span className="text-xs text-muted-foreground">
                          declare: {humanizeDocumentType(document.declared_type)}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>{document.page_count ?? "-"}</TableCell>
                    <TableCell>{formatFileSize(document.file_size)}</TableCell>
                    <TableCell>{formatDate(document.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        type="button"
                        aria-label="Preview"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelect(document.document_id);
                          onPreview(document.document_id);
                        }}
                      >
                        {previewingDocumentId === document.document_id ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <Eye className="size-4" />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
            Aucun document charge.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReadinessCard({
  readiness,
  analyzing,
}: {
  readiness: DossierReadiness | undefined;
  analyzing: boolean;
}) {
  const score = readiness?.readiness_score ?? 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Completeness</CardTitle>
        <ShieldCheck className="size-4 text-primary" />
      </CardHeader>
      <CardContent className="grid gap-4">
        <div>
          <div className="flex items-end justify-between gap-3">
            <div className="text-4xl font-semibold leading-none">{Math.round(score)}%</div>
            {analyzing ? (
              <Badge variant="outline">
                <Loader2 className="mr-1 size-3 animate-spin" />
                Analyse
              </Badge>
            ) : (
              <Badge variant={readiness?.can_send_full_dossier ? "success" : "warning"}>
                {readiness?.can_send_full_dossier ? "Dossier complet" : "Pieces a completer"}
              </Badge>
            )}
          </div>
          <div className="mt-3 h-2 rounded-full bg-muted">
            <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.min(100, Math.max(0, score))}%` }} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Fact label="Pieces valides" value={String(readiness?.valid_docs.length ?? 0)} />
          <Fact label="Pieces manquantes" value={String(readiness?.missing_docs.length ?? 0)} />
          <Fact label="Contact" value={readiness?.can_contact ? "Oui" : "Non"} />
          <Fact label="Envoi dossier" value={readiness?.can_send_full_dossier ? "Oui" : "Non"} />
        </div>
      </CardContent>
    </Card>
  );
}

function MissingDocsChecklist({ readiness }: { readiness: DossierReadiness | undefined }) {
  const missingDocuments = readiness?.missing_documents ?? [];
  const warnings = readiness?.warnings ?? [];
  const recommendations = readiness?.recommendations ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Checklist</CardTitle>
        <AlertTriangle className="size-4 text-amber-700" />
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-2">
          {missingDocuments.length > 0 ? (
            missingDocuments.map((document) => {
              const item =
                typeof document === "string"
                  ? { type: document, severity: "medium", reason: "Piece attendue" }
                  : document;
              return (
                <div key={`${item.type}-${item.reason}`} className="rounded-md border bg-background p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{humanizeDocumentType(item.type)}</span>
                    <Badge variant={item.severity === "high" ? "warning" : "outline"}>{item.severity}</Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{item.reason}</div>
                </div>
              );
            })
          ) : (
            <div className="flex items-center gap-2 rounded-md border bg-background p-3 text-sm">
              <CheckCircle2 className="size-4 text-emerald-700" />
              Aucune piece manquante.
            </div>
          )}
        </div>
        {warnings.length > 0 ? (
          <div className="grid gap-2">
            {warnings.map((warning) => (
              <div key={warning} className="text-xs text-amber-800">
                {warning}
              </div>
            ))}
          </div>
        ) : null}
        {recommendations.length > 0 ? (
          <div className="grid gap-2">
            {recommendations.map((recommendation) => (
              <div key={recommendation} className="text-xs text-muted-foreground">
                {recommendation}
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function DocumentPreviewPane({
  document,
  preview,
  previewPending,
  previewError,
  deletePending,
  deleteError,
  onPreview,
  onOpenPreview,
  onDelete,
}: {
  document: DossierDocument | undefined;
  preview: PreviewState | null;
  previewPending: boolean;
  previewError: Error | null;
  deletePending: boolean;
  deleteError: Error | null;
  onPreview: () => void;
  onOpenPreview: () => void;
  onDelete: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Preview</CardTitle>
        <FileText className="size-4 text-primary" />
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {document ? (
          <>
            <Fact label="Fichier" value={document.filename} />
            <Fact label="Type detecte" value={humanizeDocumentType(document.detected_type)} />
            <Fact label="Extraction" value={document.has_extracted_text ? "Texte extrait" : "A revoir"} />
            <Fact label="Analyse" value={document.analysis_status} />
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" type="button" disabled={previewPending} onClick={onPreview}>
                {previewPending ? <Loader2 className="size-4 animate-spin" /> : <Eye className="size-4" />}
                Apercu
              </Button>
              <Button variant="outline" type="button" disabled={!preview} onClick={onOpenPreview}>
                <ExternalLink className="size-4" />
                Ouvrir
              </Button>
              <Button
                className="col-span-2 text-destructive hover:text-destructive"
                variant="outline"
                type="button"
                disabled={deletePending}
                onClick={onDelete}
              >
                {deletePending ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                Supprimer
              </Button>
            </div>
            {preview ? (
              <div className="h-[420px] overflow-hidden rounded-md border bg-background">
                <iframe
                  className="h-full w-full"
                  src={preview.url}
                  title={`Apercu ${preview.filename}`}
                />
              </div>
            ) : (
              <div className="rounded-md border border-dashed p-4 text-xs text-muted-foreground">
                Chargez un apercu via l API protegee.
              </div>
            )}
            {previewError ? <ErrorLine error={previewError} /> : null}
            {deleteError ? <ErrorLine error={deleteError} /> : null}
            {[...document.issues, ...document.warnings].length > 0 ? (
              <div className="grid gap-1">
                {[...document.issues, ...document.warnings].map((message) => (
                  <div key={message} className="text-xs text-amber-800">
                    {message}
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <div className="rounded-md border border-dashed p-4 text-muted-foreground">Aucun document selectionne.</div>
        )}
      </CardContent>
    </Card>
  );
}

function DossierSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="grid gap-4">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-52" />
        <Skeleton className="h-80" />
      </section>
      <aside className="grid content-start gap-4">
        <Skeleton className="h-52" />
        <Skeleton className="h-64" />
        <Skeleton className="h-56" />
      </aside>
    </div>
  );
}

function DossierError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dossier indisponible</CardTitle>
        <Badge variant="warning">API</Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm text-muted-foreground">
        <p>{error instanceof ApiError ? `${error.code}: ${error.message}` : error.message}</p>
        <Button className="w-fit" variant="outline" type="button" onClick={onRetry}>
          <RefreshCcw className="size-4" />
          Retry
        </Button>
      </CardContent>
    </Card>
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
    <div className="min-w-0 rounded-md border bg-background p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-sm font-medium">{value}</div>
    </div>
  );
}

function ErrorLine({ error }: { error: Error }) {
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      {error instanceof ApiError ? `${error.code}: ${error.message}` : error.message}
    </div>
  );
}

function statusVariant(status: string): "success" | "warning" | "secondary" | "outline" {
  if (["uploaded", "classified", "valid"].includes(status)) return "success";
  if (["needs_review", "invalid"].includes(status)) return "warning";
  if (status === "deleted") return "secondary";
  return "outline";
}

function humanizeStatus(status: string): string {
  return status.replaceAll("_", " ");
}

function humanizeDocumentType(value: string | null): string {
  if (!value) return "-";
  const labels: Record<string, string> = {
    payslip: "Fiche de paie",
    identity: "Identite",
    employment_contract: "Contrat de travail",
    tax_notice: "Avis impot",
    latest_tax_notice: "Avis impot recent",
    proof_of_address: "Domicile",
    recent_income: "Revenus recents",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  return dateFormatter.format(new Date(value));
}

function formatFileSize(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${fileSizeFormatter.format(value / 1024)} KB`;
  return `${fileSizeFormatter.format(value / (1024 * 1024))} MB`;
}
