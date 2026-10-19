// Dash Brasil — mapa. Só adapters: cada um desenha a saída da Visão do mapa (visao.js) a cada mudança.
// Crises são marcadores separados (nada é agregado por município). Dois modos de fundo:
//   Municípios: malha IBGE neutra, nome no hover.   Pixels: cada crise acende os pixels em volta, pela severidade.
import { PADRAO, lerFiltros, gravarFiltros, filtrosAtivos, filtrar, numeros, opcoes, ordemDeDesenho,
  raioMarcador, raioKm, acender, celulaEm, nivel } from "./visao.js";
import { el, acao, avisar, data, rotulo, TIPOS, FONTES, SEVERIDADE, VERIFICACAO, atualizarStatusColeta } from "./cliente.js";

const CFG = JSON.parse(document.getElementById("br-config").textContent);
const PAPEL = CFG.papel;
const $ = (id) => document.getElementById(id);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const LADO = 7;  // passo da grade de pixels, em px de tela

let CORES = {};
function lerCores() {
  CORES = {
    sev: [1, 2, 3, 4, 5].map((n) => css(`--sev${n}`)),
    mun: css("--mun"), munTraco: css("--mun-traco"), munFoco: css("--mun-foco"), uf: css("--uf"),
    area: css("--area"), pixel: css("--pixel"), anel: css("--anel"),
  };
}
const corSev = (s) => CORES.sev[nivel(s) - 1];

let estado = lerFiltros(location.search);
let CRISES = [], VISIVEIS = [], INSCRITO = new Set();
let M = null, UF_DE = () => null, NOME_DE = () => "";
let mapa, camadaMun, camadaUf, marcadores, area = null;
const POR_ID = new Map();

// ---------- carregamento (FR-013) ----------
const CONTROLES = ["f-sev", "f-uf", "f-tipo", "f-fonte", "f-verif", "f-q"];
function travar(sim) { for (const id of CONTROLES) $(id).disabled = sim; }

function carregarMalha() {
  if (window.MALHA) return Promise.resolve(window.MALHA);
  return new Promise((ok, erro) => {
    const s = document.createElement("script");
    s.src = CFG.malha + (CFG.malha.includes("?") ? "&" : "?") + "t=" + Date.now();
    s.onload = () => (window.MALHA ? ok(window.MALHA) : erro(new Error("malha")));
    s.onerror = () => erro(new Error("malha"));
    document.head.append(s);
  });
}

async function carregar() {
  travar(true);
  $("falha").hidden = true;
  $("carregando").hidden = false;
  try {
    M = await carregarMalha();
  } catch {
    return falhar("Não foi possível carregar o mapa dos municípios.");
  }
  const [r, insc] = await Promise.all([
    acao("crises"),
    PAPEL === "volunteer" || PAPEL === "org" ? acao("minhas_inscricoes") : Promise.resolve({ ok: true, dados: [] }),
  ]);
  if (!r.ok || !Array.isArray(r.dados)) return falhar("Não foi possível carregar as crises.");
  CRISES = r.dados;
  INSCRITO = new Set((insc.ok && Array.isArray(insc.dados) ? insc.dados : []).map((i) => i.id));
  POR_ID.clear();
  for (const c of CRISES) POR_ID.set(c.id, c);
  if (!mapa) montarMapa();
  preencherControles();
  travar(false);
  $("carregando").hidden = true;
  desenhar({ voar: Boolean(estado.uf) });
  window.__brasil = { mapa, estado: () => ({ ...estado }), visiveis: () => VISIVEIS.map((c) => c.id), abrir: abrirCrise };
  document.body.dataset.pronto = "1";
}

function falhar(texto) {
  $("carregando").hidden = true;
  $("falha-texto").textContent = texto;
  $("falha").hidden = false;
  travar(true);
}
$("tentar").addEventListener("click", carregar);

