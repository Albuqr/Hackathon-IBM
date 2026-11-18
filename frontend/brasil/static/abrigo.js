// Dash Brasil — gestor de abrigo (ADR 0005): cadastrar/editar o abrigo em etapas e o botão de verificação de teste.
// Leve para sinal fraco: sem mapa; o local vem do GPS do navegador ou de lat/lon digitados, e a API devolve o município.
import { el, acao, avisar } from "./cliente.js";
import { checklist, continuar } from "./etapas.js";

const TIPO = { temporario: "Temporário", permanente: "Permanente" };
const linhaAcoes = (...f) => el("div", { class: "acoes" }, f);
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

// raiz: onde montar as etapas · msg: elemento .aviso · editar: abrigo vindo da API (ou null para criar) · painel: URL do painel
export function iniciarCadastro(raiz, { msg, editar = null, painel }) {
  const A = editar
    ? { nome: editar.nome, tipo: editar.tipo, endereco: editar.endereco || "", lat: editar.lat, lon: editar.lon,
        lugar: { municipio: editar.municipio, uf: editar.uf }, capacidade: editar.capacidade, ativo: editar.ativo,
        sensivel: editar.sensivel, crises: new Map(editar.crises.map((c) => [c.id, c])) }
    : { nome: "", tipo: "temporario", endereco: "", lat: null, lon: null, lugar: null, capacidade: 50, ativo: true,
        sensivel: false, crises: new Map() };
  const lugarTexto = () => (A.lugar ? [A.lugar.municipio, A.lugar.uf].filter(Boolean).join(" · ") : "");

  // ---------- 1. nome e tipo ----------
  const etapaNome = {
    nome: "Nome e tipo", pergunta: "Como o abrigo se chama?", ajuda: "O nome que as equipes e as famílias conhecem.",
    resumo: () => `${A.nome} · ${TIPO[A.tipo]}`,
    corpo(c, ok) {
      const pode = () => A.nome.trim().length >= 2;
      const b = continuar("Continuar", pode);
      const nome = el("input", { value: A.nome, maxlength: "200", autocomplete: "off", placeholder: "ex.: Ginásio Municipal",
        oninput: (e) => { A.nome = e.target.value; b.disabled = !pode(); } });
      const tipo = el("div", { class: "segmentado", role: "group", "aria-label": "Tipo de abrigo" },
        Object.entries(TIPO).map(([k, v]) => el("button", { type: "button", "aria-pressed": String(A.tipo === k), texto: v,
          onclick: () => { A.tipo = k; for (const x of tipo.children) x.setAttribute("aria-pressed", String(x.textContent === v)); } })));
      c.append(el("label", { class: "rotulo" }, ["Nome do abrigo", nome]), el("div", { class: "rotulo" }, ["Tipo", tipo]),
        el("p", { class: "dica", texto: "Temporário: montado para esta crise (escola, ginásio). Permanente: abrigo que já existia." }), linhaAcoes(b));
      b.addEventListener("click", () => { A.nome = A.nome.trim(); ok(); });
    },
  };

  // ---------- 2. local ----------
  const etapaLocal = {
    nome: "Local", pergunta: "Onde fica?", ajuda: "Use a localização do celular estando no abrigo, ou digite latitude e longitude.",
    resumo: () => [lugarTexto(), A.endereco].filter(Boolean).join(" · "),
    corpo(c, ok) {
      const b = continuar("Continuar", () => Boolean(A.lugar));
      const endereco = el("input", { value: A.endereco, maxlength: "300", autocomplete: "street-address", placeholder: "ex.: Rua das Flores, 100, Centro",
        oninput: (e) => { A.endereco = e.target.value; } });
      const num = (v, rot) => el("input", { type: "number", step: "any", inputmode: "decimal", value: v == null ? "" : String(v), "aria-label": rot });
      const lat = num(A.lat, "Latitude"), lon = num(A.lon, "Longitude");
      const achado = el("p", { class: "municipio-achado", "aria-live": "polite" });
      const gps = el("button", { type: "button", class: "botao botao-secundario", texto: "Usar minha localização" });
      const mostrar = (texto, falta = false) => { achado.textContent = texto; achado.classList.toggle("falta", falta); };
      if (A.lugar) mostrar(`Município: ${lugarTexto()}`);
      else mostrar("Informe o local para ver o município.", true);
      let t, pedido = 0;
      async function conferir() {
        const la = Number(lat.value), lo = Number(lon.value);
        A.lugar = null; b.disabled = true;
        if (lat.value === "" || lon.value === "" || !Number.isFinite(la) || !Number.isFinite(lo)) { mostrar("Informe latitude e longitude.", true); return; }
        A.lat = la; A.lon = lo;
        const meu = ++pedido;
        mostrar("Procurando o município…", true);
        const r = await acao("municipio_abrigo", { q: { lat: la, lon: lo } });
        if (meu !== pedido) return;
        if (!r.ok) { mostrar(r.erro, true); return; }
        A.lugar = r.dados;
        mostrar(`Município: ${lugarTexto()}`);
        b.disabled = false;
      }
      const depois = () => { clearTimeout(t); t = setTimeout(conferir, 400); };
      lat.addEventListener("input", depois); lon.addEventListener("input", depois);
      gps.addEventListener("click", () => {
        if (!navigator.geolocation) { mostrar("Este navegador não informa a localização. Digite latitude e longitude.", true); return; }
        gps.disabled = true; gps.textContent = "Localizando…";
        navigator.geolocation.getCurrentPosition((p) => {
          gps.disabled = false; gps.textContent = "Usar minha localização";
          lat.value = p.coords.latitude.toFixed(5); lon.value = p.coords.longitude.toFixed(5);
          conferir();
        }, () => {
          gps.disabled = false; gps.textContent = "Usar minha localização";
          mostrar("Não foi possível pegar a localização. Permita o acesso ou digite latitude e longitude.", true);
        }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 });
      });
      c.append(el("label", { class: "rotulo" }, ["Endereço", endereco]), linhaAcoes(gps),
        el("div", { class: "linha" }, [el("label", { class: "rotulo" }, ["Latitude", lat]), el("label", { class: "rotulo" }, ["Longitude", lon])]),
        achado, linhaAcoes(b));
      b.addEventListener("click", () => { A.endereco = A.endereco.trim(); ok(); });
    },
  };

  // ---------- 3. capacidade ----------
  const etapaCapacidade = {
    nome: "Capacidade", pergunta: "Quantas pessoas cabem?", ajuda: "Quantas pessoas o abrigo consegue receber para dormir.",
    resumo: () => plural(A.capacidade, "pessoa", "pessoas"),
    corpo(c, ok) {
      const pode = () => Number.isInteger(A.capacidade) && A.capacidade > 0;
      const b = continuar("Continuar", pode);
      const cap = el("input", { type: "number", min: "1", max: "100000", step: "1", inputmode: "numeric", value: String(A.capacidade),
        oninput: (e) => { A.capacidade = Number(e.target.value); b.disabled = !pode(); } });
      c.append(el("label", { class: "rotulo" }, ["Capacidade (pessoas)", cap]), linhaAcoes(b));
      b.addEventListener("click", ok);
    },
  };

  // ---------- 4. situação ----------
  const etapaSituacao = {
    nome: "Situação", pergunta: "Como está o abrigo agora?", ajuda: "Dá para mudar depois, a qualquer momento.",
    resumo: () => [A.ativo ? "Ativo" : "Inativo", A.sensivel ? "sensível" : null].filter(Boolean).join(" · "),
    corpo(c, ok) {
      const ativo = el("input", { type: "checkbox", checked: A.ativo, onchange: (e) => { A.ativo = e.target.checked; } });
      const sensivel = el("input", { type: "checkbox", checked: A.sensivel, onchange: (e) => { A.sensivel = e.target.checked; } });
      const b = continuar();
      c.append(el("label", { class: "interruptor" }, [el("span", { texto: "Ativo, recebendo pessoas" }), ativo]),
        el("label", { class: "interruptor" }, [el("span", { texto: "Abrigo sensível" }), sensivel]),
        el("p", { class: "dica", texto: "Sensível: o local não deve ser divulgado em público. Por enquanto a marcação fica só guardada." }),
        linhaAcoes(b));
      b.addEventListener("click", ok);
    },
  };

  // ---------- 5. crises (opcional) ----------
  const etapaCrises = {
    nome: "Crises", pergunta: "Atende a alguma crise?", ajuda: "Opcional. Marque as crises cujas famílias o abrigo recebe.",
    resumo: () => (A.crises.size ? plural(A.crises.size, "crise vinculada", "crises vinculadas") : "Nenhuma crise vinculada"),
    async corpo(c, ok) {
      const b = continuar(A.crises.size ? "Continuar" : "Pular");
      const atualizarBotao = () => { b.textContent = A.crises.size ? "Continuar" : "Pular"; };
      const busca = el("input", { type: "search", placeholder: "ex.: chuva Porto Alegre", autocomplete: "off", "aria-label": "Buscar crise" });
      const lista = el("ul", { class: "lista" }, [el("li", { class: "vazio", texto: "Carregando crises…" })]);
      const linha = (x) => el("label", { class: "item" }, [
        el("input", { type: "checkbox", checked: A.crises.has(x.id), onchange: (e) => { e.target.checked ? A.crises.set(x.id, x) : A.crises.delete(x.id); atualizarBotao(); } }),
        el("div", { class: "item-texto" }, [el("span", { class: "item-titulo", texto: x.title }), el("span", { class: "item-meta", texto: x.uf || "" })]),
      ]);
      async function carregar() {
        const q = busca.value.trim();
        const r = await acao("crises", { q: q ? { q, limite: 20 } : { uf: A.lugar?.uf || "", limite: 15 } });
        const achadas = r.ok ? r.dados : [];
        const marcadas = [...A.crises.values()].filter((x) => !achadas.some((y) => y.id === x.id));
        lista.replaceChildren(...([...marcadas, ...achadas].length ? [...marcadas, ...achadas].map(linha)
          : [el("li", { class: "vazio", texto: r.ok ? (q ? "Nenhuma crise com esse nome." : "Nenhuma crise ativa na sua UF agora.") : r.erro })]));
      }
      let t;
      busca.addEventListener("input", () => { clearTimeout(t); t = setTimeout(carregar, 300); });
      c.append(el("label", { class: "rotulo" }, [A.lugar?.uf ? `Crises ativas em ${A.lugar.uf}, ou busque outra` : "Busque a crise", busca]), lista, linhaAcoes(b));
      b.addEventListener("click", ok);
      await carregar();
    },
  };

  // ---------- 6. criar ----------
  const etapaCriar = {
    nome: editar ? "Salvar" : "Criar", pergunta: editar ? "Salvar as mudanças?" : "Tudo certo?",
    ajuda: editar ? "As mudanças valem na hora." : "O abrigo já funciona assim que for criado, marcado como não verificado.",
    resumo: () => "",
    corpo(c) {
      const dl = el("dl", { class: "revisao" });
      for (const [k, v] of [["Abrigo", `${A.nome} · ${TIPO[A.tipo]}`], ["Local", [lugarTexto(), A.endereco].filter(Boolean).join(" · ")],
        ["Capacidade", plural(A.capacidade, "pessoa", "pessoas")], ["Situação", etapaSituacao.resumo()],
        ["Crises", A.crises.size ? [...A.crises.values()].map((x) => x.title).join(", ") : "Nenhuma"]]) dl.append(el("dt", { texto: k }), el("dd", { texto: v }));
      const rotuloBotao = editar ? "Salvar alterações" : "Criar abrigo";
      const b = continuar(rotuloBotao);
      c.append(dl, linhaAcoes(b, el("a", { class: "texto-link pequeno", href: painel, texto: "Cancelar" })));
      b.addEventListener("click", async () => {
        b.disabled = true; b.textContent = editar ? "Salvando…" : "Criando…";
        const corpo = { nome: A.nome, endereco: A.endereco, lat: A.lat, lon: A.lon, capacidade: A.capacidade, tipo: A.tipo,
          ativo: A.ativo, sensivel: A.sensivel, crises: [...A.crises.keys()] };
        const r = editar ? await acao("editar_abrigo", { p: { abrigo_id: editar.id }, corpo }) : await acao("criar_abrigo", { corpo });
        if (!r.ok) { avisar(msg, r.erro); b.disabled = false; b.textContent = rotuloBotao; return; }
        location.href = `${painel}?${editar ? "salvo" : "criado"}=${r.dados.id}`;
      });
    },
  };

  const etapas = [etapaNome, etapaLocal, etapaCapacidade, etapaSituacao, etapaCrises, etapaCriar];
  checklist(raiz, {
    titulo: editar ? "Editar abrigo." : "Cadastrar abrigo.",
    sub: editar ? "Abra a etapa que quer mudar e salve no fim." : "Seis etapas curtas. Nada é salvo até a última.",
    etapas,
    inicio: editar ? { feitas: [0, 1, 2, 3, 4], atual: 5 } : { atual: 0 },
  });
}

// Botões "Marcar como verificado" (só com o login de teste ligado; a API também confere).
export function iniciarPainel({ msg }) {
  for (const b of document.querySelectorAll("[data-verificar]")) {
    b.addEventListener("click", async () => {
      b.disabled = true;
      const r = await acao("dev_verificar_abrigo", { p: { abrigo_id: b.dataset.verificar } });
      if (!r.ok) { avisar(msg, r.erro); b.disabled = false; return; }
      location.reload();
    });
  }
}
