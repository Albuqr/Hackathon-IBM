// Dash Brasil — mapa. Só adapters: cada um desenha a saída da Visão do mapa (visao.js) a cada mudança.
// Crises são marcadores separados (nada é agregado por município). Dois modos de fundo:
//   Municípios: malha IBGE neutra, nome no hover.   Pixels: cada crise acende os pixels em volta, pela severidade.
import { PADRAO, lerFiltros, gravarFiltros, filtrosAtivos, filtrar, numeros, opcoes, ordemDeDesenho,
  raioMarcador, raioKm, acender, nivel, grupoDe, GRUPOS } from "./visao.js";
import { el, acao, avisar, data, rotulo, textoSeguro, linkSeguro, TIPOS, FONTES, SEVERIDADE, VERIFICACAO, atualizarStatusColeta } from "./cliente.js";

const CFG = JSON.parse(document.getElementById("br-config").textContent);
const PAPEL = CFG.papel;
const $ = (id) => document.getElementById(id);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const LADO = 7;  // passo da grade de pixels, em px de tela
// ONG escolhendo a crise da nova campanha: o popup troca a ação por "Usar esta crise"
const ESCOLHER = PAPEL === "org" && new URLSearchParams(location.search).get("escolher") === "1";

let CORES = {};
function lerCores() {
  CORES = {
    sev: [1, 2, 3, 4, 5].map((n) => css(`--sev${n}`)),
    mun: css("--mun"), munTraco: css("--mun-traco"), munFoco: css("--mun-foco"), uf: css("--uf"),
    area: css("--area"), pixel: css("--pixel"), anel: css("--anel"),
    tipo: Object.fromEntries(GRUPOS.map((g) => [g, css(`--tipo-${g}`)])),
  };
}
const corSev = (s) => CORES.sev[nivel(s) - 1];
const corTipo = (tipo) => CORES.tipo[grupoDe(tipo)];

let estado = lerFiltros(location.search);
// o modo também fica lembrado fora da URL (FR-002): o link "Mapa" do cabeçalho não leva a query
try { if (!new URLSearchParams(location.search).has("modo") && localStorage.getItem("br-modo") === "pixels") estado.modo = "pixels"; } catch { /* sem armazenamento */ }
let CRISES = [], VISIVEIS = [], INSCRITO = new Set();
let LACUNAS = null;            // ids das crises onde falta gente (só a ONG usa)
const MINHAS = new Map();      // crise → campanha ativa da ONG
let M = null, UF_DE = () => null, NOME_DE = () => "";
let mapa, camadaMun, camadaUf, marcadores, area = null;
const POR_ID = new Map();

// ---------- carregamento (FR-013) ----------
const CONTROLES = ["f-sev", "f-uf", "f-tipo", "f-fonte", "f-verif", "f-q"];
function travar(sim) {
  for (const id of CONTROLES) $(id).disabled = sim;
  for (const b of document.querySelectorAll("[data-falta]")) b.disabled = sim;
}

