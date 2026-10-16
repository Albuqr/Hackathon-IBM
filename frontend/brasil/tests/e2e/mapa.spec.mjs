// E2E do Dash Brasil no navegador (AC-006.1, AC-007.1, AC-008.1, AC-009.1, NFR-001, NFR-008).
// Pré-requisito: API + frontend rodando com BRASIL_DEV_LOGIN=1 e o banco semeado por
// `python -m middleware.brasil.semear_teste`. Usa Leaflet e fontes da CDN (precisa de rede).
// Rodar: BASE_URL=http://localhost:5000 node --test frontend/brasil/tests/e2e/mapa.spec.mjs
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const BASE = process.env.BASE_URL || "http://localhost:5000";
let browser;

before(async () => { browser = await chromium.launch(); });
after(async () => { await browser?.close(); });

async function abrirMapa(viewport = { width: 1440, height: 900 }) {
  const page = await (await browser.newContext({ viewport })).newPage();
  const t0 = Date.now();
  await page.goto(`${BASE}/brasil/dev-login/voluntario`);
  await page.waitForFunction(() => window.__brasilPronto === true, null, { timeout: 30000 });
  return { page, ms: Date.now() - t0 };
}

const corDoMunicipio = (page, id) => page.evaluate((id) => {
  let cor = null;
  for (const l of Object.values(window.__brasilMapa._layers)) if (l.feature?.properties.id === id) cor = l.options.fillColor;
  return cor;
}, id);
const cssVar = (page, v) => page.evaluate((v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim(), v);

test("AC-006.1 Porto Alegre com crises sev 2 e 4 fica na cor da severidade 4 · NFR-001 mapa pronto em ≤ 3 s", async () => {
  const { page, ms } = await abrirMapa();
  assert.ok(ms <= 3000, `mapa levou ${ms} ms`);
  assert.equal(await corDoMunicipio(page, 4314902), await cssVar(page, "--s5")); // sev 4 → s5
});

test("AC-007.1 trocar para Voluntários repinta o mapa e muda a legenda", async () => {
  const { page } = await abrirMapa();
  await page.click('#ctl-indicador button[data-v="voluntarios"]');
  assert.match(await page.locator(".legenda-titulo").textContent(), /Voluntários disponíveis/);
  assert.notEqual(await corDoMunicipio(page, 4314902), await cssVar(page, "--papel")); // voluntária de teste mora em POA
  assert.equal(await corDoMunicipio(page, 1500602), await cssVar(page, "--papel"));    // Altamira sem voluntários
});

test("AC-008.1 filtro UF = RS e tipo = meteorológico deixa só os pontos do RS desse tipo", async () => {
  const { page } = await abrirMapa();
  await page.selectOption("#f-uf", "RS");
  await page.selectOption("#f-tipo", "meteorological");
  const titulos = await page.evaluate(() => Object.values(window.__brasilMapa._layers)
    .filter((l) => l.getTooltip && l.options.radius).map((l) => l.getTooltip().getContent()));
  assert.ok(titulos.length >= 2);
  assert.ok(titulos.every((t) => /POA sev 2|Caxias/.test(t)), titulos.join(" | "));
});

test("AC-009.1 Quero ajudar inscreve e Cancelar inscrição desfaz, pela interface", async () => {
  const { page } = await abrirMapa();
  await page.fill("#busca", "Caxias do Sul");
  await page.waitForFunction(() => document.querySelector("#ranking .rk-nome")?.textContent.startsWith("Caxias do Sul"));
  await page.locator("#ranking button").first().click();
  const botao = page.locator(".lista-crises button").first();
  if ((await botao.textContent()) === "Cancelar inscrição") { await botao.click(); await page.waitForTimeout(300); }
  await page.locator(".lista-crises button").first().click();
  await page.waitForFunction(() => document.querySelector(".lista-crises button")?.textContent === "Cancelar inscrição");
  assert.match(await page.locator(".lista-crises .crise-meta").first().textContent(), /1 inscritos/);
  await page.locator(".lista-crises button").first().click();
  await page.waitForFunction(() => document.querySelector(".lista-crises button")?.textContent === "Quero ajudar");
});

test("NFR-008 sem rolagem horizontal em 390 px", async () => {
  const { page } = await abrirMapa({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
});

test("AC-012.1 AC-013.1 AC-011.1 ONG cria campanha pelo mapa, convida e o voluntário aceita", async () => {
  const ctxVol = await browser.newContext();
  const vol = await ctxVol.newPage();
  await vol.goto(`${BASE}/brasil/dev-login/voluntario`); // garante que a voluntária de teste existe

  const ong = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ong.goto(`${BASE}/brasil/dev-login/ong`);
  await ong.waitForFunction(() => window.__brasilPronto === true);
  await ong.fill("#busca", "Caxias do Sul");
  await ong.waitForFunction(() => document.querySelector("#ranking .rk-nome")?.textContent.startsWith("Caxias do Sul"));
  await ong.locator("#ranking button").first().click();
  await ong.locator(".lista-crises a.crise-link").first().click();
  await ong.waitForURL(/\/brasil\/ong\?crise=/);
  assert.equal(await ong.locator('select[name="crisis_id"]').inputValue(), "teste-caxias");
  const titulo = `Campanha E2E ${Date.now()}`;
  await ong.fill('input[name="title"]', titulo);
  await ong.fill('input[name="target_volunteers"]', "10");
  await ong.click('#form-campanha button[type="submit"]');
  await ong.waitForURL(/\/brasil\/ong\/campanhas\/\d+$/);
  await ong.locator('button[data-acao="POST"]').first().click();
  await ong.waitForSelector('button[data-acao="DELETE"]');

  await vol.goto(`${BASE}/brasil/campanhas`);
  const item = vol.locator(".lista-crises li", { hasText: titulo });
  await Promise.all([vol.waitForEvent("load"), item.locator('button[data-status="confirmed"]').click()]);
  assert.match(await vol.locator(".lista-crises li", { hasText: titulo }).locator(".status").textContent(), /confirmado/);

  await ong.reload();
  assert.match(await ong.locator(".lista-crises .status").first().textContent(), /confirmado/);
});