// ---------- mapa base ----------
function montarMapa() {
  lerCores();
  const props = M.geojson.features.map((f) => f.properties);
  const porMun = new Map(props.map((p) => [p.id, p]));
  UF_DE = (cod) => porMun.get(cod)?.uf || null;
  NOME_DE = (cod) => porMun.get(cod)?.nome || "";

  mapa = L.map("mapa", { zoomSnap: 0.25, minZoom: 3.5, maxZoom: 12, preferCanvas: true, zoomControl: true });
  mapa.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>').addAttribution("IBGE · INPE · CEMADEN · INMET");
  const render = L.canvas({ padding: 0.5, tolerance: 3 });
  mapa.createPane("marcas").style.zIndex = 620;
  mapa.createPane("destaque").style.zIndex = 610;
  const painelPixels = mapa.createPane("pixels");
  painelPixels.style.zIndex = 450;
  painelPixels.style.pointerEvents = "none";
  painelPixels.append(tela);  // dentro do mapa: popups ficam por cima dos pixels

  camadaMun = L.geoJSON(M.geojson, {
    renderer: render,
    style: () => ({ fillColor: CORES.mun, fillOpacity: 1, color: CORES.munTraco, weight: 0.4, opacity: 1 }),
    onEachFeature(f, layer) {
      layer.bindTooltip(`${f.properties.nome} · ${f.properties.uf}`, { sticky: true, direction: "top", offset: [0, -6] });
      layer.on({
        mouseover: () => layer.setStyle({ color: CORES.munFoco, weight: 1.5 }),
        mouseout: () => camadaMun.resetStyle(layer),
      });
    },
  }).addTo(mapa);
  camadaUf = L.geoJSON(M.estados, { renderer: render, interactive: false,
    style: () => ({ fill: false, color: CORES.uf, weight: 0.9, opacity: 0.9 }) }).addTo(mapa);
  const limites = camadaMun.getBounds();
  mapa.fitBounds(limites, { padding: [16, 16] });
  mapa.setMaxBounds(limites.pad(0.35));
  marcadores = L.layerGroup().addTo(mapa);

  mapa.on("popupopen", (e) => mostrarArea(e.popup._criseId));
  mapa.on("popupclose", () => mostrarArea(null));
  mapa.on("moveend zoomend resize", () => estado.modo === "pixels" && desenharPixels());
  mapa.on("mousemove", pairarPixel);
  mapa.on("click", clicarPixel);
  window.addEventListener("resize", () => { mapa.invalidateSize(); if (estado.modo === "pixels") desenharPixels(); });
  document.addEventListener("br:tema", () => {
    lerCores();
    camadaMun.setStyle(() => ({ fillColor: CORES.mun, fillOpacity: 1, color: CORES.munTraco, weight: 0.4, opacity: 1 }));
    camadaUf.setStyle({ color: CORES.uf });
    desenhar({});
  });
}

// ---------- controles e URL (FR-008, FR-011) ----------
function opcao(valor, texto) { return el("option", { value: valor, texto }); }
function preencherControles() {
  const ufs = M.estados.features.map((f) => f.properties.sigla).sort();
  $("f-uf").replaceChildren(opcao("", "Todas as UFs"), ...ufs.map((u) => opcao(u, u)));
  $("f-tipo").replaceChildren(opcao("", "Todos os tipos"), ...opcoes(CRISES, "crisis_type").map(([v, n]) => opcao(v, `${rotulo(TIPOS, v)} (${n})`)));
  $("f-fonte").replaceChildren(opcao("", "Todas as fontes"), ...opcoes(CRISES, "source").map(([v, n]) => opcao(v, `${rotulo(FONTES, v)} (${n})`)));
  // valores que vieram da URL mas não existem nos dados continuam aplicados e visíveis
  for (const [id, k] of [["f-tipo", "tipo"], ["f-fonte", "fonte"]]) {
    if (estado[k] && ![...$(id).options].some((o) => o.value === estado[k])) $(id).append(opcao(estado[k], estado[k]));
  }
  sincronizarControles();
}
function sincronizarControles() {
  $("f-sev").value = estado.sev; $("f-sev-valor").textContent = estado.sev;
  $("f-uf").value = estado.uf; $("f-tipo").value = estado.tipo; $("f-fonte").value = estado.fonte;
  $("f-verif").value = estado.verif;
  if (document.activeElement !== $("f-q")) $("f-q").value = estado.q;
  for (const b of document.querySelectorAll("[data-modo]")) b.setAttribute("aria-pressed", String(b.dataset.modo === estado.modo));
  $("limpar").hidden = filtrosAtivos(estado) === 0;
}
function mudar(parcial, opcoes = {}) {
  estado = { ...estado, ...parcial };
  history.replaceState(null, "", location.pathname + gravarFiltros(estado));
  desenhar(opcoes);
}
const ligar = (id, chave, conv = (v) => v, ev = "change") =>
  $(id).addEventListener(ev, (e) => mudar({ [chave]: conv(e.target.value) }, { voar: chave === "uf" }));
