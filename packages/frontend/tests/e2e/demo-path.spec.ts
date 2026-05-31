import { expect, test } from "@playwright/test";

test("seeded demo path exposes dashboard, listings, dossier, and packet checks", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();
  await expect(page.getByText("Toulouse T2")).toBeVisible();
  await expect(page.getByText("Run summary")).toBeVisible();
  await expect(page.getByText("Validations utilisateur")).toBeVisible();
  await expect(page.locator("img[alt*='Saint-Cyprien']").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Explorer" }).first()).toHaveAttribute(
    "href",
    /demo\.dossieragent\.local\/listings\/001/,
  );
  await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible();
  await page.getByRole("button", { name: "Marquer lue" }).first().click();
  await expect(page.getByText("Lue").first()).toBeVisible();

  await page.getByRole("link", { name: "AI Chat" }).click();
  await expect(page.getByRole("heading", { name: "AI Chat" })).toBeVisible();
  await expect(page.getByText("OpenAI").first()).toBeVisible();
  await page.getByPlaceholder("Message").fill("Affiche les annonces recommandees");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("show_recommended_listings")).toBeVisible();
  await expect(page.getByText(/annonces trouvees/)).toBeVisible();

  await page.getByRole("link", { name: "Veilles" }).click();
  await expect(page.getByRole("heading", { name: "Veilles" })).toBeVisible();
  await expect(page.getByText("Toulouse T2").first()).toBeVisible();
  await page.getByRole("button", { name: "Run now" }).first().click();
  await expect(page.getByText("completed").first()).toBeVisible();

  await page.getByRole("link", { name: "Historique" }).click();
  await expect(page.getByRole("heading", { name: "Historique" })).toBeVisible();
  await expect(page.getByText("RunEventTimeline")).toBeVisible();
  await expect(page.getByText("source_scan_started")).toBeVisible();
  await expect(page.getByText("completed").first()).toBeVisible();

  await page.getByRole("link", { name: "Annonces" }).click();
  await expect(page.getByRole("heading", { name: "Annonces" })).toBeVisible();
  await expect(page.getByText("32 resultats")).toBeVisible();
  await expect(page.getByText("Deux pieces renove rue des Filatiers")).toBeVisible();
  await page.getByRole("button", { name: "T2 Carmes calme balcon" }).click();
  await expect(page.getByRole("heading", { name: "T2 Carmes calme balcon" })).toBeVisible();
  await expect(page.locator("img[alt*='Carmes']").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Explorer" }).first()).toHaveAttribute(
    "href",
    /demo\.dossieragent\.local\/listings\/repost-carmes-002/,
  );
  await expect(page.getByText("Raisons")).toBeVisible();
  await expect(page.getByText("Risques")).toBeVisible();

  await page.getByRole("link", { name: "Dossier" }).click();
  await expect(page.getByRole("heading", { name: "Dossier" })).toBeVisible();
  await expect(page.getByText("78%")).toBeVisible();
  await expect(page.getByText("Checklist")).toBeVisible();
  await page.getByRole("button", { name: "Analyser" }).click();
  await expect(page.getByText("Pieces a completer")).toBeVisible();
  await page.setInputFiles("input[type='file']", {
    name: "preview-test.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"),
  });
  await expect(page.getByText("preview-test.pdf").first()).toBeVisible();
  await page.getByRole("button", { name: "Apercu" }).click();
  await expect(page.locator("iframe[title='Apercu preview-test.pdf']")).toBeVisible();
  await page.getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByText("preview-test.pdf")).toHaveCount(0);

  await page.getByRole("link", { name: "Paquets" }).click();
  await expect(page.getByRole("heading", { name: "Paquets" })).toBeVisible();
  await expect(page.getByText("checks en attente")).toBeVisible();
  await page.getByRole("button", { name: "Generer paquet" }).click();
  await expect(page.getByText("ready_for_review").first()).toBeVisible();
  await page.getByLabel("Message brouillon").fill("Message relu et pret a copier.");
  await expect(page.getByLabel("Message brouillon")).toHaveValue("Message relu et pret a copier.");
  const savePacketResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/contact-packets/") &&
      response.request().method() === "PATCH" &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await savePacketResponse;
  await expect(page.getByLabel("Message brouillon")).toHaveValue("Message relu et pret a copier.");
  await page.getByRole("button", { name: "Copier", exact: true }).click();
  await expect(page.getByText("Message copie pour envoi manuel.")).toBeVisible();
  await page.getByRole("button", { name: "Marquer utilise" }).click();
  await expect(page.getByText("used").first()).toBeVisible();
  await expect(page.getByText("Relire le paquet de contact").first()).toBeVisible();
  await page.getByRole("button", { name: "Approuver" }).first().click();
  await expect(page.getByText("Derniere validation")).toBeVisible();
  await expect(page.getByText(/ - approved/)).toBeVisible();
});

test("settings and auth screens handle provider secrets and Supabase flows", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByText("AI providers")).toBeVisible();
  await expect(page.getByLabel("Provider")).toHaveValue("openai");

  await page.getByLabel("Provider").selectOption("codex");
  await page.getByLabel("Codex path").fill("/bin/echo");
  await page.getByLabel("Mode").selectOption("json_stdio");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("stored:provider_path")).toBeVisible();
  await expect(page.getByText("stored:provider_mode")).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText("stored:provider_path")).toHaveCount(0);
  await expect(page.getByText("stored:provider_mode")).toBeVisible();

  await page.route("**/api/v1/auth/register", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ status: "confirmation_required", user: null, session: null }),
    });
  });
  await page.route("**/api/v1/auth/password/forgot", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "recovery_requested" }),
    });
  });
  await page.route("**/api/v1/auth/logout", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "logged_out" }),
    });
  });

  await page.goto("/auth");
  await expect(page.getByRole("heading", { name: "Auth" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Login" })).toBeVisible();
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByRole("heading", { name: "Register" })).toBeVisible();
  await page.getByLabel("Email").fill("demo@example.com");
  await page.getByLabel("Display name").fill("Demo User");
  await page.getByLabel("Password").fill("password-123");
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByText("Confirmation email sent.")).toBeVisible();

  await page.getByRole("button", { name: "Forgot password" }).click();
  await expect(page.getByRole("heading", { name: "Forgot Password" })).toBeVisible();
  await page.getByLabel("Email").fill("demo@example.com");
  await page.getByRole("button", { name: "Request Reset" }).click();
  await expect(page.getByText("Password reset email requested.")).toBeVisible();

  await page.evaluate(() => {
    window.localStorage.setItem(
      "dossieragent.auth.session",
      JSON.stringify({
        access_token: "access-token-e2e",
        refresh_token: "refresh-token-e2e",
        token_type: "bearer",
        expires_in: 3600,
        expires_at: null,
        user: {
          provider: "supabase",
          provider_user_id: "provider-user-e2e",
          app_user_id: "usr_demo",
          email: "demo@example.com",
          display_name: "Demo User",
        },
      }),
    );
  });
  await page.goto("/auth");
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page.getByRole("link", { name: "Login" })).toBeVisible();
});
