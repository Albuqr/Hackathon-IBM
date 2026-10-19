// E2E do app Brasil no navegador (Seam 3 da spec brasil-app).
// Pré-requisito: API + frontend com BRASIL_DEV_LOGIN=1 e o banco semeado por
// `BRASIL_DB_PATH=… python -m middleware.brasil.semear_teste` (semear antes de cada rodada).
// Rodar: BASE_URL=http://localhost:5000 node --test --test-concurrency=1 frontend/brasil/tests/e2e/app.spec.mjs
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const BASE = process.env.BASE_URL || "http://localhost:5000";
let browser;
before(async () => { browser = await chromium.launch(); });
after(async () => { await browser?.close(); });

async function entrar(perfil, { viewport = { width: 1280, height: 720 }, url = "/brasil/mapa", colorScheme = "light" } = {}) {
  const ctx = await browser.newContext({ viewport, colorScheme });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/brasil/dev-login/${perfil}`);
  if (url !== "/brasil/mapa") await page.goto(BASE + url);
  if (url.startsWith("/brasil/mapa")) await pronto(page);
  return page;
}
const pronto = (page) => page.waitForSelector('body[data-pronto="1"]', { timeout: 40000 });
const visiveis = (page) => page.evaluate(() => window.__brasil.visiveis().sort());
const marcadores = (page) => page.evaluate(() => window.__brasil.marcadores().sort());
const semRolagem = (page) => page.evaluate(() => document.scrollingElement.scrollHeight <= innerHeight);

test("AC-001.1 tela cheia sem rolagem (desktop e celular) e barra lateral lembrada", async () => {
  const page = await entrar("admin");
  assert.ok(await semRolagem(page));
  for (const sel of [".topo", "#lateral", "#mapa", ".statusbar"]) assert.ok(await page.isVisible(sel), sel);
  await page.click("#alternar-lateral");
  await page.reload(); await pronto(page);
  assert.ok(await page.evaluate(() => document.body.classList.contains("recolhida")));
  const cel = await entrar("voluntario", { viewport: { width: 390, height: 844 } });
  assert.ok(await semRolagem(cel));
});

test("AC-002.1 modo Pixels troca o fundo e fica lembrado · AC-005.1 crises acendem pixels", async () => {
  const page = await entrar("voluntario");
  await page.click('[data-modo="pixels"]');
  await page.waitForFunction(() => window.__brasil.pixelsAcesos() > 0);
  assert.deepEqual(await marcadores(page), []);
  await page.reload(); await pronto(page);
  assert.equal(await page.getAttribute('[data-modo="pixels"]', "aria-pressed"), "true");
  assert.ok(await page.evaluate(() => window.__brasil.pixelsAcesos() > 0));
});

test("AC-004.1 duas crises na mesma coordenada são dois marcadores", async () => {
  const page = await entrar("voluntario");
  const m = await marcadores(page);
  assert.ok(m.includes("teste-pelotas-2") && m.includes("teste-pelotas-5"));
});

test("AC-006.1 voluntário se inscreve pelo popup e os números mudam", async () => {
  const page = await entrar("voluntario");
  await page.evaluate(() => window.__brasil.abrir("teste-altamira"));
  const pop = page.locator('.pop[data-crise="teste-altamira"]');
  assert.equal((await pop.locator('[data-n="voluntarios"]').textContent()).trim(), "0");
  await pop.getByRole("button", { name: "Inscrever-se" }).click();
  await pop.getByRole("button", { name: "Cancelar inscrição" }).waitFor();
  assert.equal((await pop.locator('[data-n="voluntarios"]').textContent()).trim(), "1");
  await pop.getByRole("button", { name: "Cancelar inscrição" }).click();
  await pop.getByRole("button", { name: "Inscrever-se" }).waitFor();
});

test("AC-015.2 sair de uma crise pelo perfil devolve o Inscrever-se ao popup", async () => {
  const page = await entrar("voluntario");
  await page.evaluate(() => window.__brasil.abrir("teste-caxias"));
  await page.locator(".pop").getByRole("button", { name: "Inscrever-se" }).click();
  await page.locator(".pop").getByRole("button", { name: "Cancelar inscrição" }).waitFor();
  await page.goto(`${BASE}/brasil/perfil`);
  const item = page.locator("#minhas li", { hasText: "Teste Caxias do Sul chuva" });
  await item.getByRole("button", { name: "Sair" }).click();
  await item.waitFor({ state: "detached" });
  await page.goto(`${BASE}/brasil/mapa`); await pronto(page);
  await page.evaluate(() => window.__brasil.abrir("teste-caxias"));
  assert.ok(await page.locator(".pop").getByRole("button", { name: "Inscrever-se" }).isVisible());
});

test("AC-006.2 admin vê Confirmar na notícia; ONG vê Criar campanha e não Confirmar · AC-018.1 pré-preenchido", async () => {
  const adm = await entrar("admin");
  await adm.evaluate(() => window.__brasil.abrir("teste-noticia-recife"));
  assert.ok(await adm.locator(".pop").getByRole("button", { name: "Confirmar" }).isVisible());
  const ong = await entrar("ong");
  await ong.evaluate(() => window.__brasil.abrir("teste-noticia-recife"));
  assert.equal(await ong.locator(".pop").getByRole("button", { name: "Confirmar" }).count(), 0);
  await ong.locator(".pop").getByRole("link", { name: "Criar campanha" }).click();
  await ong.waitForURL(/\/brasil\/ong\/nova\?crise=/);
  await ong.waitForSelector('#crises input[value="teste-noticia-recife"]');
  assert.ok(await ong.isChecked('#crises input[value="teste-noticia-recife"]'));
});

test("AC-007.1 alerta de área destaca os municípios ao abrir e some ao fechar", async () => {
  const page = await entrar("voluntario");
  await page.evaluate(() => window.__brasil.abrir("teste-aviso-sc-rs"));
  await page.waitForFunction(() => window.__brasil.area() === 3);
  await page.locator(".leaflet-popup-close-button").click();
  await page.waitForFunction(() => window.__brasil.area() === 0);
});

test("AC-008.1 severidade mínima filtra marcadores e números juntos · AC-010.1", async () => {
  const page = await entrar("voluntario");
  await page.locator("#f-sev").fill("4");
  await page.waitForFunction(() => window.__brasil.visiveis().length === 3);
  assert.deepEqual(await visiveis(page), ["teste-altamira", "teste-pelotas-5", "teste-poa-4"]);
  assert.deepEqual(await marcadores(page), ["teste-altamira", "teste-pelotas-5", "teste-poa-4"]);
  assert.equal(await page.textContent("#m-crises"), "3");
  assert.equal(await page.textContent("#m-criticas"), "3");
});

test("AC-009.1 UF = RS inclui o alerta centrado em SC · AC-011.1 filtros sobrevivem ao recarregar", async () => {
  const page = await entrar("voluntario");
  await page.selectOption("#f-uf", "RS");
  await page.waitForFunction(() => window.__brasil.visiveis().includes("teste-aviso-sc-rs"));
  assert.ok(!(await visiveis(page)).includes("teste-altamira"));
  await page.selectOption("#f-tipo", "meteorological");
  assert.match(page.url(), /uf=RS/);
  await page.reload(); await pronto(page);
  assert.equal(await page.inputValue("#f-uf"), "RS");
  assert.equal(await page.inputValue("#f-tipo"), "meteorological");
  assert.deepEqual(await visiveis(page), ["teste-aviso-sc-rs", "teste-caxias", "teste-pelotas-2", "teste-poa-2"]);
});

test("AC-008.2 busca por município", async () => {
  const page = await entrar("voluntario");
  await page.fill("#f-q", "pelotas");
  await page.waitForFunction(() => window.__brasil.visiveis().length === 2);
  assert.deepEqual(await visiveis(page), ["teste-pelotas-2", "teste-pelotas-5"]);
});

test("AC-013.1 falha nas crises mostra Tentar de novo e recupera", async () => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/brasil/dev-login/voluntario`);
  await page.route("**/brasil/acao/crises", (r) => r.fulfill({ status: 502, body: "Bad Gateway" }));
  await page.reload();
  await page.waitForSelector("#falha:not([hidden])");
  assert.ok(await page.isDisabled("#f-uf"));
  await page.unroute("**/brasil/acao/crises");
  await page.click("#tentar");
  await pronto(page);
  assert.ok(!(await page.isDisabled("#f-uf")));
});

