// Dash Brasil — cliente de página (candidato 3 do relatório de arquitetura).
// Tudo que as páginas repetiam: construir DOM, falar com o encaminhador (/brasil/acao/<nome>) com erro legível,
// rótulos e cores de crise, datas, tema, barra lateral e badge de convites. Sem estado de página.

export const TIPOS = {
  wildfire: "Queimada", meteorological: "Meteorológico", hydrological: "Hidrológico", geological: "Geológico",
  seismic: "Sísmico", drought: "Seca", humanitarian: "Humanitário", conflict: "Conflito", sanitary: "Sanitário",
};
export const FONTES = {
  inpe: "INPE", cemaden: "CEMADEN", inmet: "INMET", noticias: "Notícias", usgs: "USGS", gdacs: "GDACS",
  eonet: "NASA EONET", reliefweb: "ReliefWeb", gdelt: "GDELT",
};
export const SEVERIDADE = { 1: "Baixa", 2: "Moderada", 3: "Alta", 4: "Crítica", 5: "Extrema" };
export const CONVITE = { selected: "Convite pendente", confirmed: "Confirmado", declined: "Recusado" };
export const URGENCIA = { baixa: "Baixa", media: "Média", alta: "Alta", critica: "Crítica" };
export const VERIFICACAO = { verificada: "Verificada", nao_verificada: "Não verificada" };

export const rotulo = (dic, k) => dic[k] || (k ? String(k) : "—");
export const nivel = (s) => Math.max(1, Math.min(5, Math.round(Number(s) || 1)));

const fmtData = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
export function data(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : fmtData.format(d);
}

export function el(tag, attrs = {}, filhos = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "texto") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  n.append(...[].concat(filhos).filter((c) => c != null && c !== false));
  return n;
}

// Selo de severidade colorido pela escala do tema.
export const selSev = (s) => el("span", { class: `sev s${nivel(s)}`, style: `background:var(--sev${nivel(s)})`, title: `Severidade ${nivel(s)}`, texto: String(nivel(s)) });

// Mensagem legível para qualquer falha (inclui respostas que não são JSON, ex.: 502 do proxy).
export function mensagemDeErro(status, corpo) {
  const d = corpo && corpo.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0]?.msg) return d.map((x) => x.msg).join("; ");
  if (status === 401) return "Sua sessão expirou. Entre de novo.";
  if (status === 403) return "Seu perfil não pode fazer isto.";
  if (status >= 500 || status === 0) return "Serviço indisponível no momento. Tente de novo.";
  return `Não foi possível concluir (erro ${status}).`;
}

// Chama o encaminhador. Devolve { ok, status, dados, erro } e nunca lança.
export async function acao(nome, { p, q, corpo } = {}) {
  let r;
  try {
    r = await fetch(`/brasil/acao/${encodeURIComponent(nome)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ p, q, corpo }),
    });
  } catch {
    return { ok: false, status: 0, dados: null, erro: mensagemDeErro(0) };
  }
  let dados = null;
  try { dados = await r.json(); } catch { /* corpo não-JSON */ }
  return r.ok ? { ok: true, status: r.status, dados, erro: null } : { ok: false, status: r.status, dados, erro: mensagemDeErro(r.status, dados) };
}

// Mostra um aviso (ok/erro) num elemento .aviso.
export function avisar(alvo, texto, ok = false) {
  if (!alvo) return;
  alvo.hidden = !texto;
  alvo.className = ok ? "aviso ok" : "aviso";
  alvo.textContent = texto || "";
}

export function distanciaKm(a, b) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

// ---------- shell: tema, barra lateral, menu, badge, status da coleta ----------
const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch { /* sem armazenamento */ } };
const ler = (k) => { try { return localStorage.getItem(k); } catch { return null; } };

export function temaAtual() { return document.documentElement.dataset.theme || "light"; }
export function aplicarTema(t) {
  document.documentElement.dataset.theme = t;
  document.dispatchEvent(new CustomEvent("br:tema", { detail: t }));
}

export function iniciarShell() {
  const corpo = document.body;
  // barra lateral recolhível, lembrada (FR-001); no celular começa fechada
  const lateral = document.getElementById("lateral");
  if (lateral) {
    const salvo = ler("br-lateral");
    if (salvo === "fechada" || (salvo == null && window.matchMedia("(max-width: 860px)").matches)) corpo.classList.add("recolhida");
    const botao = document.getElementById("alternar-lateral");
    const sincronizar = () => {
      const fechada = corpo.classList.contains("recolhida");
      botao?.setAttribute("aria-expanded", String(!fechada));
      botao?.setAttribute("aria-label", fechada ? "Mostrar barra lateral" : "Recolher barra lateral");
    };
    botao?.addEventListener("click", () => {
      corpo.classList.toggle("recolhida");
      guardar("br-lateral", corpo.classList.contains("recolhida") ? "fechada" : "aberta");
      sincronizar();
      setTimeout(() => window.dispatchEvent(new Event("resize")), 220);
    });
    sincronizar();
  }
  // tema (FR-021): o script do <head> já aplicou o salvo ou o do sistema
  document.getElementById("alternar-tema")?.addEventListener("click", () => {
    const novo = temaAtual() === "dark" ? "light" : "dark";
    guardar("br-tema", novo);
    aplicarTema(novo);
  });
  // menu no celular
  const menu = document.getElementById("menu");
  document.getElementById("menu-botao")?.addEventListener("click", (e) => {
    const aberto = menu.classList.toggle("aberto");
    e.currentTarget.setAttribute("aria-expanded", String(aberto));
  });
  // badge de convites pendentes (FR-016)
  const badge = document.getElementById("badge-convites");
  if (badge) {
    acao("meus_convites").then(({ ok, dados }) => {
      const n = ok && Array.isArray(dados) ? dados.filter((c) => c.status === "selected").length : 0;
      badge.textContent = String(n);
      badge.hidden = n === 0;
    });
  }
  atualizarStatusColeta();
}

// Barra de status: hora e resultado da última coleta (FR-012).
export async function atualizarStatusColeta() {
  const alvo = document.getElementById("status-coleta");
  if (!alvo) return;
  const { ok, dados } = await acao("status_coleta");
  if (!ok || !Array.isArray(dados) || !dados.length) { alvo.textContent = ok ? "Nenhuma coleta ainda" : "Status da coleta indisponível"; return; }
  const ultima = dados.map((s) => s.tentativa_em).filter(Boolean).sort().pop();
  const okN = dados.filter((s) => s.ok).length;
  alvo.textContent = `Última coleta ${data(ultima)} · ${okN} de ${dados.length} fontes ok`;
}
