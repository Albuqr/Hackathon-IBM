/* Dash Brasil — mapa de pixels + mapa coroplético dos 5.570 municípios pintados pelas crises ativas.
   Estrutura herdada de temp/mapa-brasil (réplica de dashboardfortaleza.vercel.app).
   Dados: window.MALHA (IBGE, via /brasil/malha.js) e as rotas JSON /brasil/api/... */
(async () => {
  "use strict";

  const CFG = JSON.parse(document.getElementById("br-config").textContent);
  const M = window.MALHA;
  if (!M) { document.getElementById("ficha").textContent = "Não foi possível carregar a malha do IBGE."; return; }
  const FEATS = M.geojson.features;
  const MUNS = FEATS.map((f) => f.properties);
  const POR_ID = new Map(MUNS.map((p) => [p.id, p]));
  const REDUZIR = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const PODE_INSCREVER = CFG.papel === "volunteer" || CFG.papel === "org";

  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  // escalas validadas para o fundo escuro (ver brasil.css): severidade em laranja, contagens em azul
  const SEV = ["--sev1", "--sev2", "--sev3", "--sev4", "--sev5"].map(css);
  const RAMPA = ["--seq1", "--seq2", "--seq3", "--seq4", "--seq5", "--seq6"].map(css);
  const COR = { traco: css("--traco"), uf: css("--uf"), vazio: css("--vazio"), destaque: "#ffffff", alerta: css("--alerta") };
  const corSev = (s) => SEV[Math.max(1, Math.min(5, Math.round(s))) - 1];

  const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const curto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
  const TIPOS = { wildfire: "queimada", meteorological: "meteorológico", geological: "geológico", seismic: "sísmico",
    drought: "seca", humanitarian: "humanitário", conflict: "conflito", sanitary: "sanitário" };

  function el(tag, attrs = {}, filhos = []) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "texto") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v != null && v !== false) n.setAttribute(k, v);
    }
    n.append(...[].concat(filhos).filter((c) => c != null));
    return n;
  }

  // ---------- dados ----------
  const pegar = async (u) => { try { const r = await fetch(u); return r.ok ? r.json() : null; } catch { return null; } };
  let [CRISES, VOL, INSC] = await Promise.all([pegar(CFG.crises), pegar(CFG.voluntarios), PODE_INSCREVER ? pegar(CFG.inscricoes) : []]);
  CRISES = CRISES || []; VOL = VOL || {};
  let INSCRITO = new Set((INSC || []).map((i) => i.id));

  const estado = { ind: "severidade", sel: null, busca: "", f: { uf: "", sev: 1, tipo: "", fonte: "", verif: "" }, pontos: true };

  // por município: severidade máxima e nº de crises, só com as crises que passam nos filtros
  let VISIVEIS = [], POR_MUN = new Map();
  function filtrar() {
    const f = estado.f;
    VISIVEIS = CRISES.filter((c) => c.severity >= f.sev && (!f.uf || c.uf === f.uf) && (!f.tipo || c.crisis_type === f.tipo)
      && (!f.fonte || c.source === f.fonte) && (!f.verif || c.verificacao === f.verif));
    POR_MUN = new Map();
    for (const c of VISIVEIS) {
      const muns = c.municipios_afetados && c.municipios_afetados.length ? c.municipios_afetados : (c.municipio_ibge ? [c.municipio_ibge] : []);
      for (const id of muns) {
        if (!POR_ID.has(id)) continue;
        const a = POR_MUN.get(id) || { sev: 0, n: 0, crises: [] };
        a.sev = Math.max(a.sev, c.severity); a.n += 1; a.crises.push(c);
        POR_MUN.set(id, a);
      }
    }
    document.getElementById("contagem").textContent = `${nf0.format(VISIVEIS.length)} crises · ${nf0.format(POR_MUN.size)} municípios`;
    document.getElementById("k-crises").textContent = nf0.format(VISIVEIS.length);
    document.getElementById("k-muns").textContent = nf0.format(POR_MUN.size);
    document.getElementById("k-graves").textContent = nf0.format(VISIVEIS.filter((c) => c.severity >= 4).length);
    document.getElementById("k-nv").textContent = nf0.format(VISIVEIS.filter((c) => c.verificacao === "nao_verificada").length);
  }

  // ---------- indicadores ----------
  function escalaLog(valor) {
    const vals = MUNS.map(valor).filter((v) => v > 0).map(Math.log);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return { nota: (p) => { const v = valor(p); return v > 0 ? (hi > lo ? ((Math.log(v) - lo) / (hi - lo)) * 100 : 100) : 0; },
             valorDaNota: (s) => Math.exp(lo + (s / 100) * (hi - lo)) };
  }
  const IND = {
    severidade: { valor: (p) => POR_MUN.get(p.id)?.sev || 0, nota: (p) => ((POR_MUN.get(p.id)?.sev || 0) / 5) * 100,
      texto: (p) => { const a = POR_MUN.get(p.id); return a ? `severidade ${a.sev}` : "sem crise"; },
      legenda: "Severidade máxima das crises ativas", discreta: true },
    crises: { valor: (p) => POR_MUN.get(p.id)?.n || 0, dinamica: () => escalaLog((p) => POR_MUN.get(p.id)?.n || 0),
      texto: (p) => `${nf0.format(POR_MUN.get(p.id)?.n || 0)} crises`, legenda: "Nº de crises ativas", fmt: nf0.format },
    voluntarios: { valor: (p) => VOL[p.id] || 0, dinamica: () => escalaLog((p) => VOL[p.id] || 0),
      texto: (p) => `${nf0.format(VOL[p.id] || 0)} voluntários`, legenda: "Voluntários disponíveis", fmt: nf0.format },
    densidade: { valor: (p) => p.densidade_2022, ...escalaLog((p) => p.densidade_2022),
      texto: (p) => `${nf1.format(p.densidade_2022)} hab/km²`, legenda: "Densidade demográfica, 2022 (hab/km²)", fmt: nf1.format, contexto: true },
    populacao: { valor: (p) => p.pop_2022, ...escalaLog((p) => p.pop_2022),
      texto: (p) => `${nf0.format(p.pop_2022)} hab.`, legenda: "População residente, 2022", fmt: curto.format, contexto: true },
  };
  let I = IND.severidade;
  function escolher(nome) {
    estado.ind = nome; I = IND[nome];
    if (I.dinamica) Object.assign(I, I.dinamica());
  }
  const nota = (p) => I.nota(p);
  function cor(p) {
    if (I.discreta) { const s = POR_MUN.get(p.id)?.sev; return s ? corSev(s) : COR.vazio; }
    if (!I.contexto && !I.valor(p)) return COR.vazio;
    return RAMPA[Math.max(0, Math.min(5, Math.floor((nota(p) / 100) * 6)))];
  }

  // =====================================================================
  // MAPA (Leaflet, sem tiles; canvas para os 5.570 polígonos)
  // =====================================================================
  const mapaEl = document.getElementById("mapa-leaflet");
  const mapa = L.map(mapaEl, { zoomSnap: 0.25, minZoom: 3.5, maxZoom: 12, scrollWheelZoom: false, preferCanvas: true });
  const render = L.canvas({ padding: 0.5, tolerance: 2 });
  mapa.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>').addAttribution("IBGE · INPE · CEMADEN · INMET");
  mapaEl.addEventListener("click", () => mapa.scrollWheelZoom.enable(), { once: true });

  function estilo(f) {
    const sel = estado.sel === f.properties.id;
    return { fillColor: cor(f.properties), fillOpacity: 1, color: sel ? COR.destaque : COR.traco,
             weight: sel ? 2.5 : 0.4, opacity: sel ? 1 : 0.8 };
  }
  const camada = L.geoJSON(M.geojson, {
    renderer: render, style: estilo,
    onEachFeature(f, layer) {
      layer.bindTooltip(() => `<b>${f.properties.nome} – ${f.properties.uf}</b><span>${I.texto(f.properties)}</span>`,
        { sticky: true, direction: "top", offset: [0, -8], className: "dica-mapa" });
      layer.on({
        mouseover: () => { if (estado.sel !== f.properties.id) layer.setStyle({ weight: 2, color: COR.destaque }); },
        mouseout: () => { camada.resetStyle(layer); if (estado.sel === f.properties.id) layer.bringToFront(); },
        click: () => selecionar(f.properties.id, { centralizar: false }),
      });
    },
  }).addTo(mapa);
  const ufs = L.geoJSON(M.estados, { renderer: render, interactive: false,
    style: { fill: false, color: COR.uf, weight: 1, opacity: 0.9 } }).addTo(mapa);
  mapa.fitBounds(camada.getBounds(), { padding: [12, 12] });
  mapa.setMaxBounds(camada.getBounds().pad(0.3));
  const camadaSel = () => camada.getLayers().find((l) => l.feature.properties.id === estado.sel);

  const pontos = L.layerGroup().addTo(mapa);
  function desenharPontos() {
    pontos.clearLayers();
    if (!estado.pontos) return;
    for (const c of VISIVEIS) {
      const naoVer = c.verificacao === "nao_verificada";
      L.circleMarker([c.lat, c.lon], { renderer: render, radius: 2.5 + c.severity, fillColor: corSev(c.severity), fillOpacity: 1,
        color: naoVer ? COR.alerta : COR.traco, weight: naoVer ? 1.6 : 2, dashArray: naoVer ? "3 2" : null })
        .bindTooltip(`<b>${c.title}</b><span>sev. ${c.severity}${naoVer ? " · não verificada" : ""}</span>`, { direction: "top", className: "dica-mapa" })
        .on("click", () => c.municipio_ibge && selecionar(c.municipio_ibge, { centralizar: false }))
        .addTo(pontos);
    }
  }

  function pintar() {
    camada.setStyle(estilo);
    ufs.bringToFront();
    camadaSel()?.bringToFront();
  }

  // ---------- legenda ----------
  function legenda() {
    const box = document.getElementById("legenda");
    const titulo = el("p", { class: "legenda-titulo", texto: I.legenda });
    if (I.discreta) {
      box.replaceChildren(titulo,
        el("div", { class: "legenda-escala", "aria-hidden": "true" }, [COR.vazio, ...SEV].map((c) => el("span", { style: `background:${c}` }))),
        el("div", { class: "legenda-rotulos uniforme" }, ["sem", "1", "2", "3", "4", "5"].map((r) => el("span", { texto: r }))));
      return;
    }
    box.replaceChildren(titulo,
      el("div", { class: "legenda-escala", "aria-hidden": "true" }, RAMPA.map((c) => el("span", { style: `background:${c}` }))),
      el("div", { class: "legenda-rotulos" }, [I.fmt(I.valorDaNota(0)), I.fmt(I.valorDaNota(100))].map((r) => el("span", { texto: r }))));
  }

  // =====================================================================
  // FICHA E RANKING
  // =====================================================================
  let ORDEM = [], POS = new Map();
  function ordenar() {
    ORDEM = [...MUNS].filter((p) => I.contexto || I.valor(p) > 0).sort((a, b) => I.valor(b) - I.valor(a));
    POS = new Map(ORDEM.map((p, i) => [p.id, i + 1]));
  }

  async function alternar(c, botao) {
    const acao = INSCRITO.has(c.id) ? "cancelar" : "inscrever";
    botao.disabled = true;
    const r = await fetch(CFG.inscrever.replace("__ID__", encodeURIComponent(c.id)).replace("__ACAO__", acao), { method: "POST" });
    if (r.ok) {
      const d = await r.json();
      c.inscritos = d.inscritos;
      acao === "inscrever" ? INSCRITO.add(c.id) : INSCRITO.delete(c.id);
    }
    ficha(false);
  }

  function itemCrise(c) {
    const naoVer = c.verificacao === "nao_verificada";
    return el("li", { class: "crise" }, [
      el("div", { class: "item-topo" }, [
        el("span", { class: "item-titulo", texto: c.title }),
        el("span", { class: "sev", style: `background:${corSev(c.severity)}`, texto: String(Math.round(c.severity)), title: "severidade" }),
      ]),
      el("span", { class: "item-meta crise-meta", texto: `${TIPOS[c.crisis_type] || c.crisis_type} · ${c.source.toUpperCase()} · ${nf0.format(c.inscritos || 0)} inscritos` }),
      naoVer ? el("span", {}, el("span", { class: "selo selo-nv", texto: "não verificada" })) : null,
      c.link_fonte ? el("a", { class: "item-meta", href: c.link_fonte, target: "_blank", rel: "noopener", texto: "fonte ↗" }) : null,
      PODE_INSCREVER ? el("div", { class: "acoes" }, [
        el("button", {
          type: "button", class: `botao botao-pequeno ${INSCRITO.has(c.id) ? "botao-neutro" : "botao-primario"} inscricao`,
          texto: INSCRITO.has(c.id) ? "Cancelar inscrição" : "Quero ajudar",
          onclick: (e) => alternar(c, e.currentTarget),
        }),
        CFG.nova_campanha ? el("a", { class: "botao botao-secundario botao-pequeno criar-campanha", href: `${CFG.nova_campanha}?crise=${encodeURIComponent(c.id)}#nova`, texto: "Criar campanha" }) : null,
      ]) : null,
    ]);
  }

  function ficha(animar) {
    const box = document.getElementById("ficha");
    const p = POR_ID.get(estado.sel);
    if (!p) {
      box.replaceChildren(el("p", { class: "vazio", texto: CRISES.length
        ? "Clique num município no mapa ou na lista para ver as crises dele."
        : "Ainda não há crises carregadas. Um admin precisa clicar em \"Atualizar dados\"." }));
      return;
    }
    const a = POR_MUN.get(p.id);
    box.replaceChildren(
      el("p", { class: "ficha-local", texto: `${p.uf} · Região ${p.regiao} · ${nf0.format(p.pop_2022)} hab.` }),
      el("h3", { texto: p.nome }),
      el("div", { class: "ficha-numero" }, [
        el("b", { style: a ? `color:${corSev(a.sev)}` : null, texto: a ? String(Math.round(a.sev)) : "–" }),
        el("span", { texto: a ? `severidade máxima · ${a.n} crise${a.n > 1 ? "s" : ""} ativa${a.n > 1 ? "s" : ""}` : "Sem crise ativa com os filtros atuais" }),
      ]),
      a ? el("ul", { class: "lista lista-crises" }, a.crises.sort((x, y) => y.severity - x.severity).map(itemCrise)) : null,
    );
    if (animar) { box.classList.remove("entrando"); void box.offsetWidth; box.classList.add("entrando"); }
  }

  const LIMITE = 150;
  const semAcento = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const CHAVE = new Map(MUNS.map((p) => [p.id, semAcento(`${p.nome} ${p.uf}`)]));
  function ranking() {
    const q = semAcento(estado.busca.trim());
    const base = q ? MUNS.filter((p) => CHAVE.get(p.id).includes(q) || p.uf.toLowerCase() === q).sort((a, b) => I.valor(b) - I.valor(a)) : ORDEM;
    const ord = base.slice(0, LIMITE);
    document.getElementById("ranking-pe").textContent = base.length > LIMITE
      ? `Mostrando ${LIMITE} de ${nf0.format(base.length)}. Busque para achar os outros.`
      : base.length ? "" : (q ? "Nenhum município encontrado." : "Nenhum município com valor neste indicador.");
    document.getElementById("ranking").replaceChildren(...ord.map((p) => el("li", {}, el("button", {
      type: "button", "data-id": p.id, "aria-current": estado.sel === p.id ? "true" : "false",
    }, [
      el("span", { class: "rk-pos", texto: POS.has(p.id) ? String(POS.get(p.id)).padStart(2, "0") : "–" }),
      el("span", { class: "rk-nome", texto: `${p.nome} – ${p.uf}` }),
      el("span", { class: "rk-barra", "aria-hidden": "true" }, el("i", { style: `width:${nota(p).toFixed(1)}%;background:${cor(p)}` })),
      el("span", { class: "rk-valor", texto: I.texto(p) }),
    ]))));
  }
  document.getElementById("ranking").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-id]");
    if (b) selecionar(Number(b.dataset.id), { centralizar: true });
  });
  let tBusca;
  document.getElementById("busca").addEventListener("input", (e) => {
    clearTimeout(tBusca);
    tBusca = setTimeout(() => { estado.busca = e.target.value; ranking(); }, 120);
  });

  function selecionar(id, { centralizar }) {
    estado.sel = estado.sel === id && !centralizar ? null : id;
    pintar(); ficha(true); ranking();
    const l = camadaSel();
    if (l && centralizar) mapa.flyToBounds(l.getBounds(), { padding: [60, 60], maxZoom: 9, duration: REDUZIR ? 0 : 0.8 });
  }

  function atualizarTudo() {
    filtrar(); escolher(estado.ind); ordenar(); pintar(); legenda(); ficha(false); ranking(); desenharPontos(); atualizarPixels();
  }

  // ---------- controles ----------
  document.getElementById("ctl-indicador").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (!b) return;
    for (const x of e.currentTarget.querySelectorAll("button")) x.setAttribute("aria-pressed", String(x === b));
    estado.ind = b.dataset.v;
    atualizarTudo();
  });
  const opcoes = (id, valores, rotulo = (v) => v) => {
    const s = document.getElementById(id);
    for (const v of [...new Set(valores)].filter(Boolean).sort()) s.append(el("option", { value: v, texto: rotulo(v) }));
  };
  opcoes("f-uf", MUNS.map((p) => p.uf));
  opcoes("f-tipo", CRISES.map((c) => c.crisis_type), (v) => TIPOS[v] || v);
  opcoes("f-fonte", CRISES.map((c) => c.source), (v) => v.toUpperCase());
  for (const [id, k, num] of [["f-uf", "uf"], ["f-sev", "sev", true], ["f-tipo", "tipo"], ["f-fonte", "fonte"], ["f-verif", "verif"]]) {
    document.getElementById(id).addEventListener("change", (e) => { estado.f[k] = num ? Number(e.target.value) : e.target.value; atualizarTudo(); });
  }
  document.getElementById("f-pontos").addEventListener("change", (e) => { estado.pontos = e.target.checked; desenharPontos(); });

  // =====================================================================
  // ABERTURA: Brasil em pixels
  // =====================================================================
  const tela = document.getElementById("cidade");
  const ctx = tela.getContext("2d");
  const tag = document.getElementById("cidade-tag");
  let celulas = [], grade = null, inicio = 0, rodando = false, emFoco = null, visivel = true;

  const LAT0 = -15, KX = Math.cos((LAT0 * Math.PI) / 180);
  const aneis = FEATS.map((f) => {
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
    const rings = polys.map((pl) => pl.map((r) => r.map(([lo, la]) => [lo * KX, la])));
    let bb = [Infinity, Infinity, -Infinity, -Infinity];
    rings.flat(2).forEach(([x, yy]) => { bb = [Math.min(bb[0], x), Math.min(bb[1], yy), Math.max(bb[2], x), Math.max(bb[3], yy)]; });
    return { id: f.properties.id, rings, bb };
  });
  const BB = aneis.reduce((a, r) => [Math.min(a[0], r.bb[0]), Math.min(a[1], r.bb[1]), Math.max(a[2], r.bb[2]), Math.max(a[3], r.bb[3])], [Infinity, Infinity, -Infinity, -Infinity]);
  const BALDES = new Map();
  for (const a of aneis) {
    for (let x = Math.floor(a.bb[0]); x <= Math.floor(a.bb[2]); x++) {
      for (let yy = Math.floor(a.bb[1]); yy <= Math.floor(a.bb[3]); yy++) {
        const k = `${x}:${yy}`;
        if (!BALDES.has(k)) BALDES.set(k, []);
        BALDES.get(k).push(a);
      }
    }
  }
  function dentro(x, yy, ring) {
    let c = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > yy) !== (yj > yy) && x < ((xj - xi) * (yy - yi)) / (yj - yi) + xi) c = !c;
    }
    return c;
  }
  function municipioEm(x, yy) {
    for (const a of BALDES.get(`${Math.floor(x)}:${Math.floor(yy)}`) || []) {
      if (x < a.bb[0] || x > a.bb[2] || yy < a.bb[1] || yy > a.bb[3]) continue;
      for (const pl of a.rings) if (dentro(x, yy, pl[0]) && !pl.slice(1).some((h) => dentro(x, yy, h))) return a.id;
    }
    return null;
  }

  function montarCidade() {
    const r = tela.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    tela.width = Math.round(r.width * dpr); tela.height = Math.round(r.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const lado = r.width < 360 ? 3 : 4;
    const pad = 12, w = r.width - 2 * pad, h = r.height - 2 * pad - 20;
    const esc = Math.min(w / (BB[2] - BB[0]), h / (BB[3] - BB[1]));
    const ox = pad + (w - (BB[2] - BB[0]) * esc) / 2, oy = pad + (h - (BB[3] - BB[1]) * esc) / 2;
    const centro = { x: r.width * 0.5, y: r.height * 0.4 };
    const cols = Math.floor(r.width / lado), lins = Math.floor(r.height / lado);
    grade = { lado, cols, lins, ids: new Int32Array(cols * lins).fill(-1) };
    celulas = [];
    for (let j = 0; j < lins; j++) {
      for (let i = 0; i < cols; i++) {
        const cx = i * lado + lado / 2, cy = j * lado + lado / 2;
        const id = municipioEm(BB[0] + (cx - ox) / esc, BB[3] - (cy - oy) / esc);
        if (id == null) continue;
        grade.ids[j * cols + i] = id;
        const dist = Math.hypot(cx - centro.x, cy - centro.y) / Math.hypot(r.width, r.height);
        celulas.push({ x: i * lado, y: j * lado, id, t: 0, atraso: dist * 1500 + Math.random() * 380 });
      }
    }
    atualizarPixels();
  }
  function atualizarPixels() {
    for (const c of celulas) c.t = nota(POR_ID.get(c.id)) / 100;
    if (REDUZIR && grade) desenharCidade(performance.now());
  }

  function desenharCidade(agora) {
    const r = tela.getBoundingClientRect();
    ctx.clearRect(0, 0, r.width, r.height);
    const lado = grade.lado, dt = agora - inicio;
    const varre = REDUZIR ? -1e9 : ((agora / 6500) % 1) * (r.width + 240) - 120;
    for (const c of celulas) {
      let k = 1;
      if (!REDUZIR) {
        k = Math.min(1, Math.max(0, (dt - c.atraso) / 520));
        if (k === 0) continue;
        k = 1 - Math.pow(1 - k, 3);
      }
      const foco = emFoco === c.id;
      const onda = Math.exp(-(((c.x - varre) / 46) ** 2));
      const tam = foco ? lado - 1 : lado * (0.2 + 0.62 * c.t + 0.22 * onda) * k;
      const alfa = foco ? 1 : Math.min(1, 0.32 + 0.6 * c.t + 0.3 * onda);
      ctx.fillStyle = c.t > 0 || foco ? `rgba(255,177,136,${alfa})` : `rgba(255,255,255,${alfa * 0.35})`;
      const off = (lado - tam) / 2;
      ctx.fillRect(c.x + off, c.y + off, tam, tam);
    }
  }
  function laco(agora) {
    if (!visivel) { rodando = false; return; }
    desenharCidade(agora);
    if (REDUZIR) { rodando = false; return; }
    requestAnimationFrame(laco);
  }
  function iniciarLaco() { if (!rodando) { rodando = true; requestAnimationFrame(laco); } }

  tela.addEventListener("pointermove", (e) => {
    if (!grade) return;
    const r = tela.getBoundingClientRect();
    const i = Math.floor((e.clientX - r.left) / grade.lado), j = Math.floor((e.clientY - r.top) / grade.lado);
    const id = i >= 0 && j >= 0 && i < grade.cols && j < grade.lins ? grade.ids[j * grade.cols + i] : -1;
    emFoco = id >= 0 ? id : null;
    if (emFoco == null) { tag.hidden = true; tela.style.cursor = "default"; }
    else {
      const p = POR_ID.get(emFoco);
      tag.replaceChildren(el("b", { texto: `${p.nome} – ${p.uf}` }), I.texto(p));
      tag.hidden = false;
      tag.style.left = (e.clientX - r.left) + "px";
      tag.style.top = (e.clientY - r.top) + "px";
      tela.style.cursor = "pointer";
    }
    if (REDUZIR) desenharCidade(performance.now());
  });
  tela.addEventListener("pointerleave", () => { emFoco = null; tag.hidden = true; if (REDUZIR) desenharCidade(performance.now()); });
  tela.addEventListener("click", () => {
    if (emFoco == null) return;
    selecionar(emFoco, { centralizar: true });
    document.getElementById("mapa").scrollIntoView();
  });
  new IntersectionObserver((ents) => {
    visivel = ents[0].isIntersecting;
    if (visivel) iniciarLaco();
    else if (grade) desenharCidade(inicio + 1e6);  // fora da tela: deixa o quadro final pronto, sem animar
  }).observe(tela);

  let tRedim;
  window.addEventListener("resize", () => {
    clearTimeout(tRedim);
    tRedim = setTimeout(() => { montarCidade(); inicio = performance.now() - 5000; iniciarLaco(); mapa.invalidateSize(); }, 200);
  });

  // ---------- início ----------
  filtrar(); escolher(estado.ind); ordenar(); pintar(); legenda(); ficha(false); ranking(); desenharPontos();
  montarCidade();
  inicio = performance.now();
  iniciarLaco();
  window.__brasilMapa = mapa;
  window.__brasilPronto = true;
})();