test("AC-016.1 badge de convites pendentes cai ao aceitar · AC-014.1 menu por perfil", async () => {
  const page = await entrar("voluntario", { url: "/brasil/campanhas" });
  await page.waitForSelector("#badge-convites:not([hidden])");
  assert.equal(await page.textContent("#badge-convites"), "2");
  await page.getByRole("button", { name: "Aceitar" }).first().click();
  await page.waitForFunction(() => document.getElementById("badge-convites").textContent === "1");
  const ong = await entrar("ong", { url: "/brasil/ong" });
  assert.equal(await ong.locator("#badge-convites").count(), 0);
});

test("AC-021.1 tema segue o sistema na primeira visita e a escolha fica lembrada", async () => {
  const page = await entrar("voluntario", { colorScheme: "dark" });
  assert.equal(await page.getAttribute("html", "data-theme"), "dark");
  await page.click("#alternar-tema");
  await page.reload(); await pronto(page);
  assert.equal(await page.getAttribute("html", "data-theme"), "light");
});

// Clique real (marcador e pixel), sem atalhos: posição da crise na tela → clique do mouse.
async function clicarNaCrise(page, id) {
  const pt = await page.evaluate((id) => {
    const m = window.__brasil.mapa, c = { "teste-altamira": [-3.2, -52.2] }[id];
    m.setView(c, 7, { animate: false });
    const p = m.latLngToContainerPoint(c), r = m.getContainer().getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y };
  }, id);
  await page.waitForTimeout(300);  // um quadro para marcadores/pixels redesenharem na nova vista
  await page.mouse.click(pt.x, pt.y);
}