ligar("f-sev", "sev", Number, "input");
ligar("f-uf", "uf");
ligar("f-tipo", "tipo");
ligar("f-fonte", "fonte");
ligar("f-verif", "verif");
let tBusca;
$("f-q").addEventListener("input", (e) => { clearTimeout(tBusca); tBusca = setTimeout(() => mudar({ q: e.target.value }), 150); });
$("limpar").addEventListener("click", () => mudar({ ...PADRAO, modo: estado.modo }, { voar: true }));
for (const b of document.querySelectorAll("[data-modo]")) b.addEventListener("click", () => mudar({ modo: b.dataset.modo }));

// ---------- desenho: tudo sai da Visão do mapa ----------
function desenhar({ voar = false } = {}) {
  if (!mapa) return;
  VISIVEIS = filtrar(CRISES, estado, { ufDe: UF_DE, nomeDe: NOME_DE });
  sincronizarControles();
  const n = numeros(VISIVEIS, UF_DE);
  $("m-crises").textContent = n.crises.toLocaleString("pt-BR");
  $("m-ufs").textContent = n.ufs;
  $("m-criticas").textContent = n.criticas.toLocaleString("pt-BR");
  $("m-nv").textContent = n.naoVerificadas.toLocaleString("pt-BR");
  const pixels = estado.modo === "pixels";
  if (pixels) { mapa.removeLayer(camadaMun); marcadores.clearLayers(); desenharPixels(); }
  else { if (!mapa.hasLayer(camadaMun)) camadaMun.addTo(mapa); camadaUf.bringToFront(); limparPixels(); desenharMarcadores(); }
  if (voar) voarParaUf(estado.uf);
}

function voarParaUf(uf) {
  const alvo = uf ? camadaUf.getLayers().find((l) => l.feature.properties.sigla === uf) : camadaMun;
  if (alvo) mapa.flyToBounds(alvo.getBounds(), { padding: [24, 24], duration: 0.6 });
}

// ---------- marcadores (FR-004) ----------
function desenharMarcadores() {
  mapa.closePopup();
  marcadores.clearLayers();
  for (const c of ordemDeDesenho(VISIVEIS)) {
    const nv = c.verificacao === "nao_verificada";
    L.circleMarker([c.lat, c.lon], {
      pane: "marcas", radius: raioMarcador(c.severity), fillColor: corSev(c.severity), fillOpacity: 0.92,
      color: nv ? css("--acento") : CORES.anel, weight: nv ? 1.5 : 1.2, dashArray: nv ? "3 2" : null,
    }).bindTooltip(c.title, { direction: "top", offset: [0, -4] })
      .on("click", () => abrirCrise(c.id))
      .addTo(marcadores);
  }
}

// ---------- pixels (FR-005) ----------
const tela = $("pixels");
const ctx2d = tela.getContext("2d");
let PIX = { celulas: [], acesas: [], indice: new Map() };

function limparPixels() { ctx2d.clearRect(0, 0, tela.width, tela.height); PIX = { celulas: [], acesas: [], indice: new Map() }; }

// Recorta a grade ao Brasil desenhando as UFs num canvas fora da tela e lendo onde há tinta.
function celulasNoBrasil(w, h) {
  const off = document.createElement("canvas");
  off.width = w; off.height = h;
  const o = off.getContext("2d");
  o.fillStyle = "#000";
  for (const f of M.estados.features) {
    const g = f.geometry;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
    o.beginPath();
    for (const pl of polys) for (const anel of pl) {
      anel.forEach(([lon, lat], i) => {
        const p = mapa.latLngToContainerPoint([lat, lon]);
        i ? o.lineTo(p.x, p.y) : o.moveTo(p.x, p.y);
      });
      o.closePath();
    }
    o.fill("evenodd");
  }
  const img = o.getImageData(0, 0, w, h).data;
  const celulas = [];
  for (let y = LADO / 2; y < h; y += LADO) {
    for (let x = LADO / 2; x < w; x += LADO) {
      if (img[(Math.floor(y) * w + Math.floor(x)) * 4 + 3] > 0) celulas.push({ x, y });
    }
  }
  return celulas;
}