async function carregarLacunas() {
  if (LACUNAS || PAPEL !== "org") return;
  const r = await acao("distribuicao");
  LACUNAS = new Set(r.ok ? r.dados.lacunas.map((l) => l.crisis_id) : []);
  $("m-falta") && ($("m-falta").textContent = LACUNAS.size.toLocaleString("pt-BR"));
}

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
  const [r, insc, minhas] = await Promise.all([
    acao("crises"),
    PAPEL === "volunteer" || PAPEL === "org" ? acao("minhas_inscricoes") : Promise.resolve({ ok: true, dados: [] }),
    PAPEL === "org" ? acao("campanhas_ong") : Promise.resolve({ ok: true, dados: [] }),
    carregarLacunas(),
  ]);
  MINHAS.clear();
  for (const cam of minhas.ok && Array.isArray(minhas.dados) ? minhas.dados : []) if (cam.status === "active") MINHAS.set(cam.crisis_id, cam);
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
  // ganchos para o E2E: o que está desenhado, sem olhar dentro do Leaflet
  window.__brasil = { mapa, estado: () => ({ ...estado }), visiveis: () => VISIVEIS.map((c) => c.id), abrir: abrirCrise,
    marcadores: () => marcadores.getLayers().map((l) => l.options.criseId),
    area: () => (area ? area.getLayers().length : 0),
    pixelsAcesos: () => (PIX ? PIX.foco.filter((f) => f >= 0).length : 0) };
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
      layer.bindTooltip(textoSeguro(`${f.properties.nome} · ${f.properties.uf}`), { sticky: true, direction: "top", offset: [0, -6] });
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
  mapa.on("zoomstart", () => { if (estado.modo === "pixels") tela.style.visibility = "hidden"; });
  mapa.on("moveend resize", pedirPixels);
  mapa.on("mousemove", pairarPixel);
  mapa.on("click", clicarPixel);
  window.addEventListener("resize", () => { mapa.invalidateSize(); pedirPixels(); });
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
  for (const b of document.querySelectorAll("[data-falta]")) b.setAttribute("aria-pressed", String(b.dataset.falta === estado.falta));
  $("limpar").hidden = filtrosAtivos(estado) === 0;
}
function mudar(parcial, opcoes = {}) {
  estado = { ...estado, ...parcial };
  try { localStorage.setItem("br-modo", estado.modo); } catch { /* sem armazenamento */ }
  const busca = gravarFiltros(estado);
  history.replaceState(null, "", location.pathname + busca + (ESCOLHER ? (busca ? "&" : "?") + "escolher=1" : ""));
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
for (const b of document.querySelectorAll("[data-falta]")) b.addEventListener("click", async () => { await carregarLacunas(); mudar({ falta: b.dataset.falta }); });

// ---------- desenho: tudo sai da Visão do mapa ----------
function desenhar({ voar = false } = {}) {
  if (!mapa) return;
  VISIVEIS = filtrar(CRISES, estado, { ufDe: UF_DE, nomeDe: NOME_DE, lacunas: PAPEL === "org" ? LACUNAS : null });
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
    const nv = c.verificacao === "nao_verificada", minha = MINHAS.has(c.id);
    L.circleMarker([c.lat, c.lon], {
      pane: "marcas", radius: raioMarcador(c.severity), fillColor: corTipo(c.crisis_type), fillOpacity: 0.9,
      color: minha ? css("--verde") : nv ? css("--acento") : CORES.anel, weight: minha ? 3 : nv ? 1.5 : 1.2,
      dashArray: nv && !minha ? "3 2" : null, criseId: c.id,
    }).bindTooltip(textoSeguro(c.title), { direction: "top", offset: [0, -4] })
      .on("click", () => abrirCrise(c.id))
      .addTo(marcadores);
  }
}

// ---------- pixels (FR-005) ----------
// Desempenho: a forma do Brasil vira uma máscara lat/lon calculada uma vez; cada redesenho só lê a máscara
// (lon por coluna e lat por linha, porque na projeção do mapa elas são independentes), acende as células
// perto das crises visíveis na tela e pinta tudo em poucos caminhos por cor.
const tela = $("pixels");
const ctx2d = tela.getContext("2d");
let PIX = null;          // { grade, foco, k, focos }
let MASCARA = null;      // { w, h, lon0, lat1, passo, dados }

function montarMascara() {
  const passo = 0.04;  // graus (~4 km)
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const aneis = [];
  for (const f of M.estados.features) {
    const g = f.geometry;
    for (const pl of g.type === "Polygon" ? [g.coordinates] : g.coordinates) for (const anel of pl) {
      aneis.push(anel);
      for (const [lon, lat] of anel) { x0 = Math.min(x0, lon); x1 = Math.max(x1, lon); y0 = Math.min(y0, lat); y1 = Math.max(y1, lat); }
    }
  }
  const w = Math.ceil((x1 - x0) / passo) + 1, h = Math.ceil((y1 - y0) / passo) + 1;
  const off = document.createElement("canvas");
  off.width = w; off.height = h;
  const o = off.getContext("2d");
  o.beginPath();
  for (const anel of aneis) anel.forEach(([lon, lat], i) => {
    const x = (lon - x0) / passo, y = (y1 - lat) / passo;
    i ? o.lineTo(x, y) : o.moveTo(x, y);
  });
  o.fill("evenodd");
  const img = o.getImageData(0, 0, w, h).data;
  const dados = new Uint8Array(w * h);
  for (let p = 0; p < w * h; p++) dados[p] = img[p * 4 + 3] > 0 ? 1 : 0;
  MASCARA = { w, h, lon0: x0, lat1: y1, passo, dados };
}

function limparPixels() { ctx2d.clearRect(0, 0, tela.width, tela.height); PIX = null; }

