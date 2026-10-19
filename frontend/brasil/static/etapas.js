// Dash Brasil — motor de etapas: uma etapa aberta por vez; as feitas mostram o resumo e "Editar";
// as próximas ficam travadas até a anterior terminar. Cada página só descreve as etapas.
//
// checklist(raiz, { titulo, sub, etapas, inicio: { feitas: [i], atual: i }, final: () => Node })
// etapa: { nome, pergunta, ajuda, resumo: () => texto, editar?: "Trocar", corpo(caixa, concluir) }
// Desktop: a abertura e as etapas resumidas ficam numa coluna; a etapa aberta ocupa o resto da tela.
// Celular: as colunas somem (display: contents) e a ordem (order) volta a ser a das etapas.
import { el } from "./cliente.js";

const CHECK = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 7.4 5.8 10 11 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const CADEADO = '<svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true"><rect x="2.5" y="6.2" width="9" height="6.3" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M4.6 6.2V4.6a2.4 2.4 0 0 1 4.8 0v1.6" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';

export function checklist(raiz, cfg) {
  const feitas = new Set(cfg.inicio?.feitas || []);
  const primeiraAberta = () => cfg.etapas.findIndex((_, i) => !feitas.has(i));
  const st = { atual: cfg.inicio?.atual ?? Math.max(0, primeiraAberta()), fim: primeiraAberta() < 0 && cfg.inicio?.atual == null };

  raiz.classList.add("checklist");
  function render() {
    const n = cfg.etapas.length;
    const ol = el("ol", { class: "etapas" });
    const olFoco = el("ol", { class: "etapas" });
    const lado = el("div", { class: "checklist-lado" });
    const foco = el("div", { class: "checklist-foco" }, [olFoco]);
    raiz.replaceChildren(lado, foco);
    lado.append(
      el("div", { class: "abertura", style: "order:-1" }, [
        el("h1", { texto: cfg.titulo }),
        cfg.sub ? el("p", { texto: cfg.sub }) : null,
        el("div", { class: "progresso" }, [
          el("div", { class: "trilho" }, [el("i", { style: `width:${Math.round((feitas.size / n) * 100)}%` })]),
          el("span", { texto: `${feitas.size} de ${n} concluídas` }),
        ]),
      ]),
      ol,
    );
    cfg.etapas.forEach((e, i) => {
      const atual = !st.fim && i === st.atual, feita = feitas.has(i) && !atual, travada = !feita && !atual;
      const marcador = el("span", { class: "marcador" });
      if (feita) marcador.innerHTML = CHECK; else if (travada) marcador.innerHTML = CADEADO; else marcador.textContent = String(i + 1);
      const li = el("li", { class: `etapa ${atual ? "atual" : feita ? "feita" : "travada"}`, "data-etapa": String(i), style: `order:${i}`, value: String(i + 1) }, [
        el("div", { class: "etapa-linha" }, [
          marcador,
          el("div", { class: "etapa-texto" }, [
            atual ? el("h2", { class: "etapa-titulo", texto: e.pergunta }) : el("span", { class: "etapa-titulo", texto: e.nome }),
            el("span", { class: "resumo", texto: atual ? e.ajuda : feita ? e.resumo() : `Disponível depois da etapa ${i}` }),
          ]),
          feita ? el("button", { class: "editar", type: "button", texto: e.editar || "Editar", onclick: () => abrir(i) }) : null,
        ]),
      ]);
      if (atual) {
        const corpo = el("div", { class: "etapa-corpo" });
        li.append(corpo);
        e.corpo(corpo, () => concluir(i));
      }
      (atual ? olFoco : ol).append(li);
    });
    if (st.fim && cfg.final) { const f = cfg.final(); f.style.order = "99"; foco.append(f); }
  }
  function abrir(i) { st.atual = i; st.fim = false; render(); focar(); }
  function concluir(i) {
    feitas.add(i);
    const prox = cfg.etapas.findIndex((_, j) => !feitas.has(j) && j > i);
    const resto = prox >= 0 ? prox : primeiraAberta();
    if (resto < 0) st.fim = true; else st.atual = resto;
    render(); focar();
  }
  function focar() {
    requestAnimationFrame(() => {
      const a = raiz.querySelector(".etapa.atual, .final");
      a?.scrollIntoView({ behavior: "smooth", block: "start" });
      a?.querySelector("h2, .final h2")?.setAttribute("tabindex", "-1");
      a?.querySelector("h2")?.focus({ preventScroll: true });
    });
  }
  render();
  return { abrir, concluir, render, feitas };
}

// Botão "Continuar" da etapa; `pode()` diz se já dá para seguir.
export function continuar(texto = "Continuar", pode = () => true) {
  const b = el("button", { type: "button", class: "pilula", texto });
  b.disabled = !pode();
  return b;
}
