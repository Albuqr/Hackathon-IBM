// Dash Brasil — estoque e necessidades do abrigo (ADR 0007).
// Em cima, o que precisa agora (Urgente primeiro). No meio, "Que item?": sugestões enquanto digita (lista compartilhada
// por todos os abrigos), status e quantidade; se nada servir, cria um item novo com grupo e unidade. Nome parecido com
// um item que existe aparece como "Possível duplicado de: …", com o botão para usar o existente (nunca une sozinho).
// Embaixo, a lista do abrigo por grupo. Leve para sinal fraco: uma chamada pequena por pausa na digitação.
import { el, acao, avisar, toast, data } from "./cliente.js";

const STATUS = { urgente: "Urgente", precisa: "Precisa", ok: "OK", sobrando: "Sobrando" };
const ORDEM = ["urgente", "precisa", "ok", "sobrando"];
const PEDIDO = ["urgente", "precisa"];
const NOTA_PEDIDO = "Profissionais e veículos são só pedidos, sem estoque.";
const UNIDADE = { sustento: "unidades", profissionais: "pessoas", energia_mobilidade: "litros", estrutura_ativos: "unidades" };
const num = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const linhaAcoes = (...f) => el("div", { class: "acoes" }, f);
const estado = (s) => el("span", { class: `estado ${s}`, texto: STATUS[s] || s });

// "Precisa de 200 litros" / "120 unidades" / "" (sem quantidade)
function quanto(x) {
  if (x.quantidade == null) return "";
  const q = `${num.format(x.quantidade)} ${x.unidade}`;
  return PEDIDO.includes(x.status) ? `precisa de ${q}` : q;
}

// O que mostrar depois das sugestões (regra simples, nunca une; ADR 0007):
// - mesmo nome normalizado de um item que existe ("agua" e "Água"): a API reaproveita esse item, então não há "Criar item
//   novo"; se o texto digitado não é igual ao nome mostrado (acento, maiúscula, espaço), sinaliza o item para usar;
// - sem item igual: sinaliza os parecidos que não estão na lista de sugestões e oferece criar (a partir de 2 letras).
export function sinalDuplicado(q, { itens = [], exato = null, possiveis_duplicados: dup = [] } = {}) {
  const texto = String(q || "").trim();
  if (exato != null) {
    const igual = itens.find((i) => i.id === exato) || dup.find((d) => d.id === exato);
    return { duplicados: igual && igual.nome !== texto ? [igual] : [], criar: false };
  }
  return { duplicados: dup.filter((d) => !itens.some((i) => i.id === d.id)), criar: texto.length >= 2 };
}

