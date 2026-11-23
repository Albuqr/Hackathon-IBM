// Dash Brasil — pessoas do abrigo (ADR 0006): lotação, registrar chegada em etapas, saída e busca por nome.
// Leve para sinal fraco: sem mapa, sem diálogos do navegador; a confirmação de saída fica na própria linha.
// Nada aqui escreve dados de pessoas no console do navegador.
import { el, acao, avisar, data, toast } from "./cliente.js";
import { checklist, continuar } from "./etapas.js";

const NECESSIDADES = { idoso: "Idoso", deficiencia: "Pessoa com deficiência", saude: "Problema de saúde", gestante: "Gestante" };
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
const digitos = (s) => String(s || "").replace(/\D/g, "");
const cpfFormatado = (c) => (c && c.length === 11 ? `${c.slice(0, 3)}.${c.slice(3, 6)}.${c.slice(6, 9)}-${c.slice(9)}` : "");
const linhaAcoes = (...f) => el("div", { class: "acoes" }, f);
const novaPessoa = () => ({ nome: "", nome_mae: "", cpf: "", necessidades: new Set() });

export function iniciarPessoas({ abrigo, msg }) {
  const lotNum = document.getElementById("lot-num");
  const lotAviso = document.getElementById("lot-aviso");
  const lista = document.getElementById("presentes");

  function mostrarLotacao(l) {
    lotNum.textContent = `${l.presentes} de ${l.capacidade}`;
    lotAviso.hidden = !l.lotado;
    lotAviso.textContent = l.acima ? `Acima da capacidade: ${plural(l.acima, "pessoa", "pessoas")} a mais.` : "Abrigo lotado: não há vagas livres.";
  }

  // ---------- lista de presentes, por grupo familiar ----------
  function linhaPessoa(p) {
    const meta = [`Mãe: ${p.nome_mae}`, p.cpf ? `CPF ${cpfFormatado(p.cpf)}` : null, `Entrada ${data(p.entrada_em)}`]
      .concat(p.necessidades.map((n) => NECESSIDADES[n] || n)).filter(Boolean).join(" · ");
    const acoes = el("div", { class: "confirma" });
    const botaoSaida = el("button", { type: "button", class: "botao botao-secundario botao-pequeno", texto: "Registrar saída" });
    acoes.append(botaoSaida);
    botaoSaida.addEventListener("click", () => {
      const sim = el("button", { type: "button", class: "botao botao-primario botao-pequeno", texto: "Confirmar saída" });
      const nao = el("button", { type: "button", class: "texto-link pequeno", texto: "Cancelar" });
      acoes.replaceChildren(el("span", { class: "dica", texto: `Saída de ${p.nome}?` }), sim, nao);
      sim.focus();
      nao.addEventListener("click", () => { acoes.replaceChildren(botaoSaida); botaoSaida.focus(); });
      sim.addEventListener("click", async () => {
        sim.disabled = true; sim.textContent = "Registrando…";
        const r = await acao("registrar_saida", { p: { pessoa_id: p.id }, corpo: {} });
        if (!r.ok) { avisar(msg, r.erro); sim.disabled = false; sim.textContent = "Confirmar saída"; return; }
        avisar(msg, "");
        mostrarLotacao(r.dados.lotacao);
        toast("Saída registrada.");
        carregar();
      });
    });
    return el("div", { class: "pessoa", "data-pessoa": String(p.id) }, [
      el("div", { class: "item-texto" }, [el("span", { class: "item-titulo", texto: p.nome }), el("span", { class: "item-meta", texto: meta })]),
      acoes,
    ]);
  }

  async function carregar() {
    const r = await acao("pessoas_abrigo", { p: { abrigo_id: abrigo.id } });
    if (!r.ok) { lista.replaceChildren(el("li", { class: "vazio", texto: r.erro })); return; }
    mostrarLotacao(r.dados.lotacao);
    const grupos = r.dados.grupos;
    if (!grupos.length) {
      lista.replaceChildren(el("li", { class: "vazio", texto: "Ninguém presente agora. Use “Registrar chegada” quando alguém chegar." }));
      return;
    }
    lista.replaceChildren(...grupos.map((g) => el("li", { class: "grupo" }, [
      g.pessoas.length > 1 ? el("span", { class: "grupo-rotulo", texto: `Grupo familiar · ${plural(g.pessoas.length, "pessoa", "pessoas")}` }) : null,
      ...g.pessoas.map(linhaPessoa),
    ])));
  }

  // ---------- registrar chegada: Quem chegou › Necessidades especiais › Confirmar ----------
  const caixa = document.getElementById("chegada");
  const abrir = document.getElementById("abrir-chegada");
  const acoesTopo = document.getElementById("chegada-acoes");
  let P = [novaPessoa()];
  const nomeDe = (p, i) => p.nome.trim() || `Pessoa ${i + 1}`;

  function fechar() { caixa.hidden = true; caixa.replaceChildren(); acoesTopo.hidden = false; abrir.focus(); }

  const etapaQuem = {
    nome: "Quem chegou", pergunta: "Quem chegou?", ajuda: "Uma pessoa, ou todas as que chegaram juntas (família, grupo).",
    resumo: () => P.map(nomeDe).join(", "),
    corpo(c, ok) {
      const valida = (p) => p.nome.trim() && p.nome_mae.trim() && [0, 11].includes(digitos(p.cpf).length);
      const b = continuar("Continuar", () => P.every(valida));
      const atualizar = () => { b.disabled = !P.every(valida); };
      function desenhar(focarUltima = false) {
        const blocos = P.map((p, i) => {
          const erroCpf = el("p", { class: "erro-campo", "aria-live": "polite" });
          const conferirCpf = () => {
            const n = digitos(p.cpf).length;
            erroCpf.textContent = n && n !== 11 ? `O CPF tem 11 números (aqui tem ${n}). Corrija ou deixe em branco.` : "";
          };
          const campo = (rot, k, extra = {}) => el("label", { class: "rotulo" }, [rot, el("input", {
            value: p[k], maxlength: "200", autocomplete: "off", ...extra,
            oninput: (e) => { p[k] = e.target.value; if (k === "cpf") conferirCpf(); atualizar(); } })]);
          conferirCpf();
          return el("fieldset", { class: "pessoa-campos" }, [
            el("legend", { texto: P.length > 1 ? `Pessoa ${i + 1}` : "Pessoa" }),
            campo("Nome", "nome"),
            campo("Nome da mãe", "nome_mae"),
            campo("CPF (opcional)", "cpf", { inputmode: "numeric", maxlength: "14", placeholder: "só números" }),
            el("p", { class: "dica", texto: "Deixe em branco se não souber." }),
            erroCpf,
            i > 0 ? el("button", { type: "button", class: "texto-link pequeno", texto: "Tirar esta pessoa",
              onclick: () => { P.splice(i, 1); desenhar(); } }) : null,
          ]);
        });
        const mais = el("button", { type: "button", class: "botao botao-secundario", texto: "Adicionar outra pessoa do mesmo grupo",
          onclick: () => { P.push(novaPessoa()); desenhar(true); } });
        c.replaceChildren(...blocos, linhaAcoes(mais), linhaAcoes(b, el("button", { type: "button", class: "texto-link pequeno", texto: "Cancelar", onclick: fechar })));
        atualizar();
        if (focarUltima) c.querySelectorAll(".pessoa-campos")[P.length - 1]?.querySelector("input")?.focus();
      }
      b.addEventListener("click", () => {
        for (const p of P) { p.nome = p.nome.trim(); p.nome_mae = p.nome_mae.trim(); }
        ok();
      });
      desenhar();
    },
  };

  const etapaNecessidades = {
    nome: "Necessidades especiais", pergunta: "Alguém precisa de cuidado especial?", ajuda: "Marque o que valer para cada pessoa. Se ninguém, é só continuar.",
    resumo: () => {
      const n = P.filter((p) => p.necessidades.size).length;
      return n ? plural(n, "pessoa com necessidade", "pessoas com necessidades") : "Nenhuma";
    },
    corpo(c, ok) {
      const b = continuar();
      const blocos = P.map((p, i) => el("fieldset", { class: "pessoa-campos" }, [
        el("legend", { texto: nomeDe(p, i) }),
        ...Object.entries(NECESSIDADES).map(([k, rot]) => el("label", { class: "item" }, [
          el("input", { type: "checkbox", checked: p.necessidades.has(k),
            onchange: (e) => { e.target.checked ? p.necessidades.add(k) : p.necessidades.delete(k); } }),
          el("span", { texto: rot }),
        ])),
      ]));
      c.append(...blocos, linhaAcoes(b));
      b.addEventListener("click", ok);
    },
  };

  const etapaConfirmar = {
    nome: "Confirmar", pergunta: "Registrar a chegada?", ajuda: "Confira os nomes. A entrada fica com a hora de agora.",
    resumo: () => "",
    corpo(c) {
      const dl = el("dl", { class: "revisao" });
      P.forEach((p, i) => {
        const extra = [`Mãe: ${p.nome_mae}`, digitos(p.cpf) ? `CPF ${cpfFormatado(digitos(p.cpf))}` : "Sem CPF",
          ...[...p.necessidades].map((k) => NECESSIDADES[k])].join(" · ");
        dl.append(el("dt", { texto: nomeDe(p, i) }), el("dd", { texto: extra }));
      });
      const rotulo = P.length > 1 ? `Registrar ${P.length} pessoas` : "Registrar chegada";
      const b = continuar(rotulo);
      c.append(
        P.length > 1 ? el("p", { class: "dica", texto: "Elas ficam juntas como um grupo familiar." }) : null,
        dl,
        linhaAcoes(b, el("button", { type: "button", class: "texto-link pequeno", texto: "Cancelar", onclick: fechar })),
      );
      b.addEventListener("click", async () => {
        b.disabled = true; b.textContent = "Registrando…";
        const corpo = { pessoas: P.map((p) => ({ nome: p.nome, nome_mae: p.nome_mae, cpf: digitos(p.cpf) || null, necessidades: [...p.necessidades] })) };
        const r = await acao("registrar_chegada", { p: { abrigo_id: abrigo.id }, corpo });
        if (!r.ok) { avisar(msg, r.erro); b.disabled = false; b.textContent = rotulo; return; }
        const feito = `Chegada registrada: ${plural(r.dados.pessoas.length, "pessoa", "pessoas")}.`;
        avisar(msg, [feito, ...r.dados.avisos].join(" "), r.dados.avisos.length === 0);
        mostrarLotacao(r.dados.lotacao);
        P = [novaPessoa()];
        fechar();
        carregar();
      });
    },
  };

  abrir.addEventListener("click", () => {
    avisar(msg, "");
    P = [novaPessoa()];
    acoesTopo.hidden = true;
    caixa.hidden = false;
    checklist(caixa, {
      titulo: "Registrar chegada.", sub: "Três etapas curtas. Nada é salvo até a última.",
      etapas: [etapaQuem, etapaNecessidades, etapaConfirmar], inicio: { atual: 0 },
    });
  });

  // ---------- busca por nome ----------
  const busca = document.getElementById("busca");
  const resultados = document.getElementById("resultados");
  const escopo = document.getElementById("escopo");
  const ESCOPO = { todos: "Buscando em todos os abrigos, menos os sensíveis. De outros abrigos aparece só o nome.", meus_abrigos: "Buscando só nos seus abrigos até um deles ser verificado." };
  let t, pedido = 0;
  async function procurar() {
    const termo = busca.value.trim();
    const meu = ++pedido;
    if (termo.length < 2) { resultados.hidden = true; resultados.replaceChildren(); return; }
    const r = await acao("buscar_abrigados", { q: { nome: termo } });
    if (meu !== pedido) return;
    resultados.hidden = false;
    if (!r.ok) { resultados.replaceChildren(el("li", { class: "vazio", texto: r.erro })); return; }
    escopo.textContent = ESCOPO[r.dados.escopo] || escopo.textContent;
    const achados = r.dados.resultados;
    if (!achados.length) { resultados.replaceChildren(el("li", { class: "vazio", texto: "Ninguém com esse nome." })); return; }
    resultados.replaceChildren(...achados.map((x) => {
      // de outro abrigo só vêm o nome e o contato (ADR 0008)
      const meta = !x.meu_abrigo ? ["Em outro abrigo", x.contato].filter(Boolean).join(" · ") : [`Mãe: ${x.nome_mae}`,
        x.cpf ? `CPF ${cpfFormatado(x.cpf)}` : null, [x.abrigo.nome, x.abrigo.municipio].filter(Boolean).join(", "),
        `Entrada ${data(x.entrada_em)}`, x.presente ? "Presente" : `Saiu ${data(x.saida_em)}`].filter(Boolean).join(" · ");
      return el("li", {}, [el("div", { class: "item-texto" }, [el("span", { class: "item-titulo", texto: x.nome }), el("span", { class: "item-meta", texto: meta })])]);
    }));
    if (achados.length >= r.dados.limite) resultados.append(el("li", { class: "vazio", texto: `Mostrando os primeiros ${r.dados.limite}. Digite mais do nome.` }));
  }
  busca.addEventListener("input", () => { clearTimeout(t); t = setTimeout(procurar, 350); });

  carregar();
}
