/* Mapa do Brasil por município — mesma estrutura do dashboardfortaleza.vercel.app:
   1) abertura: país desenhado em "pixels" num <canvas> (tamanho e brilho pelo indicador)
   2) explorador: mapa coroplético em Leaflet, sem tiles de fundo, só o GeoJSON pintado em 6 classes.
   Dados em data.js: window.DADOS.geojson (uma Feature por município) e window.DADOS.estados (contornos das UFs). */
(() => {
  "use strict";

  const D = window.DADOS;
  const FEATS = D.geojson.features;
  const MUNS = FEATS.map((f) => f.properties);
  const POR_ID = new Map(MUNS.map((p) => [p.id, p]));
  const REDUZIR = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const RAMPA = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"].map(css);
  const COR = { cobalto: css("--cobalto"), escuro: css("--cobalto-escuro"), branco: "#ffffff" };

  const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  const curto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });

  function el(tag, attrs = {}, filhos = []) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "texto") n.textContent = v;
      else if (v != null) n.setAttribute(k, v);
    }
    n.append(...[].concat(filhos).filter((c) => c != null));
    return n;
  }

  const estado = { ind: "densidade", sel: null, busca: "" };

  // ---------- indicadores ----------
  // Cada indicador vira uma nota de 0 a 100 em escala log (min-max), como a renda no original:
  // os valores entre municípios variam em ordens de grandeza (densidade de ~0,1 a ~13 mil hab/km²).
  function escalaLog(campo) {
    const vals = MUNS.map((p) => Math.log(p[campo]));
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return {
      nota: (p) => ((Math.log(p[campo]) - lo) / (hi - lo)) * 100,
      valorDaNota: (s) => Math.exp(lo + (s / 100) * (hi - lo)),
    };
  }
  const IND = {
    densidade: {
      ...escalaLog("densidade_2022"),
      texto: (p) => `${nf1.format(p.densidade_2022)} hab/km²`,
      legenda: "Densidade demográfica, 2022 (hab/km²)",
      fmt: (v) => nf1.format(v),
    },
    populacao: {
      ...escalaLog("pop_2022"),
      texto: (p) => `${nf0.format(p.pop_2022)} hab.`,
      legenda: "População residente, 2022",
      fmt: (v) => curto.format(v),
    },
    area: {
      ...escalaLog("area_km2"),
      texto: (p) => `${nf0.format(p.area_km2)} km²`,
      legenda: "Área territorial (km²)",
      fmt: (v) => curto.format(v),
    },
  };
  const ind = () => IND[estado.ind];
  const nota = (p) => ind().nota(p);

  // 6 classes de intervalos iguais entre a menor e a maior nota
  function cor(v) {
    return RAMPA[Math.max(0, Math.min(5, Math.floor((v / 100) * 6)))];
  }

  // =====================================================================
  // MAPA (Leaflet, sem camada de tiles; canvas para aguentar os 5.570 polígonos)
  // =====================================================================
  const mapaEl = document.getElementById("mapa-leaflet");
  const mapa = L.map(mapaEl, { zoomSnap: 0.25, minZoom: 3.5, maxZoom: 12, scrollWheelZoom: false, preferCanvas: true });
  const tela2d = L.canvas({ padding: 0.5, tolerance: 2 });
  mapa.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>').addAttribution("IBGE");
  mapaEl.addEventListener("click", () => mapa.scrollWheelZoom.enable(), { once: true });

  function estilo(f) {
    const sel = estado.sel === f.properties.id;
    return {
      className: "bairro-forma",
      fillColor: cor(nota(f.properties)),
      fillOpacity: 0.9,
      color: sel ? COR.escuro : COR.branco,
      weight: sel ? 3 : 0.35,
      opacity: sel ? 1 : 0.7,
    };
  }

  const camada = L.geoJSON(D.geojson, {
    renderer: tela2d,
    style: estilo,
    onEachFeature(f, layer) {
      layer.bindTooltip(() => `<b>${f.properties.nome} – ${f.properties.uf}</b><span>${ind().texto(f.properties)}</span>`, {
        sticky: true, direction: "top", offset: [0, -8], className: "dica-mapa",
      });
      layer.on({
        mouseover: () => { if (estado.sel !== f.properties.id) layer.setStyle({ weight: 2.2, color: COR.escuro }); },
        mouseout: () => { camada.resetStyle(layer); if (estado.sel === f.properties.id) layer.bringToFront(); },
        click: () => selecionar(f.properties.id, { centralizar: false }),
      });
    },
  }).addTo(mapa);
  // contorno das UFs por cima, só para orientar (não recebe clique)
  const ufs = L.geoJSON(D.estados, {
    renderer: tela2d, interactive: false,
    style: { fill: false, color: COR.escuro, weight: 1.1, opacity: 0.55 },
  }).addTo(mapa);
  mapa.fitBounds(camada.getBounds(), { padding: [12, 12] });
  mapa.setMaxBounds(camada.getBounds().pad(0.3));
  const camadaSel = () => camada.getLayers().find((l) => l.feature.properties.id === estado.sel);

  function pintar() {
    camada.setStyle(estilo);
    ufs.bringToFront();
    camadaSel()?.bringToFront();
  }

  // ---------- legenda ----------
  function legenda() {
    const i = ind();
    document.getElementById("legenda").replaceChildren(
      el("p", { class: "legenda-titulo", texto: i.legenda }),
      el("div", { class: "legenda-escala", "aria-hidden": "true" }, RAMPA.map((c) => el("span", { style: `background:${c}` }))),
      el("div", { class: "legenda-rotulos" }, [i.fmt(i.valorDaNota(0)), i.fmt(i.valorDaNota(100))].map((r) => el("span", { texto: r }))),
    );
  }

  // =====================================================================
  // FICHA E RANKING
  // =====================================================================
  let ORDEM = [], POS = new Map();
  function ordenar() {
    ORDEM = [...MUNS].sort((a, b) => nota(b) - nota(a));
    POS = new Map(ORDEM.map((p, i) => [p.id, i + 1]));
  }

  function ficha(animar) {
    const box = document.getElementById("ficha");
    const p = POR_ID.get(estado.sel);
    if (!p) {
      box.replaceChildren(el("p", { class: "ficha-vazia", texto: "Clique num município no mapa ou na lista para ver os números dele." }));
      return;
    }
    const eixo = (nome, txt, n) => el("li", {}, [
      el("div", { class: "eixo-linha" }, [el("span", { texto: nome }), el("span", { texto: txt })]),
      el("div", { class: "barra" }, el("i", { style: `width:${n.toFixed(1)}%` })),
    ]);
    box.replaceChildren(
      el("p", { class: "ficha-sub", texto: `${p.uf} · Região ${p.regiao}` }),
      el("h3", { texto: p.nome }),
      el("div", { class: "ficha-topo" }, [
        el("p", { class: "ficha-indice" }, [nf0.format(nota(p)), el("small", { texto: "/100" })]),
        el("p", { class: "ficha-pos", texto: `${nf0.format(POS.get(p.id))}º de ${nf0.format(MUNS.length)} em ${ind().legenda.split(",")[0].toLowerCase()}` }),
      ]),
      el("ul", { class: "eixos" }, [
        eixo("Densidade", IND.densidade.texto(p), IND.densidade.nota(p)),
        eixo("População", IND.populacao.texto(p), IND.populacao.nota(p)),
        eixo("Área", IND.area.texto(p), IND.area.nota(p)),
      ]),
    );
    if (animar) { box.classList.remove("entrando"); void box.offsetWidth; box.classList.add("entrando"); }
  }

  // a lista mostra no máximo LIMITE linhas; a busca filtra por nome ou UF
  const LIMITE = 150;
  const semAcento = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const CHAVE = new Map(MUNS.map((p) => [p.id, semAcento(`${p.nome} ${p.uf}`)]));
  function ranking() {
    const q = semAcento(estado.busca.trim());
    const achados = q ? ORDEM.filter((p) => CHAVE.get(p.id).includes(q) || p.uf.toLowerCase() === q) : ORDEM;
    const ord = achados.slice(0, LIMITE);
    document.getElementById("ranking-pe").textContent = achados.length > LIMITE
      ? `Mostrando ${LIMITE} de ${nf0.format(achados.length)}. Busque para achar os outros.`
      : achados.length ? "" : "Nenhum município encontrado.";
    document.getElementById("ranking").replaceChildren(...ord.map((p) => el("li", {}, el("button", {
      type: "button", "data-id": p.id, "aria-current": estado.sel === p.id ? "true" : "false",
    }, [
      el("span", { class: "rk-pos", texto: String(POS.get(p.id)).padStart(2, "0") }),
      el("span", { class: "rk-nome", texto: `${p.nome} – ${p.uf}` }),
      el("span", { class: "rk-barra", "aria-hidden": "true" }, el("i", { style: `width:${nota(p).toFixed(1)}%` })),
      el("span", { class: "rk-valor", texto: ind().texto(p) }),
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
    if (l && centralizar) mapa.flyToBounds(l.getBounds(), { padding: [60, 60], maxZoom: 10, duration: REDUZIR ? 0 : 0.8 });
  }

  // ---------- controles ----------
  document.getElementById("ctl-indicador").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (!b) return;
    estado.ind = b.dataset.v;
    for (const x of e.currentTarget.querySelectorAll("button")) x.setAttribute("aria-pressed", String(x === b));
    ordenar(); pintar(); legenda(); ficha(false); ranking();
    atualizarPixels();
  });

  // =====================================================================
  // ABERTURA: Brasil em pixels (as "bolinhas")
  // =====================================================================
  const tela = document.getElementById("cidade");
  const ctx = tela.getContext("2d");
  const tag = document.getElementById("cidade-tag");
  let celulas = [], grade = null, inicio = 0, rodando = false, emFoco = null, visivel = true;

  // polígonos em coordenadas planas simples (lon·cos(lat0), lat); lat0 no centro do país
  const LAT0 = -15, KX = Math.cos((LAT0 * Math.PI) / 180);
  const aneis = FEATS.map((f) => {
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
    const rings = polys.map((pl) => pl.map((r) => r.map(([lo, la]) => [lo * KX, la])));
    let bb = [Infinity, Infinity, -Infinity, -Infinity];
    rings.flat(2).forEach(([x, yy]) => { bb = [Math.min(bb[0], x), Math.min(bb[1], yy), Math.max(bb[2], x), Math.max(bb[3], yy)]; });
    return { id: f.properties.id, rings, bb };
  });
  const BB = aneis.reduce((a, r) => [Math.min(a[0], r.bb[0]), Math.min(a[1], r.bb[1]), Math.max(a[2], r.bb[2]), Math.max(a[3], r.bb[3])], [Infinity, Infinity, -Infinity, -Infinity]);
  // índice espacial: baldes de 1° com os municípios cuja caixa toca cada balde (5.570 polígonos)
  const balde = (x, yy) => `${Math.floor(x)}:${Math.floor(yy)}`;
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
    for (const a of BALDES.get(balde(x, yy)) || []) {
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
    const lado = r.width < 520 ? 5 : 7;
    const pad = 12, w = r.width - 2 * pad, h = r.height - 2 * pad - 24;
    const esc = Math.min(w / (BB[2] - BB[0]), h / (BB[3] - BB[1]));
    const ox = pad + (w - (BB[2] - BB[0]) * esc) / 2, oy = pad + (h - (BB[3] - BB[1]) * esc) / 2;
    const centro = { x: r.width * 0.42, y: r.height * 0.3 };
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
  // t (0–1) = nota do indicador escolhido; muda junto com os botões do explorador
  function atualizarPixels() {
    for (const c of celulas) c.t = nota(POR_ID.get(c.id)) / 100;
    if (REDUZIR) desenharCidade(performance.now());
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
      ctx.fillStyle = `rgba(255,255,255,${alfa})`;
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
      tag.replaceChildren(el("b", { texto: `${p.nome} – ${p.uf}` }), ind().texto(p));
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
  }).observe(tela);

  let tRedim;
  window.addEventListener("resize", () => {
    clearTimeout(tRedim);
    tRedim = setTimeout(() => { montarCidade(); inicio = performance.now() - 5000; iniciarLaco(); mapa.invalidateSize(); }, 200);
  });

  // ---------- início ----------
  ordenar(); legenda(); ficha(false); ranking();
  montarCidade();
  inicio = performance.now();
  iniciarLaco();
  requestAnimationFrame(() => document.querySelector(".hero").classList.add("pronto"));
})();
