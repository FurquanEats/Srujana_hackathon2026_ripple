import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Each role's pages, as its sidebar lists them. */
const ROLES: { role: string; member?: string; pages: string[] }[] = [
  {
    role: "nodal_officer",
    member: "bank-b",
    pages: ["/app/overview", "/app/notices", "/app/liens", "/app/payment-check", "/app/audit"],
  },
  {
    role: "frm_analyst",
    member: "bank-d",
    pages: [
      "/app/overview",
      "/app/flags",
      "/app/holds",
      "/app/detection",
      "/app/payment-check",
      "/app/audit",
    ],
  },
  { role: "grievance_officer", member: "bank-a", pages: ["/app/reviews", "/app/reviews/D05"] },
  { role: "police_officer", pages: ["/app/overview", "/app/cases", "/app/hold-reports"] },
  { role: "demo", pages: ["/app/simulation", "/app/cases"] },
  { role: "account_holder", pages: ["/app/my-hold"] },
  { role: "victim", pages: ["/app/my-complaint"] },
];

async function signIn(page: Page, role: string, member?: string) {
  await page.goto("/sign-in");
  await page.check(`input[value="${role}"]`);
  if (member) await page.selectOption("#member", member);
  await Promise.all([page.waitForURL(/\/app\//), page.getByRole("button", { name: "Continue" }).click()]);
}

function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

async function sideways(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

for (const width of [1440, 390]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("the home page renders every section without errors", async ({ page }) => {
      const errors = watchConsole(page);
      await page.goto("/");
      for (const heading of ["Follow the money.", "Trace it yourself"])
        await expect(page.getByText(heading, { exact: false }).first()).toBeVisible();
      expect(await sideways(page)).toBe(0);
      expect(errors).toEqual([]);
    });

    for (const { role, member, pages } of ROLES) {
      test(`${role} can open every page`, async ({ page }) => {
        const errors = watchConsole(page);
        await signIn(page, role, member);
        for (const path of pages) {
          const response = await page.goto(path);
          expect(response?.status(), path).toBe(200);
          await expect(page.locator("h1")).toBeVisible();
          expect(await sideways(page), path).toBe(0);
        }
        expect(errors).toEqual([]);
      });
    }
  });
}

test("an FRM analyst places a hold and the customer notice is sent", async ({ page }) => {
  await signIn(page, "frm_analyst", "bank-c");
  await page.goto("/app/flags");
  const row = page.locator("tbody tr").filter({ hasNotText: "Hold active" }).first();
  await row.locator("a").click();
  await page.getByRole("button", { name: "Place hold and send notice" }).click();
  await expect(page.getByRole("status")).toContainText("Hold placed");
});

test("the police instruct a bank on a reported hold", async ({ page }) => {
  await signIn(page, "police_officer");
  await page.goto("/app/hold-reports");
  await page.getByRole("button", { name: "Send instruction" }).first().click();
  await expect(page.getByRole("status")).toContainText("Instruction sent");
});

test("a grievance officer confirms a verdict", async ({ page }) => {
  await signIn(page, "grievance_officer", "bank-a");
  await page.goto("/app/reviews/D01");
  await page.getByRole("button", { name: "Confirm verdict" }).first().click();
  await expect(page.getByRole("status")).toContainText("confirmed");
});

test("the trail replays hop by hop", async ({ page }) => {
  await signIn(page, "police_officer");
  await page.goto("/app/cases");
  await page.locator("tbody tr a").first().click();
  const slider = page.getByRole("slider", { name: "Replay position" });
  await slider.fill("0");
  await expect(page.getByText(/Step 1 of/)).toBeVisible();
});

test("the home page and sign-in have no serious accessibility problems", async ({ page }) => {
  for (const path of ["/", "/sign-in"]) {
    await page.goto(path);
    // The footer's giant wordmark is decoration, hidden from assistive technology, in the reference site's style.
    // axe pins its own copy of the playwright-core types, so the page is passed through as is
    const { violations } = await new AxeBuilder({ page: page as never })
      .exclude("[data-decorative]")
      .analyze();
    const serious = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${path}: ${v.id}`)).toEqual([]);
  }
});
