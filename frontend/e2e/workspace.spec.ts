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
  await page.getByRole("button", { name: /Import sample “lanternfall”/ }).click();
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
  await page.getByRole("radio", { name: "Exact" }).click();
  await page.getByLabel("Search query").fill('"sea wall"');
  await page.getByRole("button", { name: "Search" }).click();
  const hits = page.getByTestId("search-hit");
  await expect(hits.first()).toBeVisible();
  await expect(hits.first().locator("mark").first()).toHaveText(/sea/i);
  const snippet = await hits.first().locator(".snippet").innerText();
  await hits.first().getByTestId("search-hit-link").click();
  await expect(page.getByTestId("span-highlight")).toHaveText(snippet);
});

test("hybrid search answers a question and explains each result", async ({ page, request }) => {
  const novelId = await importSample(request);
  // The API's in-process worker embeds the chapters in the background.
  await expect
    .poll(async () => (await (await request.get(`/api/novels/${novelId}/index`)).json()).coverage, {
      timeout: 20_000,
    })
    .toEqual(expect.objectContaining({ embedded: expect.any(Number) }));
  await expect
    .poll(async () => {
      const c = (await (await request.get(`/api/novels/${novelId}/index`)).json()).coverage;
      return c.embedded === c.total;
    })
    .toBe(true);
  await page.goto(`/novels/${novelId}/search?q=${encodeURIComponent("What colour are Mara's eyes?")}`);
  await expect(page.getByRole("radio", { name: "Hybrid", exact: true })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  // E2E runs with the deterministic mock embedder, so only require the answer in the top 3.
  const hits = page.getByTestId("search-hit");
  await expect(hits.first().locator(".chip").filter({ hasText: "fused #1" })).toBeVisible();
  const top3 = await hits.evaluateAll((els) => els.slice(0, 3).map((e) => e.textContent ?? ""));
  expect(top3.some((t) => t.includes("Mara's grey eyes"))).toBe(true);
  await page.getByRole("radio", { name: "Exact" }).click();
  await expect(page.getByTestId("search-summary")).toContainText("0 results");
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

test("review: accept into canon, refuse silent overwrite, reject out of the report", async ({
  page,
  request,
}) => {
  await request.post("/api/samples/lanternfall/import");
  const novelId = (await (await request.get("/api/novels")).json()).find(
    (n: { slug: string | null }) => n.slug === "lanternfall",
  ).id;
  await page.goto(`/novels/${novelId}/review`);
  const items = page.getByTestId("review-item");

  // Accept Mara's grey eyes: it becomes canon and appears in the change log.
  const grey = items.filter({ hasText: "Mara's grey eyes" });
  await grey.getByRole("button", { name: "Accept" }).click();
  await expect(items.filter({ hasText: "Mara's grey eyes" })).toHaveCount(0);

  // Hollin contradicts the character sheet (Varrow): accepting asks first, and we keep canon.
  const hollin = items.filter({ hasText: "Tomas was born in Hollin" });
  await expect(hollin).toContainText("Canon says “Varrow”");
  await hollin.getByRole("button", { name: "Accept" }).click();
  await expect(hollin.getByRole("alert")).toContainText("Varrow");
  await hollin.getByRole("button", { name: "Keep canon" }).click();

  // Reject the right-handed statement: the handedness contradiction disappears.
  await items.filter({ hasText: "Tomas was right-handed" }).getByRole("button", { name: "Reject" }).click();
  await page.goto(`/novels/${novelId}/contradictions`);
  await expect(page.getByTestId("finding").filter({ hasText: "handedness" })).toHaveCount(0);

  await page.goto(`/novels/${novelId}/canon`);
  await expect(page.getByTestId("canon-changes")).toContainText("attributes.eye_color");
  await expect(page.getByTestId("canon-changes")).toContainText("grey");
});

test("dismiss a finding with a reason; it moves to the dismissed tab", async ({ page, request }) => {
  const novel = await (await request.post("/api/novels", { data: { title: "Dismissal" } })).json();
  await request.post(`/api/novels/${novel.id}/characters`, { data: { name: "Kell Varn" } });
  const chapters = ["Kell was left-handed.", "Kell was right-handed."];
  for (const body of chapters) {
    await request.post(`/api/novels/${novel.id}/chapters`, { data: { title: "C", body } });
  }
  await page.goto(`/novels/${novel.id}/contradictions`);
  const finding = page.getByTestId("finding");
  await expect(finding).toHaveCount(1);
  await finding.getByRole("button", { name: "Dismiss…" }).click();
  await expect(finding.getByRole("button", { name: "Dismiss", exact: true })).toBeDisabled();
  await finding.getByLabel("Reason").fill("intentional: Kell is lying");
  await finding.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(page.getByTestId("finding")).toHaveCount(0);
  await page.getByRole("radio", { name: /dismissed/ }).click();
  await expect(page.getByTestId("finding")).toContainText("intentional: Kell is lying");
  await page.getByRole("button", { name: "Reopen" }).click();
  await page.getByRole("radio", { name: /open/ }).click();
  await expect(page.getByTestId("finding")).toHaveCount(1);
});

test("draft assistant: plan, approve, stream a draft, check it, apply it", async ({ page, request }) => {
  const novel = await (await request.post("/api/novels", { data: { title: "Assisted" } })).json();
  await request.post(`/api/novels/${novel.id}/chapters`, {
    data: { title: "Opening", body: "The harbour was quiet." },
  });
  await page.goto(`/novels/${novel.id}/draft`);
  await page.getByLabel("Goal").fill("The fog arrives and the lamps are lit early");
  await page.getByLabel("Target chapter").selectOption("");
  await page.getByRole("button", { name: "Start" }).click();
  const status = page.getByTestId("workflow-status");
  await expect(status).toHaveText("awaiting plan approval", { timeout: 15_000 });
  await page.getByLabel("Plan").fill("1. Fog.\n2. Lamps.");
  await page.getByRole("button", { name: "Approve plan and draft" }).click();
  await expect(status).toHaveText("awaiting decision", { timeout: 15_000 });
  await expect(page.getByText("Check: no conflicts found")).toBeVisible();
  await expect(page.getByTestId("draft-text")).toContainText("harbour lamps");
  await page.getByRole("button", { name: "Apply as new chapter version" }).click();
  await expect(page.getByText(/Applied as version 1/)).toBeVisible();
  await expect(page.locator(".chapter-list li")).toHaveCount(2);
});

test("character graph and timeline show evidence and contradictions", async ({ page, request }) => {
  const novelId = await importSample(request);
  await page.goto(`/novels/${novelId}/graph`);
  await expect(page.getByTestId("graph-node")).toHaveCount(3);
  await page.getByTestId("graph-node").filter({ hasText: "Mara Venn" }).click();
  await expect(page.getByTestId("graph-details")).toContainText("Mara Venn");
  await page.getByRole("radio", { name: "Timeline" }).click();
  await expect(page.getByTestId("timeline-event").first()).toBeVisible();
  await expect(page.getByTestId("timeline-conflict").first()).toBeAttached();
  await page.getByTestId("timeline-event").first().click();
  await expect(page).toHaveURL(/\/chapters\/.+\?start=\d+&end=\d+/);
  await expect(page.getByTestId("span-highlight")).toBeVisible();
});

test("story logic: replay a recorded local-model audit and follow its evidence", async ({
  page,
  request,
}) => {
  const res = await request.post("/api/samples/xueye-dangpu/import");
  expect(res.ok()).toBeTruthy();
  const novelId = (await res.json()).novel_id;
  await page.goto(`/novels/${novelId}/story`);
  await expect(page.getByRole("heading", { name: "人物与故事线" })).toBeVisible();
  await page.getByTestId("story-llm").selectOption("replay:ollama:qwen2.5:7b");
  await page.getByRole("button", { name: "开始审查" }).click();
  await expect(page.getByTestId("story-usage")).toContainText("replay:ollama:qwen2.5:7b", {
    timeout: 20_000,
  });

  const runs = await (await request.get(`/api/novels/${novelId}/story-audits`)).json();
  const run = await (await request.get(`/api/story-audits/${runs[0].id}`)).json();
  expect(run.status).toBe("done");
  const issues = page.getByTestId("story-issue");
  await expect(issues).toHaveCount(run.result.issues.length);
  expect(run.result.issues.length).toBeGreaterThan(0);

  // Evidence opens the chapter with exactly that span highlighted.
  const link = page.getByTestId("story-evidence").first();
  const quote = stripQuotes(await link.innerText());
  await link.click();
  await expect(page).toHaveURL(/\/chapters\/[0-9a-f-]+\?start=\d+&end=\d+/);
  await expect(page.getByTestId("span-highlight")).toHaveText(quote);

  await page.goto(`/novels/${novelId}/story`);
  await page.getByRole("button", { name: "人物动机" }).click();
  await expect(page.getByTestId("story-beat").first()).toBeVisible();
  await page.getByRole("button", { name: "节奏曲线" }).click();
  await expect(page.locator(".story-chart circle")).toHaveCount(
    run.result.pulses.filter((p: { tension: number }) => p.tension > 0).length,
  );

  // A revision suggestion opens the draft assistant with the goal filled in.
  if (run.result.suggestions.length > 0) {
    await page.getByRole("button", { name: /重大事故点/ }).click();
    await page.getByTestId("story-draft-link").first().click();
    await expect(page).toHaveURL(/\/draft\?goal=/);
    await expect(page.getByLabel("Goal")).toHaveValue(
      new RegExp(run.result.suggestions[0].change.slice(0, 12).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    );
  }
});
