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

// ---------- pixels (FR-005) ----------
// Alcance de cada crise: cresce com a severidade.
export const raioKm = (s) => 25 + 35 * nivel(s);

// celulas: [{x, y}] centros dos pixels (já recortados ao Brasil), em px de tela.
// focos: [{x, y, r, sev, id}] cada crise visível projetada na tela, com alcance r em px.
// Devolve, para cada célula, null (apagada) ou { sev, k (0–1), id } da crise mais grave que a alcança
// (empate: a mais próxima). A intensidade cai linearmente até a borda do alcance.
export function acender(celulas, focos, lado = 7) {
  const saida = new Array(celulas.length).fill(null);
  if (!focos.length || !celulas.length) return saida;
  const indice = new Map();
  celulas.forEach((c, i) => indice.set(`${Math.floor(c.x / lado)}:${Math.floor(c.y / lado)}`, i));
  for (const f of focos) {
    const r = Math.max(f.r, lado * 0.75);
    const i0 = Math.floor((f.x - r) / lado), i1 = Math.floor((f.x + r) / lado);
    const j0 = Math.floor((f.y - r) / lado), j1 = Math.floor((f.y + r) / lado);
    for (let i = i0; i <= i1; i++) {
      for (let j = j0; j <= j1; j++) {
        const idx = indice.get(`${i}:${j}`);
        if (idx === undefined) continue;
        const c = celulas[idx];
        const d = Math.hypot(c.x - f.x, c.y - f.y);
        if (d > r) continue;
        const k = 1 - d / r;
        const atual = saida[idx];
        const sev = nivel(f.sev);
        if (!atual || sev > atual.sev || (sev === atual.sev && k > atual.k)) saida[idx] = { sev, k, id: f.id };
      }
    }
  }
  return saida;
}

// Célula da grade sob um ponto de tela (para clique/hover nos pixels).
export const celulaEm = (x, y, lado = 7) => `${Math.floor(x / lado)}:${Math.floor(y / lado)}`;
