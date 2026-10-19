// Dash Brasil — Visão do mapa (candidato 1 do relatório de arquitetura).
// Module puro (sem DOM, sem Leaflet): recebe crises + filtros e devolve o que desenhar.
// Marcadores, pixels, barra lateral e legenda só desenham a saída daqui, então nunca discordam.
// A regra de UF é a mesma da API (middleware/brasil/ingestao.py: filtrar / ufs_da_crise).

export const PADRAO = Object.freeze({ sev: 1, uf: "", tipo: "", fonte: "", verif: "", q: "", modo: "municipios" });
const CHAVES = { sev: "sev", uf: "uf", tipo: "tipo", fonte: "fonte", verif: "verif", q: "q", modo: "modo" };

export const nivel = (s) => Math.max(1, Math.min(5, Math.round(Number(s) || 1)));

export function semAcento(s) {
  return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// ---------- filtros ↔ URL (FR-011) ----------
export function lerFiltros(busca) {
  const p = new URLSearchParams(busca || "");
  const f = { ...PADRAO };
  for (const [k, nome] of Object.entries(CHAVES)) if (p.has(nome)) f[k] = p.get(nome);
  f.sev = nivel(f.sev);
  f.uf = f.uf.toUpperCase();
  if (f.modo !== "pixels") f.modo = "municipios";
  return f;
}

export function gravarFiltros(f) {
  const p = new URLSearchParams();
  for (const [k, nome] of Object.entries(CHAVES)) if (String(f[k] ?? "") !== String(PADRAO[k])) p.set(nome, f[k]);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const filtrosAtivos = (f) => ["sev", "uf", "tipo", "fonte", "verif", "q"].filter((k) => String(f[k]) !== String(PADRAO[k])).length;

// ---------- regras (FR-008, FR-009) ----------
// UFs que a crise alcança: a do município principal e a de cada município afetado.
export function ufsDaCrise(c, ufDe) {
  const ufs = new Set(c.uf ? [c.uf] : []);
  for (const cod of [c.municipio_ibge, ...(c.municipios_afetados || [])]) {
    const uf = cod ? ufDe(Number(cod)) : null;
    if (uf) ufs.add(uf);
  }
  return ufs;
}

export function filtrar(crises, f, { ufDe = () => null, nomeDe = () => "" } = {}) {
  const termo = semAcento(f.q).trim();
  return crises.filter((c) => {
    if ((Number(c.severity) || 0) < f.sev) return false;
    if (f.tipo && c.crisis_type !== f.tipo) return false;
    if (f.fonte && c.source !== f.fonte) return false;
    if (f.verif && c.verificacao !== f.verif) return false;
    if (f.uf && !ufsDaCrise(c, ufDe).has(f.uf)) return false;
    if (termo && !semAcento(c.title).includes(termo) && !semAcento(nomeDe(Number(c.municipio_ibge))).includes(termo)) return false;
    return true;
  });
}

// ---------- números da barra lateral (FR-010) ----------
export function numeros(visiveis, ufDe = () => null) {
  const ufs = new Set();
  for (const c of visiveis) for (const uf of ufsDaCrise(c, ufDe)) ufs.add(uf);
  return {
    crises: visiveis.length,
    ufs: ufs.size,
    criticas: visiveis.filter((c) => Number(c.severity) >= 4).length,
    naoVerificadas: visiveis.filter((c) => c.verificacao === "nao_verificada").length,
  };
}

// Opções dos selects, contadas sobre todas as crises (para o usuário ver o que existe).
export function opcoes(crises, campo) {
  const n = new Map();
  for (const c of crises) if (c[campo]) n.set(c[campo], (n.get(c[campo]) || 0) + 1);
  return [...n.entries()].sort((a, b) => b[1] - a[1]);
}

// ---------- marcadores (FR-004) ----------
export const raioMarcador = (s) => 4 + 2 * nivel(s);
// Ordem de desenho: menos grave embaixo, mais grave por cima (crises na mesma coordenada continuam separadas).
export const ordemDeDesenho = (crises) => [...crises].sort((a, b) => (Number(a.severity) || 0) - (Number(b.severity) || 0));

// ---------- cor por tipo de crise ----------
// Ordem fixa dos grupos (paleta categórica validada, brasil.css --tipo-*); nunca reciclada.
export const GRUPOS = ["meteorologico", "queimada", "hidrologico", "seca", "geologico", "outros"];
const GRUPO_DO_TIPO = { meteorological: "meteorologico", wildfire: "queimada", hydrological: "hidrologico",
  drought: "seca", geological: "geologico", seismic: "geologico" };
export const grupoDe = (tipo) => GRUPO_DO_TIPO[tipo] || "outros";

// ---------- pixels (FR-005) ----------
// Alcance de cada crise: cresce com a severidade.
export const raioKm = (s) => 40 + 45 * nivel(s);

// grade: { cols, lins, lado, dentro: Uint8Array(cols*lins) } (1 = célula dentro do Brasil), em px de tela.
// focos: [{ x, y, r, sev }] cada crise visível projetada na tela, com alcance r em px.
// Devolve { foco: Int32Array (índice do foco que domina a célula, -1 = apagada), k: Float32Array (0–1) }.
// Domina a crise mais grave que alcança a célula (empate: a mais próxima). A intensidade cai até a borda.
// Só percorre as células dentro do quadrado de cada foco, recortado à tela: custo ~ área acesa, não tela × crises.
export function acender(grade, focos) {
  const { cols, lins, lado, dentro } = grade;
  const n = cols * lins;
  const foco = new Int32Array(n).fill(-1);
  const k = new Float32Array(n);
  const sev = new Uint8Array(n);
  for (let f = 0; f < focos.length; f++) {
    const F = focos[f];
    const r = Math.max(F.r, lado * 0.75), s = nivel(F.sev);
    const i0 = Math.max(0, Math.floor((F.x - r) / lado)), i1 = Math.min(cols - 1, Math.floor((F.x + r) / lado));
    const j0 = Math.max(0, Math.floor((F.y - r) / lado)), j1 = Math.min(lins - 1, Math.floor((F.y + r) / lado));
    for (let j = j0; j <= j1; j++) {
      const cy = j * lado + lado / 2, dy = cy - F.y;
      for (let i = i0; i <= i1; i++) {
        const idx = j * cols + i;
        if (!dentro[idx]) continue;
        const dx = i * lado + lado / 2 - F.x;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d > r) continue;
        const kk = 1 - d / r;
        if (foco[idx] < 0 || s > sev[idx] || (s === sev[idx] && kk > k[idx])) { foco[idx] = f; k[idx] = kk; sev[idx] = s; }
      }
    }
  }
  return { foco, k };
}
