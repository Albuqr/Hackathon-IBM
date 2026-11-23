// Regra do aviso de possível duplicado no estoque (frontend/brasil/static/estoque.js). Rodar: node --test frontend/brasil/tests/estoque.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { sinalDuplicado } from "../static/estoque.js";

const agua = { id: 1, nome: "Água" };
const mineral = { id: 2, nome: "Água mineral" };
const garrafa = { id: 3, nome: "Garrafa de água" };

test("'agua' com 'Água' na lista: sinaliza Água e não oferece criar (a API reaproveita o item)", () => {
  const r = sinalDuplicado("agua", { itens: [agua, garrafa], exato: 1, possiveis_duplicados: [agua, mineral] });
  assert.deepEqual(r, { duplicados: [agua], criar: false });
});

test("diferença só de maiúscula ou espaço também sinaliza", () => {
  for (const q of ["ÁGUA", "água", "  Água  mineral "]) {
    const ex = q.includes("mineral") ? mineral : agua;
    const r = sinalDuplicado(q, { itens: [ex], exato: ex.id, possiveis_duplicados: [ex] });
    assert.deepEqual(r.duplicados, [ex], q);
    assert.equal(r.criar, false);
  }
});

test("digitou exatamente o nome mostrado: sem aviso e sem criar", () => {
  assert.deepEqual(sinalDuplicado(" Água ", { itens: [agua], exato: 1, possiveis_duplicados: [agua, mineral] }),
    { duplicados: [], criar: false });
});

test("item igual fora das sugestões ainda é achado nos duplicados", () => {
  assert.deepEqual(sinalDuplicado("agua", { itens: [], exato: 1, possiveis_duplicados: [agua] }).duplicados, [agua]);
});

test("sem item igual: só os parecidos fora da lista de sugestões, e criar a partir de 2 letras", () => {
  assert.deepEqual(sinalDuplicado("aguas", { itens: [mineral], exato: null, possiveis_duplicados: [agua, mineral] }),
    { duplicados: [agua], criar: true });
  assert.deepEqual(sinalDuplicado("a", { itens: [], exato: null, possiveis_duplicados: [] }), { duplicados: [], criar: false });
});