function kmPorPx() {
  const c = mapa.getSize().divideBy(2);
  const a = mapa.containerPointToLatLng(c), b = mapa.containerPointToLatLng(c.add([100, 0]));
  return a.distanceTo(b) / 1000 / 100;
}

function desenharPixels() {
  const t = mapa.getSize();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  tela.width = Math.round(t.x * dpr); tela.height = Math.round(t.y * dpr);
  tela.style.width = t.x + "px"; tela.style.height = t.y + "px";
  L.DomUtil.setPosition(tela, mapa.containerPointToLayerPoint([0, 0]));
  ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx2d.clearRect(0, 0, t.x, t.y);
  const celulas = celulasNoBrasil(t.x, t.y);
  const escala = kmPorPx();
  const focos = VISIVEIS.map((c) => {
    const p = mapa.latLngToContainerPoint([c.lat, c.lon]);
    return { id: c.id, sev: c.severity, x: p.x, y: p.y, r: raioKm(c.severity) / escala };
  });
  const acesas = acender(celulas, focos, LADO);
  const indice = new Map();
  celulas.forEach((c, i) => indice.set(celulaEm(c.x, c.y, LADO), i));
  PIX = { celulas, acesas, indice };
  for (let i = 0; i < celulas.length; i++) {
    const c = celulas[i], a = acesas[i];
    const tam = a ? LADO * (0.45 + 0.5 * a.k) : LADO * 0.32;
    ctx2d.fillStyle = a ? corSev(a.sev) : CORES.pixel;
    ctx2d.globalAlpha = a ? 0.55 + 0.45 * a.k : 1;
    ctx2d.fillRect(c.x - tam / 2, c.y - tam / 2, tam, tam);
  }
  ctx2d.globalAlpha = 1;
}

function criseNoPixel(e) {
  if (estado.modo !== "pixels" || !PIX.celulas.length) return null;
  const i = PIX.indice.get(celulaEm(e.containerPoint.x, e.containerPoint.y, LADO));
  return i === undefined ? null : PIX.acesas[i];
}
function pairarPixel(e) {
  const a = criseNoPixel(e);
  mapa.getContainer().style.cursor = a ? "pointer" : "";
  if (a) mapa.getContainer().title = POR_ID.get(a.id)?.title || "";
  else mapa.getContainer().removeAttribute("title");
}
function clicarPixel(e) {
  const a = criseNoPixel(e);
  if (a) abrirCrise(a.id);
}

// ---------- popup (FR-006) e área (FR-007) ----------
function mostrarArea(id) {
  if (area) { mapa.removeLayer(area); area = null; }
  const c = id && POR_ID.get(id);
  const cods = new Set((c?.municipios_afetados || []).map(Number));
  if (!c || cods.size < 2) return;
  const feats = M.geojson.features.filter((f) => cods.has(f.properties.id));
  area = L.geoJSON({ type: "FeatureCollection", features: feats }, {
    pane: "destaque", interactive: false,
    style: { color: CORES.area, weight: 1.6, fillColor: CORES.area, fillOpacity: 0.18 },
  }).addTo(mapa);
}

function abrirCrise(id) {
  const c = POR_ID.get(id);
  if (!c) return;
  const pop = L.popup({ maxWidth: 320, autoPanPaddingTopLeft: [24, 70], autoPanPaddingBottomRight: [24, 24] }).setLatLng([c.lat, c.lon]).setContent(conteudo(c));
  pop._criseId = id;
  pop.openOn(mapa);
}