test("AC-006.1 clicar no marcador abre o popup da crise", async () => {
  const page = await entrar("voluntario");
  await clicarNaCrise(page, "teste-altamira");
  await page.waitForSelector('.pop[data-crise="teste-altamira"]');
});

test("AC-005.1 clicar num pixel aceso abre a crise que o acendeu", async () => {
  const page = await entrar("voluntario", { url: "/brasil/mapa?modo=pixels" });
  await page.waitForFunction(() => window.__brasil.pixelsAcesos() > 0);
  await clicarNaCrise(page, "teste-altamira");
  await page.waitForSelector('.pop[data-crise="teste-altamira"]');
});

test("AC-006.2 admin confirma a notícia pelo popup e o selo some", async () => {
  const page = await entrar("admin");
  await page.evaluate(() => window.__brasil.abrir("teste-noticia-recife"));
  await page.locator(".pop").getByRole("button", { name: "Confirmar" }).click();
  await page.waitForFunction(() => document.getElementById("m-nv").textContent === "0");
  await page.evaluate(() => window.__brasil.abrir("teste-noticia-recife"));
  await page.waitForSelector('.pop[data-crise="teste-noticia-recife"] .selo.verificada');
  // o popup anterior pode ainda estar sumindo (animação); espera ficar só o novo
  await page.waitForFunction(() => document.querySelectorAll(".pop").length === 1);
  assert.equal(await page.locator(".pop").getByRole("button", { name: "Confirmar" }).count(), 0);
});

test("AC-019.1 campanha: convidar e remover voluntário, editar e encerrar", async () => {
  const page = await entrar("ong", { url: "/brasil/ong" });
  await page.getByRole("link", { name: "Gerenciar" }).first().click();
  await page.waitForSelector("#na-campanha tr");
  await page.selectOption("#f-disp", "");
  await page.locator("#f-dist").fill("3000");
  const convidar = page.locator("#disponiveis").getByRole("button", { name: "Convidar" }).first();
  if (await convidar.count()) {  // a voluntária de teste já está nas 2 campanhas da semente
    await convidar.click();
    await page.waitForSelector("#msg:not([hidden])");
  }
  await page.locator("#na-campanha").getByRole("button", { name: "Remover" }).first().click();
  await page.waitForFunction(() => /removido/.test(document.getElementById("msg").textContent));
  await page.fill('#form-editar input[name="title"]', "Teste campanha editada");
  await page.click('#form-editar button[type="submit"]');
  await page.waitForFunction(() => document.querySelector(".pagina-cabeca h1").textContent === "Teste campanha editada");
  page.once("dialog", (d) => d.accept());
  await page.click("#encerrar");
  await page.waitForSelector(".selo.closed");
});

test("AC-015.1 perfil sem localização salva o resto (sem erro de local)", async () => {
  const page = await entrar("voluntario", { url: "/brasil/perfil" });
  await page.fill('input[name="lat"]', "");
  await page.fill('input[name="lon"]', "");
  await page.fill('input[name="name"]', "Voluntária de Teste");
  await page.click('#form-perfil button[type="submit"]');
  await page.waitForSelector("#msg.ok");
});
