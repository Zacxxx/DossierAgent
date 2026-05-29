import { expect, test } from "@playwright/test";

test("seeded demo path exposes dashboard, listings, dossier, and packet checks", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();
  await expect(page.getByText("Toulouse T2")).toBeVisible();
  await expect(page.getByText("Run summary")).toBeVisible();
  await expect(page.getByText("Validations utilisateur")).toBeVisible();

  await page.getByRole("link", { name: "Annonces" }).click();
  await expect(page.getByRole("heading", { name: "Annonces" })).toBeVisible();
  await expect(page.getByText("30 resultats")).toBeVisible();
  await page.getByRole("button", { name: /T2/ }).first().click();
  await expect(page.getByRole("heading", { name: /T2/ })).toBeVisible();
  await expect(page.getByText("Raisons")).toBeVisible();
  await expect(page.getByText("Risques")).toBeVisible();

  await page.getByRole("link", { name: "Dossier" }).click();
  await expect(page.getByRole("heading", { name: "Dossier" })).toBeVisible();
  await expect(page.getByText("78%")).toBeVisible();
  await expect(page.getByText("Checklist")).toBeVisible();
  await page.getByRole("button", { name: "Analyser" }).click();
  await expect(page.getByText("Pieces a completer")).toBeVisible();

  await page.getByRole("link", { name: "Paquets" }).click();
  await expect(page.getByRole("heading", { name: "Paquets" })).toBeVisible();
  await expect(page.getByText("checks en attente")).toBeVisible();
  await page.getByRole("button", { name: "Generer paquet" }).click();
  await expect(page.getByText("ready_for_review")).toBeVisible();
  await expect(page.getByText("Relire le paquet de contact").first()).toBeVisible();
  await page.getByRole("button", { name: "Approuver" }).first().click();
  await expect(page.getByText("Derniere validation")).toBeVisible();
  await expect(page.getByText(/approved/)).toBeVisible();
});