function gradeNaTela(t) {
  if (!MASCARA) montarMascara();
  const cols = Math.ceil(t.x / LADO), lins = Math.ceil(t.y / LADO);
  const colX = new Int32Array(cols), linY = new Int32Array(lins);
  for (let i = 0; i < cols; i++) colX[i] = Math.floor((mapa.containerPointToLatLng([i * LADO + LADO / 2, 0]).lng - MASCARA.lon0) / MASCARA.passo);
  for (let j = 0; j < lins; j++) linY[j] = Math.floor((MASCARA.lat1 - mapa.containerPointToLatLng([0, j * LADO + LADO / 2]).lat) / MASCARA.passo);
  const dentro = new Uint8Array(cols * lins);
  for (let j = 0; j < lins; j++) {
    const y = linY[j];
    if (y < 0 || y >= MASCARA.h) continue;
    for (let i = 0; i < cols; i++) {
      const x = colX[i];
      if (x >= 0 && x < MASCARA.w) dentro[j * cols + i] = MASCARA.dados[y * MASCARA.w + x];
    }
  }
  return { cols, lins, lado: LADO, dentro };
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
  const grade = gradeNaTela(t);
  const escala = kmPorPx();
  const focos = [];
  for (const c of VISIVEIS) {
    // alcance em km, mas limitado em px: com zoom alto as crises continuam separadas em vez de inundar a tela
    const p = mapa.latLngToContainerPoint([c.lat, c.lon]);
    const r = Math.min(raioKm(c.severity) / escala, LADO * (2.5 + 1.5 * nivel(c.severity)));
    if (p.x + r < 0 || p.y + r < 0 || p.x - r > t.x || p.y - r > t.y) continue;  // fora da tela
    focos.push({ id: c.id, sev: c.severity, grupo: grupoDe(c.crisis_type), x: p.x, y: p.y, r });
  }
  const { foco, k } = acender(grade, focos);
  PIX = { grade, foco, k, focos };
  // um caminho para as células apagadas e um por (tipo, faixa de intensidade) para as acesas
  const caminhos = new Map();
  const apagadas = new Path2D();
  const { cols, lins } = grade, base = LADO * 0.3;
  for (let j = 0; j < lins; j++) for (let i = 0; i < cols; i++) {
    const idx = j * cols + i;
    if (!grade.dentro[idx]) continue;
    const cx = i * LADO + LADO / 2, cy = j * LADO + LADO / 2;
    const f = foco[idx];
    if (f < 0) { apagadas.rect(cx - base / 2, cy - base / 2, base, base); continue; }
    const faixa = Math.min(3, Math.floor(k[idx] * 4));          // 0–3
    const chave = focos[f].grupo + faixa;
    let c = caminhos.get(chave);
    if (!c) caminhos.set(chave, (c = { grupo: focos[f].grupo, faixa, p: new Path2D() }));
    const tam = LADO * (0.62 + 0.11 * faixa);                    // acesas quase cheias: o mapa ganha cor
    c.p.rect(cx - tam / 2, cy - tam / 2, tam, tam);
  }
  ctx2d.fillStyle = CORES.pixel;
  ctx2d.fill(apagadas);
  for (const c of caminhos.values()) {
    ctx2d.globalAlpha = 0.55 + 0.15 * c.faixa;
    ctx2d.fillStyle = CORES.tipo[c.grupo];
    ctx2d.fill(c.p);
  }
  ctx2d.globalAlpha = 1;
  tela.style.visibility = "";
}

// Redesenho em no máximo um quadro; durante o zoom animado os pixels somem (não escalam com o mapa).
let pedido = 0;
function pedirPixels() {
  if (estado.modo !== "pixels" || pedido) return;
  pedido = requestAnimationFrame(() => { pedido = 0; desenharPixels(); });
}

