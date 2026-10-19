// Seam 1: regras do mapa sem navegador (node --test frontend/brasil/tests/visao.test.mjs).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  PADRAO, lerFiltros, gravarFiltros, filtrosAtivos, filtrar, numeros, ufsDaCrise, acender, raioKm, ordemDeDesenho, opcoes,
  grupoDe, GRUPOS,
} from "../static/visao.js";

const UF = { 4205407: "SC", 4321501: "RS", 4314902: "RS", 3304557: "RJ" };
const NOME = { 4205407: "Florianópolis", 4321501: "Torres", 4314902: "Porto Alegre", 3304557: "Rio de Janeiro" };
const ctx = { ufDe: (c) => UF[c] || null, nomeDe: (c) => NOME[c] || "" };

const AVISO = { id: "inmet-1", title: "Chuvas intensas", severity: 3, uf: "SC", municipio_ibge: 4205407,
  municipios_afetados: [4205407, 4321501], crisis_type: "meteorological", source: "inmet", verificacao: "verificada" };
const QUEIMADA = { id: "inpe-1", title: "Focos de calor", severity: 2, uf: "RS", municipio_ibge: 4314902,
  municipios_afetados: [4314902], crisis_type: "wildfire", source: "inpe", verificacao: "verificada" };
const NOTICIA = { id: "news-1", title: "Deslizamento em Petrópolis", severity: 5, uf: "RJ", municipio_ibge: 3304557,
  municipios_afetados: [3304557], crisis_type: "geological", source: "noticias", verificacao: "nao_verificada" };
const TODAS = [AVISO, QUEIMADA, NOTICIA];
const ids = (l) => l.map((c) => c.id).sort();

test("AC-008.1 severidade mínima filtra tudo de uma vez", () => {
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, sev: 4 }, ctx)), ["news-1"]);
  assert.deepEqual(ids(filtrar(TODAS, PADRAO, ctx)), ["inmet-1", "inpe-1", "news-1"]);  // padrão 1: nada escondido
});

test("AC-009.1 UF pela área: aviso centrado em SC aparece no RS", () => {
  assert.deepEqual([...ufsDaCrise(AVISO, ctx.ufDe)].sort(), ["RS", "SC"]);
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, uf: "RS" }, ctx)), ["inmet-1", "inpe-1"]);
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, uf: "SC" }, ctx)), ["inmet-1"]);
});

test("AC-008.2 busca por título ou município, sem acento", () => {
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, q: "porto alegre" }, ctx)), ["inpe-1"]);
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, q: "PETROPOLIS" }, ctx)), ["news-1"]);
});

test("tipo, fonte e verificação", () => {
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, tipo: "wildfire" }, ctx)), ["inpe-1"]);
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, fonte: "inmet" }, ctx)), ["inmet-1"]);
  assert.deepEqual(ids(filtrar(TODAS, { ...PADRAO, verif: "nao_verificada" }, ctx)), ["news-1"]);
});

test("AC-010.1 números refletem os filtros", () => {
  assert.deepEqual(numeros(filtrar(TODAS, PADRAO, ctx), ctx.ufDe), { crises: 3, ufs: 3, criticas: 1, naoVerificadas: 1 });
  assert.deepEqual(numeros(filtrar(TODAS, { ...PADRAO, uf: "RS" }, ctx), ctx.ufDe), { crises: 2, ufs: 2, criticas: 0, naoVerificadas: 0 });
  assert.deepEqual(numeros([], ctx.ufDe), { crises: 0, ufs: 0, criticas: 0, naoVerificadas: 0 });
});

test("AC-011.1 filtros vão e voltam da URL; padrão não aparece", () => {
  const f = { ...PADRAO, uf: "RS", tipo: "wildfire", modo: "pixels" };
  const url = gravarFiltros(f);
  assert.equal(url, "?uf=RS&tipo=wildfire&modo=pixels");
  assert.deepEqual(lerFiltros(url), f);
  assert.equal(gravarFiltros(PADRAO), "");
  assert.equal(lerFiltros("?sev=9&modo=xyz&uf=rs").sev, 5);
  assert.equal(lerFiltros("?modo=xyz").modo, "municipios");
  assert.equal(lerFiltros("?uf=rs").uf, "RS");
  assert.equal(filtrosAtivos(f), 2);
});

test("AC-004.1 crises na mesma coordenada continuam separadas; a mais grave por cima", () => {
  const a = { id: "a", severity: 5, lat: -30, lon: -51 }, b = { id: "b", severity: 2, lat: -30, lon: -51 };
  assert.deepEqual(ordemDeDesenho([a, b]).map((c) => c.id), ["b", "a"]);
});

test("AC-005.1 pixels: mais grave acende mais e domina a célula", () => {
  const lado = 7, cols = 60, lins = 30;
  const grade = { cols, lins, lado, dentro: new Uint8Array(cols * lins).fill(1) };
  const escala = 0.3;  // px por km
  const focos = [{ sev: 5, x: 100, y: 100, r: raioKm(5) * escala }, { sev: 1, x: 330, y: 100, r: raioKm(1) * escala }];
  const { foco } = acender(grade, focos);
  const acesas = (f) => foco.filter((x) => x === f).length;
  assert.ok(acesas(0) > acesas(1) && acesas(1) > 0);
  assert.equal(foco[Math.floor(100 / lado) * cols + Math.floor(100 / lado)], 0);
  // sobreposição: a de severidade maior vence mesmo mais longe
  const um = { cols: 1, lins: 1, lado: 100, dentro: new Uint8Array([1]) };
  assert.equal(acender(um, [{ sev: 5, x: 80, y: 50, r: 60 }, { sev: 2, x: 52, y: 50, r: 60 }]).foco[0], 0);
  // fora do Brasil não acende
  assert.equal(acender({ ...um, dentro: new Uint8Array([0]) }, [{ sev: 5, x: 50, y: 50, r: 60 }]).foco[0], -1);
  // foco fora da tela não estoura a grade
  assert.doesNotThrow(() => acender(grade, [{ sev: 5, x: -5000, y: 99999, r: 300 }]));
});

test("cor por tipo: grupos fixos, tipos desconhecidos em outros", () => {
  assert.deepEqual(GRUPOS, ["meteorologico", "queimada", "hidrologico", "seca", "geologico", "outros"]);
  assert.equal(grupoDe("wildfire"), "queimada");
  assert.equal(grupoDe("seismic"), "geologico");
  assert.equal(grupoDe("conflict"), "outros");
});

test("opções contam crises por valor", () => {
  assert.deepEqual(opcoes(TODAS, "source"), [["inmet", 1], ["inpe", 1], ["noticias", 1]]);
});

test("filtro 'onde falta gente' mostra só as lacunas e vai para a URL", () => {
  const f = { ...PADRAO, falta: "1" };
  assert.deepEqual(ids(filtrar(TODAS, f, { ...ctx, lacunas: new Set(["inpe-1"]) })), ["inpe-1"]);
  assert.deepEqual(ids(filtrar(TODAS, f, ctx)).length, 3);  // sem lacunas carregadas não esconde nada
  assert.equal(gravarFiltros(f), "?falta=1");
  assert.equal(lerFiltros("?falta=1").falta, "1");
  assert.equal(filtrosAtivos(f), 1);
});
