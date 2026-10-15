import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

test.describe.configure({ mode: "serial" });

const stripQuotes = (s: string) => s.trim().replace(/^“/, "").replace(/”$/, "");

async function importSample(request: APIRequestContext): Promise<string> {
  const res = await request.post("/api/samples/lanternfall/import");
  expect(res.ok()).toBeTruthy();
  return (await res.json()).novel_id;
}

async function openContradictions(page: Page, novelId: string) {
  await page.goto(`/novels/${novelId}/contradictions`);
  await expect(page.getByTestId("report-summary")).toBeVisible();
}

test("import the sample from the home page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Import sample/ }).click();
  await expect(page).toHaveURL(/\/novels\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "The Lanternfall Ledger" })).toBeVisible();
  await expect(page.locator(".chapter-list li")).toHaveCount(3);
});

test("every contradiction citation opens the chapter with that exact span highlighted", async ({
  page,
  request,
}) => {
  const novelId = await importSample(request);
  await openContradictions(page, novelId);
  await expect(page.getByTestId("finding")).toHaveCount(4);
  const linkCount = await page.getByTestId("evidence-link").count();
  expect(linkCount).toBe(7);

  for (let i = 0; i < linkCount; i++) {
    await openContradictions(page, novelId);
    const link = page.getByTestId("evidence-link").nth(i);
    const quote = stripQuotes(await link.innerText());
    await link.click();
    await expect(page).toHaveURL(/\/chapters\/[0-9a-f-]+\?start=\d+&end=\d+/);
    const mark = page.getByTestId("span-highlight");
    await expect(mark).toHaveText(quote);
    await expect(mark).toBeInViewport();
  }
});

test("hedged and dialogue statements appear only when asked for", async ({ page, request }) => {
  const novelId = await importSample(request);
  await openContradictions(page, novelId);
  await expect(page.getByTestId("finding")).toHaveCount(4);
  await page.getByLabel(/Include hedged statements/).check();
  await expect(page.getByTestId("finding")).toHaveCount(6);
  await expect(page.getByText("“Ilsa's eyes seemed almost black”")).toBeVisible();
});

test("search results link to the matching passage", async ({ page, request }) => {
  const novelId = await importSample(request);
  await page.goto(`/novels/${novelId}/search`);
  await page.getByLabel("Search query").fill('"sea wall"');
  await page.getByRole("button", { name: "Search" }).click();
  const hits = page.getByTestId("search-hit");
  await expect(hits.first()).toBeVisible();
  await expect(hits.first().locator("mark").first()).toHaveText(/sea/i);
  const snippet = await hits.first().locator(".snippet").innerText();
  await hits.first().getByTestId("search-hit-link").click();
  await expect(page.getByTestId("span-highlight")).toHaveText(snippet);
});

test("edits persist, and a stale save shows a conflict instead of overwriting", async ({
  page,
  request,
}) => {
  const novel = await (await request.post("/api/novels", { data: { title: "Scratch" } })).json();
  const chapter = await (
    await request.post(`/api/novels/${novel.id}/chapters`, {
      data: { title: "Opening", body: "First draft." },
    })
  ).json();

  await page.goto(`/novels/${novel.id}/chapters/${chapter.id}`);
  const editor = page.getByLabel("Chapter text");
  await editor.fill("Second draft, with *emphasis*.");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved version 2")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Chapter text")).toHaveValue("Second draft, with *emphasis*.");

  await page.getByRole("tab", { name: "Preview" }).click();
  await expect(page.locator(".prose em")).toHaveText("emphasis");
  await page.getByRole("tab", { name: "Write" }).click();

  // Someone else saves version 3 while this tab still holds version 2.
  const other = await request.patch(`/api/chapters/${chapter.id}`, {
    data: { version: 2, body: "Edited in another tab." },
  });
  expect(other.ok()).toBeTruthy();

  await page.getByLabel("Chapter text").fill("My conflicting edit.");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Not saved");
  const current = await (await request.get(`/api/chapters/${chapter.id}`)).json();
  expect(current.body).toBe("Edited in another tab.");

  await page.getByRole("button", { name: "Save mine anyway" }).click();
  await expect(page.getByText("Saved version 4")).toBeVisible();
  const revisions = await (await request.get(`/api/chapters/${chapter.id}/revisions`)).json();
  expect(revisions.map((r: { version: number }) => r.version)).toEqual([4, 3, 2, 1]);
});

test("fixing the text in the editor clears the contradiction", async ({ page, request }) => {
  const novelId = await importSample(request);
  await openContradictions(page, novelId);
  await page.getByText("“Mara's eyes were green”").click();
  await page.getByRole("tab", { name: "Write" }).click();
  const editor = page.getByLabel("Chapter text");
  const text = await editor.inputValue();
  await editor.fill(text.replace("Mara's eyes were green", "Mara's eyes were grey"));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(/Saved version 2/)).toBeVisible();
  await page.getByRole("link", { name: "Contradictions" }).click();
  await expect(page.getByTestId("finding")).toHaveCount(3);
  await expect(page.getByText("eye colour", { exact: false })).toHaveCount(0);
});

test("a canon fact added on the character sheet is checked against the text", async ({
  page,
  request,
}) => {
  const novelId = await importSample(request);
  await page.goto(`/novels/${novelId}/characters`);
  const mara = page.getByTestId("character-card").filter({ hasText: "Mara Venn" });
  await mara.getByRole("button", { name: "Edit" }).click();
  const editor = page.getByTestId("character-editor");
  await editor.getByRole("button", { name: "+ Add fact" }).click();
  await editor.getByLabel("Attribute", { exact: true }).selectOption("hair_color");
  await editor.getByLabel("Attribute value").fill("red");
  await editor.getByRole("button", { name: "Save" }).click();
  await expect(mara.getByText("hair colour")).toBeVisible();

  await openContradictions(page, novelId);
  const finding = page.getByTestId("finding").filter({ hasText: "hair colour" });
  await expect(finding).toContainText("Contradicts character sheet");
  await expect(finding).toContainText("“Mara's hair was black”");
});

test("create, rename and delete a novel; add and delete a chapter", async ({ page }) => {
  page.on("dialog", (d) => d.accept());
  await page.goto("/");
  await page.getByLabel("Novel title").fill("Working Title");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Working Title" })).toBeVisible();

  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Novel title").fill("Final Title");
  await page.getByLabel("Synopsis").fill("A short synopsis.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("heading", { name: "Final Title" })).toBeVisible();
  await expect(page.getByText("A short synopsis.")).toBeVisible();

  await page.getByRole("button", { name: "Add chapter" }).click();
  await expect(page.getByLabel("Chapter title")).toHaveValue("Chapter 1");
  await expect(page.locator(".chapter-list li")).toHaveCount(1);
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.locator(".chapter-list li")).toHaveCount(0);

  await page.goto("/");
  const card = page.locator(".card").filter({ hasText: "Final Title" });
  await card.getByRole("button", { name: "Delete" }).click();
  await expect(page.locator(".card").filter({ hasText: "Final Title" })).toHaveCount(0);
});