function conteudo(c) {
  const nv = c.verificacao === "nao_verificada";
  const mun = NOME_DE(Number(c.municipio_ibge));
  const msg = el("p", { class: "aviso", role: "status", hidden: true });
  const caixa = el("div", { class: "pop", "data-crise": c.id }, [
    el("div", { class: "pop-topo" }, [
      el("span", { class: `sev s${nivel(c.severity)}`, style: `background:${corSev(c.severity)}`, texto: String(nivel(c.severity)) }),
      el("span", { class: "pop-titulo", texto: c.title }),
    ]),
    el("div", { class: "pop-meta" }, [
      el("span", { texto: rotulo(TIPOS, c.crisis_type) }),
      el("span", { texto: rotulo(FONTES, c.source) }),
      el("span", { texto: `${SEVERIDADE[nivel(c.severity)]}` }),
      mun ? el("span", { texto: `${mun} · ${c.uf || ""}` }) : null,
      (c.municipios_afetados || []).length > 1 ? el("span", { texto: `${c.municipios_afetados.length} municípios` }) : null,
      el("span", { texto: data(c.visto_em || c.updated_at || c.created_at) }),
    ]),
    el("div", {}, [
      el("span", { class: nv ? "selo selo-nv" : "selo verificada", texto: rotulo(VERIFICACAO, c.verificacao || "verificada") }),
      c.link_fonte ? el("a", { class: "item-meta", href: c.link_fonte, target: "_blank", rel: "noopener", texto: " fonte ↗" }) : null,
    ]),
    el("div", { class: "pop-assoc" }, [
      el("span", {}, [el("b", { "data-n": "voluntarios", texto: String(c.voluntarios ?? 0) }), "voluntários"]),
      el("span", {}, [el("b", { "data-n": "ongs", texto: String(c.ongs ?? 0) }), "ONGs"]),
    ]),
    acoes(c, msg),
    msg,
  ]);
  return caixa;
}

function acoes(c, msg) {
  const box = el("div", { class: "acoes" });
  if (PAPEL === "volunteer" || PAPEL === "org") {
    const botao = el("button", { type: "button", class: "botao botao-pequeno" });
    const pintar = () => {
      const dentro = INSCRITO.has(c.id);
      botao.className = `botao botao-pequeno ${dentro ? "botao-neutro" : "botao-primario"}`;
      botao.textContent = dentro ? "Cancelar inscrição" : (PAPEL === "org" ? "Apoiar crise" : "Inscrever-se");
    };
    botao.addEventListener("click", async () => {
      botao.disabled = true;
      const r = await acao(INSCRITO.has(c.id) ? "cancelar" : "inscrever", { p: { crisis_id: c.id } });
      botao.disabled = false;
      if (!r.ok) return avisar(msg, r.erro);
      INSCRITO.has(c.id) ? INSCRITO.delete(c.id) : INSCRITO.add(c.id);
      c.voluntarios = r.dados.voluntarios; c.ongs = r.dados.ongs;
      const pop = botao.closest(".pop");
      pop.querySelector('[data-n="voluntarios"]').textContent = c.voluntarios;
      pop.querySelector('[data-n="ongs"]').textContent = c.ongs;
      avisar(msg, "");
      pintar();
    });
    pintar();
    box.append(botao);
  }
  if (PAPEL === "org") {
    box.append(el("a", { class: "botao botao-secundario botao-pequeno", href: `${CFG.nova_campanha}?crise=${encodeURIComponent(c.id)}`, texto: "Criar campanha" }));
  }
  if (PAPEL === "admin" && c.verificacao === "nao_verificada") {
    for (const [acaoNome, texto, cls] of [["confirmar", "Confirmar", "botao-primario"], ["descartar", "Descartar", "botao-neutro"]]) {
      box.append(el("button", { type: "button", class: `botao botao-pequeno ${cls}`, texto, onclick: async () => {
        const r = await acao("verificar", { p: { crisis_id: c.id }, corpo: { acao: acaoNome } });
        if (!r.ok) return avisar(msg, r.erro);
        if (acaoNome === "descartar") { CRISES = CRISES.filter((x) => x.id !== c.id); POR_ID.delete(c.id); }
        else c.verificacao = "verificada";
        mapa.closePopup();
        desenhar();
      } }));
    }
  }
  return box;
}

// ---------- admin: atualizar dados pela barra lateral ----------
$("atualizar")?.addEventListener("click", async (e) => {
  const b = e.currentTarget, msg = $("atualizar-msg");
  b.disabled = true;
  avisar(msg, "Coletando… pode levar até 2 minutos.", true);
  const r = await acao("atualizar_dados");
  b.disabled = false;
  avisar(msg, r.ok ? `Pronto: ${r.dados.gravadas} crises gravadas em ${r.dados.segundos}s.` : r.erro, r.ok);
  if (r.ok) { atualizarStatusColeta(); carregar(); }
});

carregar();
