// Regras puras da campanha guiada (frontend/brasil/static/campanha.js). Rodar: node --test frontend/brasil/tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { lerPlano, temPlano, motivos, cobertura, preSelecionar } from "../static/campanha.js";

test("lerPlano lê o formato do assistant_agent e normaliza a urgência", () => {
  const p = lerPlano(`Resumo da necessidade: Evento hidrológico em São Borja (RS), severidade 4.
Habilidades necessárias: resgate, abrigo, logística e primeiros socorros
Número de voluntários recomendado: 20
Urgência: **Média**
Descrição da campanha: Apoio às famílias atingidas,
em turnos com a Defesa Civil.`);
  assert.deepEqual(p.habilidades, ["resgate", "abrigo", "logística", "primeiros socorros"]);
  assert.equal(p.voluntarios, 20);
  assert.equal(p.urgencia, "media");
  assert.match(p.descricao, /^Apoio às famílias atingidas,\nem turnos/);
  assert.ok(temPlano(p));
});

test("lerPlano devolve null no que não aparece; texto solto não vira plano", () => {
  const p = lerPlano("Sugiro começar pelos abrigos. - Urgência: crítica");
  assert.equal(p.urgencia, "critica");
  assert.equal(p.habilidades, null);
  assert.equal(temPlano(lerPlano("Olá! Como posso ajudar?")), false);
});

test("motivos explicam o score do matching", () => {
  assert.deepEqual(motivos({ habilidades_comuns: ["resgate"], distancia_km: 12.4, historico: true, avisado_24h: true }),
    ["resgate", "12 km", "já atuou antes", "avisado(a) nas últimas 24 h"]);
  assert.deepEqual(motivos({ habilidades_comuns: [], distancia_km: null }), ["sem habilidade do plano"]);
});

test("cobertura conta pessoas por habilidade, sem meta rígida, ignorando acento", () => {
  const cob = cobertura(["logística", "abrigo"], [{ skills: ["Logistica"] }, { habilidades_comuns: ["logística"] }]);
  assert.deepEqual(cob, [{ habilidade: "logística", pessoas: 2 }, { habilidade: "abrigo", pessoas: 0 }]);
});

test("preSelecionar marca os primeiros até a meta", () => {
  const r = [1, 2, 3].map((volunteer_id) => ({ volunteer_id }));
  assert.deepEqual(preSelecionar(r, 2), [1, 2]);
  assert.deepEqual(preSelecionar(r, 10), [1, 2, 3]);
});