export function iniciarEstoque(raiz, { msg, abrigo, estoque, grupos }) {
  const S = { estoque: [...estoque] };
  const nomeGrupo = (g) => grupos.find((x) => x.id === g)?.nome || g;
  const daLista = (id) => S.estoque.find((x) => x.id === id);

  const agora = el("section", { class: "secao", "aria-labelledby": "agora-t" });
  const busca = el("input", { type: "search", id: "busca", autocomplete: "off", maxlength: "80", placeholder: "ex.: água, colchões, diesel",
    enterkeyhint: "search" });
  const sugestoes = el("div", { class: "sugestoes", "aria-live": "polite" });
  const editor = el("div", { class: "editor", hidden: true });
  const atualizar = el("section", { class: "secao", "aria-labelledby": "atualizar-t" }, [
    el("h2", { id: "atualizar-t", texto: "Atualizar um item" }),
    el("label", { class: "rotulo" }, ["Que item?", busca]), sugestoes, editor,
  ]);
  const lista = el("section", { class: "secao", "aria-labelledby": "lista-t" });
  raiz.replaceChildren(agora, atualizar, lista);

  // ---------- o que precisa agora ----------
  function linha(x) {
    return el("li", {}, [el("button", { type: "button", class: "item-linha", onclick: () => abrirItem(x) }, [
      el("div", { class: "item-texto" }, [
        el("span", { class: "item-titulo", texto: x.nome }),
        el("span", { class: "item-meta", texto: [quanto(x), x.atualizado_em ? `atualizado ${data(x.atualizado_em)}` : ""].filter(Boolean).join(" · ") }),
      ]),
      estado(x.status),
    ])]);
  }
  function renderAgora() {
    const falta = S.estoque.filter((x) => PEDIDO.includes(x.status)).sort((a, b) => PEDIDO.indexOf(a.status) - PEDIDO.indexOf(b.status));
    agora.replaceChildren(el("h2", { id: "agora-t", texto: "Precisa agora" }),
      falta.length ? el("ul", { class: "lista" }, falta.map(linha))
        : el("p", { class: "dica", texto: S.estoque.length ? "Nada urgente agora. Atualize quando algo começar a faltar." : "Nenhum item marcado ainda. Comece pelo que mais falta." }));
  }

  // ---------- lista do abrigo, por grupo ----------
  function renderLista() {
    const partes = [el("h2", { id: "lista-t", texto: "Lista do abrigo" })];
    for (const g of grupos) {
      const doGrupo = S.estoque.filter((x) => x.grupo === g.id)
        .sort((a, b) => ORDEM.indexOf(a.status) - ORDEM.indexOf(b.status) || a.nome.localeCompare(b.nome, "pt-BR"));
      if (doGrupo.length) partes.push(el("h3", { class: "grupo-t", texto: g.nome }), el("ul", { class: "lista" }, doGrupo.map(linha)));
    }
    if (partes.length === 1) partes.push(el("p", { class: "dica", texto: "A lista aparece aqui conforme você marca os itens." }));
    lista.replaceChildren(...partes);
  }
  const renderTudo = () => { renderAgora(); renderLista(); };

  // ---------- sugestões enquanto digita ----------
  let t, pedido = 0;
  async function sugerir() {
    const q = busca.value.trim();
    const meu = ++pedido;
    if (q.length < 1) { sugestoes.replaceChildren(); return; }
    const r = await acao("sugerir_itens", { q: { q } });
    if (meu !== pedido) return;  // chegou depois de outra digitação
    if (!r.ok) { sugestoes.replaceChildren(el("p", { class: "dica", texto: r.erro })); return; }
    const { itens, possiveis_duplicados: dup } = r.dados;
    const partes = [];
    if (itens.length) {
      partes.push(el("ul", { class: "lista" }, itens.map((i) => {
        const noAbrigo = daLista(i.id);
        return el("li", {}, [el("button", { type: "button", class: "item-linha", onclick: () => abrirItem(noAbrigo || i) }, [
          el("div", { class: "item-texto" }, [el("span", { class: "item-titulo", texto: i.nome }),
            el("span", { class: "item-meta", texto: `${i.grupo_nome} · ${i.unidade}` })]),
          noAbrigo ? estado(noAbrigo.status) : null,
        ])]);
      })));
    }
    const sinal = sinalDuplicado(q, r.dados);
    if (sinal.duplicados.length) partes.push(avisoDuplicado(sinal.duplicados));
    if (sinal.criar) {
      partes.push(linhaAcoes(el("button", { type: "button", class: "botao botao-secundario", texto: `Criar item novo “${q}”`,
        onclick: () => abrirNovo(q, dup) })));
    } else if (!itens.length) partes.push(el("p", { class: "dica", texto: "Nenhum item com esse nome." }));
    sugestoes.replaceChildren(...partes);
  }
  busca.addEventListener("input", () => { clearTimeout(t); t = setTimeout(sugerir, 250); });

  function avisoDuplicado(dup) {
    return el("div", { class: "duplicado", role: "status" }, [
      el("p", {}, [el("b", { texto: "Possível duplicado de: " }), dup.map((d) => d.nome).join(", ")]),
      linhaAcoes(...dup.map((d) => el("button", { type: "button", class: "botao botao-secundario botao-pequeno", texto: `Usar ${d.nome}`,
        onclick: () => abrirItem(daLista(d.id) || d) }))),
    ]);
  }

  function fechar() {
    editor.hidden = true; editor.replaceChildren();
    busca.value = ""; sugestoes.replaceChildren();
    busca.focus();
  }

  // ---------- status e quantidade de um item ----------
  function abrirItem(item, nota = null) {
    const atual = daLista(item.id);
    const pedidoSo = Boolean(item.so_necessidade);
    const opcoes = pedidoSo ? PEDIDO : ORDEM;
    const E = { status: atual && opcoes.includes(atual.status) ? atual.status : null, quantidade: atual?.quantidade ?? null };
    sugestoes.replaceChildren();
    const salvar = el("button", { type: "button", class: "botao botao-primario", texto: "Salvar" });
    const pode = () => Boolean(E.status) && (!pedidoSo || (E.quantidade != null && E.quantidade > 0));
    const chips = el("div", { class: "segmentado", role: "group", "aria-label": "Status" },
      opcoes.map((s) => el("button", { type: "button", "aria-pressed": String(E.status === s), "data-status": s, texto: STATUS[s],
        onclick: () => { E.status = s; for (const b of chips.children) b.setAttribute("aria-pressed", String(b.dataset.status === s)); salvar.disabled = !pode(); } })));
    const qtd = el("input", { type: "number", min: "0", step: "any", inputmode: "decimal", value: E.quantidade == null ? "" : String(E.quantidade),
      oninput: (e) => { const v = e.target.value.trim(); E.quantidade = v === "" ? null : Number(v); salvar.disabled = !pode(); } });
    salvar.disabled = !pode();
    salvar.addEventListener("click", async () => {
      salvar.disabled = true; salvar.textContent = "Salvando…";
      const r = await acao("atualizar_estoque", { p: { abrigo_id: abrigo.id, item_id: item.id }, corpo: { status: E.status, quantidade: E.quantidade } });
      if (!r.ok) { avisar(msg, r.erro); salvar.disabled = false; salvar.textContent = "Salvar"; return; }
      avisar(msg, "");
      S.estoque = [...S.estoque.filter((x) => x.id !== item.id), r.dados];
      renderTudo(); fechar(); toast(`${item.nome}: ${STATUS[r.dados.status]}`);
    });
    const tirar = atual ? el("button", { type: "button", class: "texto-link perigo pequeno", texto: "Tirar da lista", onclick: async (e) => {
      e.currentTarget.disabled = true;
      const r = await acao("remover_estoque", { p: { abrigo_id: abrigo.id, item_id: item.id } });
      if (!r.ok) { avisar(msg, r.erro); e.currentTarget.disabled = false; return; }
      S.estoque = S.estoque.filter((x) => x.id !== item.id);
      renderTudo(); fechar(); toast(`${item.nome} saiu da lista`);
    } }) : null;
    editor.replaceChildren(...[
      el("div", { class: "editor-topo" }, [el("h3", { texto: item.nome }), el("span", { class: "item-meta", texto: item.grupo_nome || nomeGrupo(item.grupo) })]),
      nota ? el("p", { class: "dica", texto: nota }) : null,
      el("div", { class: "rotulo" }, ["Status", chips]),
      pedidoSo ? el("p", { class: "dica", texto: NOTA_PEDIDO }) : null,
      el("label", { class: "rotulo" }, [pedidoSo ? "Quantos precisa" : "Quantidade aproximada",
        el("div", { class: "com-unidade" }, [qtd, el("span", { texto: item.unidade })])]),
      linhaAcoes(salvar, el("button", { type: "button", class: "texto-link pequeno", texto: "Cancelar", onclick: fechar }), tirar),
    ].filter(Boolean));
    editor.hidden = false;
    (E.status ? qtd : chips.firstChild).focus();
  }

  // ---------- item novo (vale para todos os abrigos) ----------
  function abrirNovo(nome, dup) {
    const N = { nome, grupo: null, unidade: "", veiculo: false };
    let unidadeMexida = false;
    sugestoes.replaceChildren();
    const criar = el("button", { type: "button", class: "botao botao-primario", texto: "Criar item" });
    const pode = () => N.nome.trim().length >= 2 && Boolean(N.grupo) && N.unidade.trim().length >= 1;
    const campoNome = el("input", { value: nome, maxlength: "80", autocomplete: "off", oninput: (e) => { N.nome = e.target.value; criar.disabled = !pode(); } });
    const unidade = el("input", { maxlength: "30", autocomplete: "off", placeholder: "ex.: litros, unidades, pessoas",
      oninput: (e) => { N.unidade = e.target.value; unidadeMexida = true; criar.disabled = !pode(); } });
    const veiculo = el("input", { type: "checkbox", onchange: (e) => { N.veiculo = e.target.checked; padraoUnidade(); } });
    const caixaVeiculo = el("label", { class: "interruptor", hidden: true }, [el("span", { texto: "É veículo?" }), veiculo]);
    const notaPedido = el("p", { class: "dica", hidden: true, texto: NOTA_PEDIDO });
    function padraoUnidade() {
      if (!unidadeMexida) { N.unidade = N.grupo === "energia_mobilidade" && N.veiculo ? "veículos" : UNIDADE[N.grupo] || ""; unidade.value = N.unidade; }
      caixaVeiculo.hidden = N.grupo !== "energia_mobilidade";
      notaPedido.hidden = !(N.grupo === "profissionais" || (N.grupo === "energia_mobilidade" && N.veiculo));
      criar.disabled = !pode();
    }
    const grupo = el("div", { class: "segmentado", role: "group", "aria-label": "Grupo" },
      grupos.map((g) => el("button", { type: "button", "aria-pressed": "false", "data-grupo": g.id, texto: g.nome,
        onclick: () => { N.grupo = g.id; for (const b of grupo.children) b.setAttribute("aria-pressed", String(b.dataset.grupo === g.id)); padraoUnidade(); } })));
    criar.disabled = true;
    criar.addEventListener("click", async () => {
      criar.disabled = true; criar.textContent = "Criando…";
      const r = await acao("criar_item", { corpo: { nome: N.nome.trim(), grupo: N.grupo, unidade: N.unidade.trim(),
        so_necessidade: N.grupo === "energia_mobilidade" ? N.veiculo : null } });
      if (!r.ok) { avisar(msg, r.erro); criar.disabled = false; criar.textContent = "Criar item"; return; }
      avisar(msg, "");
      const { item, existente, possiveis_duplicados: parecidos } = r.dados;
      const nota = existente ? `“${item.nome}” já existia na lista; usando esse.`
        : parecidos.length ? `Item criado. Parece com: ${parecidos.map((d) => d.nome).join(", ")}. Se for o mesmo, use o que já existia.`
        : "Item criado. Já aparece para os outros abrigos.";
      abrirItem(daLista(item.id) || item, nota);
    });
    editor.replaceChildren(...[
      el("div", { class: "editor-topo" }, [el("h3", { texto: "Item novo" }), el("span", { class: "item-meta", texto: "Fica disponível para todos os abrigos" })]),
      dup.length ? avisoDuplicado(dup) : null,
      el("label", { class: "rotulo" }, ["Nome do item", campoNome]),
      el("div", { class: "rotulo" }, ["Grupo", grupo]),
      caixaVeiculo, notaPedido,
      el("label", { class: "rotulo" }, ["Unidade", unidade]),
      linhaAcoes(criar, el("button", { type: "button", class: "texto-link pequeno", texto: "Cancelar", onclick: fechar })),
    ].filter(Boolean));
    editor.hidden = false;
    grupo.firstChild?.focus();
  }

  renderTudo();
}