function criseNoPixel(e) {
  if (estado.modo !== "pixels" || !PIX) return null;
  const { cols, lins, lado } = PIX.grade;
  const i = Math.floor(e.containerPoint.x / lado), j = Math.floor(e.containerPoint.y / lado);
  if (i < 0 || j < 0 || i >= cols || j >= lins) return null;
  const f = PIX.foco[j * cols + i];
  return f < 0 ? null : PIX.focos[f];
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

// ---------- popup da ONG: quem já está lá, o plano do assistente e a campanha ----------
const URG = { baixa: "baixa", "média": "média", alta: "alta", "crítica": "crítica" };
function acoesOng(c, box) {
  const ir = (href, texto) => el("a", { class: "botao botao-primario", href, texto });
  const minha = MINHAS.get(c.id);
  if (ESCOLHER) box.append(ir(`${CFG.nova_campanha}?crise=${encodeURIComponent(c.id)}`, "Usar esta crise"));
  else if (minha) box.append(ir(`${CFG.campanha}${minha.id}`, "Abrir minha campanha"));
  else box.append(ir(`${CFG.nova_campanha}?crise=${encodeURIComponent(c.id)}`, "Criar campanha aqui"));
  acao("plano", { p: { crisis_id: c.id } }).then((r) => {
    const pop = box.closest(".pop");
    if (!pop) return;
    const n = pop.querySelector('[data-n="campanhas"]'), linha = pop.querySelector("[data-plano]");
    if (!r.ok) { if (linha) linha.hidden = true; return; }
    if (n) n.textContent = String(r.dados.campanhas_ativas);
    if (!linha) return;
    if (r.dados.minha_campanha) {
      linha.replaceChildren("Você já tem a campanha ", el("b", { texto: r.dados.minha_campanha.title }), " aqui.");
      if (!minha) {
        MINHAS.set(c.id, r.dados.minha_campanha);
        box.firstChild.replaceWith(ir(`${CFG.campanha}${r.dados.minha_campanha.id}`, "Abrir minha campanha"));
      }
      return;
    }
    linha.replaceChildren(el("span", { class: "sugestao", style: "margin:0", texto: "recomendação do assistente" }), el("br"),
      `${r.dados.voluntarios} voluntários · ${r.dados.habilidades.join(", ")} · urgência ${URG[r.dados.urgencia] || r.dados.urgencia}`);
  });
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
      el("span", {}, [el("i", { class: "ponto-tipo", style: `background:${corTipo(c.crisis_type)}` }), rotulo(TIPOS, c.crisis_type)]),
      el("span", { texto: rotulo(FONTES, c.source) }),
      el("span", { texto: `${SEVERIDADE[nivel(c.severity)]}` }),
      mun ? el("span", { texto: `${mun} · ${c.uf || ""}` }) : null,
      (c.municipios_afetados || []).length > 1 ? el("span", { texto: `${c.municipios_afetados.length} municípios` }) : null,
      el("span", { texto: data(c.visto_em || c.updated_at || c.created_at) }),
    ]),
    el("div", {}, [
      el("span", { class: nv ? "selo selo-nv" : "selo verificada", texto: rotulo(VERIFICACAO, c.verificacao || "verificada") }),
      linkSeguro(c.link_fonte) ? el("a", { class: "item-meta", href: linkSeguro(c.link_fonte), target: "_blank", rel: "noopener", texto: " fonte ↗" }) : null,
    ]),
    el("div", { class: "pop-assoc" }, [
      el("span", {}, [el("b", { "data-n": "voluntarios", texto: String(c.voluntarios ?? 0) }), "voluntários"]),
      el("span", {}, [el("b", { "data-n": "ongs", texto: String(c.ongs ?? 0) }), "ONGs"]),
      PAPEL === "org" ? el("span", {}, [el("b", { "data-n": "campanhas", texto: "–" }), "campanhas"]) : null,
    ]),
    PAPEL === "org" && !ESCOLHER ? el("p", { class: "pop-rec", "data-plano": "", texto: "Carregando a recomendação do assistente…" }) : null,
    acoes(c, msg),
    msg,
  ]);
  return caixa;
}

function acoes(c, msg) {
  const box = el("div", { class: "acoes" });
  if (PAPEL === "org") acoesOng(c, box);
  if ((PAPEL === "volunteer" || PAPEL === "org") && !ESCOLHER) {
    const botao = el("button", { type: "button" });
    const pintar = () => {
      const dentro = INSCRITO.has(c.id);
      // para a ONG, apoiar é secundário: a ação principal do popup é a campanha
      botao.className = PAPEL === "org" ? "texto-link pequeno" : `botao botao-pequeno ${dentro ? "botao-neutro" : "botao-primario"}`;
      botao.textContent = dentro ? (PAPEL === "org" ? "Deixar de apoiar" : "Cancelar inscrição") : (PAPEL === "org" ? "Apoiar crise" : "Inscrever-se");
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
