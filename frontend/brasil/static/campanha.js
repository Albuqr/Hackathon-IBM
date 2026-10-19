// Dash Brasil — regras puras da campanha guiada (sem DOM): ler o plano que o assistente escreveu,
// explicar o matching, contar quem cobre cada habilidade e marcar os recomendados até a meta.
import { semAcento } from "./visao.js";

export const URGENCIAS = ["baixa", "media", "alta", "critica"];
const URG = { baixa: "baixa", media: "media", alta: "alta", critica: "critica" };

// Habilidades oferecidas nos chips (as do assistente por tipo de crise e as que os voluntários mais usam).
export const HABILIDADES = ["resgate", "primeiros socorros", "logística", "abrigo", "saúde", "enfermagem", "medicina", "engenharia",
  "combate a incêndio", "brigadista", "distribuição de água", "assistência social", "comunicação", "motorista", "cozinha", "psicologia"];

// Lê o plano no formato do assistant_agent ("Habilidades necessárias: …", "Número de voluntários recomendado: …",
// "Urgência: …", "Descrição da campanha: …"). Campos que não aparecem voltam null.
export function lerPlano(texto) {
  const t = String(texto || "").replace(/\*\*/g, "").replace(/^\s*[-•*]\s*/gm, "");
  const linha = (re) => { const m = t.match(re); return m ? m[1].trim() : null; };
  const habs = linha(/habilidades[^:\n]*:\s*(.+)/i);
  const num = linha(/volunt[áa]rios[^:\n]*:\s*(\d+)/i);
  const urg = linha(/urg[êe]ncia[^:\n]*:\s*([^\s.,;]+)/i);
  const desc = t.match(/descri[çc][ãa]o[^:\n]*:\s*([\s\S]+?)(?=\n\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^:\n]{2,40}:|$)/i);
  const urgencia = urg ? URG[semAcento(urg)] || null : null;
  return {
    habilidades: habs ? habs.split(/,|;| e /).map((s) => s.trim().replace(/\.$/, "")).filter(Boolean) : null,
    voluntarios: num ? Number(num) : null,
    urgencia,
    descricao: desc ? desc[1].trim() : null,
  };
}
export const temPlano = (p) => Boolean(p && (p.habilidades?.length || p.voluntarios || p.urgencia || p.descricao));

// Os motivos do score, em português, a partir do que a API de matching devolve.
export function motivos(m) {
  const out = [m.habilidades_comuns?.length ? m.habilidades_comuns.join(", ") : "sem habilidade do plano"];
  if (m.distancia_km != null) out.push(`${Math.round(m.distancia_km)} km`);
  if (m.historico) out.push("já atuou antes");
  if (m.avisado_24h) out.push("avisado(a) nas últimas 24 h");
  return out;
}

// Quantas pessoas escolhidas têm cada habilidade do plano. Sem meta por habilidade: só aponta as descobertas.
export function cobertura(habilidades, pessoas) {
  return habilidades.map((h) => {
    const n = semAcento(h);
    return { habilidade: h, pessoas: pessoas.filter((p) => (p.skills || p.habilidades_comuns || []).some((s) => semAcento(s) === n)).length };
  });
}

// Os recomendados já vêm marcados até a meta (na ordem do matching).
export const preSelecionar = (ranking, meta) => ranking.slice(0, Math.max(0, meta)).map((m) => m.volunteer_id);
