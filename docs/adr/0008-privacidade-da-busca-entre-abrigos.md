# 0008 — Privacidade da busca entre abrigos (emenda a 0006)
status: accepted · date: 2026-11-18

## Context
A ADR 0006 abriu a busca em todos os abrigos para o gestor com algum abrigo verificado, e cada resultado de outro abrigo trazia nome, nome da mãe, abrigo (id, nome, município), entrada, saída e se a pessoa estava presente. Ficaram abertas duas questões: abrigos sensíveis ainda apareciam na busca, e quem já tinha saído também. Para quem está num abrigo de proteção (mulheres, crianças), "onde está" e "desde quando" são exatamente o que não pode vazar: um gestor verificado não é garantia de que quem procura alguém quer o bem dessa pessoa. O João decidiu as regras abaixo. O abrigo não tem campo de tipo (mulheres, crianças...) nem contato público; tem só o `sensivel`, marcado pelo próprio gestor (ADR 0005).

## Options considered
| Option | Pros | Cons | Fit |
|---|---|---|---|
| Abrigo sensível fora da busca de outros gestores; de outros abrigos só nome + caminho de contato; quem saiu não aparece; toda busca entre abrigos registrada no banco | ninguém descobre por busca onde está quem é protegido; o reencontro passa por uma pessoa (coordenação); dá para auditar abuso | mais um passo para reunir famílias; registro guarda nomes buscados | atende (decisão do João) |
| Manter a 0006 (nome da mãe, abrigo, datas) | reencontro mais rápido | entrega o endereço de quem foge de alguém | inseguro |
| Mostrar abrigo sensível com dados ocultos ("pessoa em abrigo protegido") | o gestor sabe que a pessoa está viva e abrigada | confirma a quem procura que a pessoa está num abrigo de proteção | não serve |
| Campo novo de tipo de abrigo ou de contato público | regra mais fina por tipo; contato direto | muda o esquema e o cadastro; o `sensivel` já cobre o caso | não agora |
| Registro só em log do servidor (print/logging) | sem tabela nova | logs não guardam dados de pessoas (regra do brief); não sobrevive ao merge | não serve |

## Decision
- Abrigo sensível (`abrigos.sensivel = 1`, flag que já existe; sem coluna nova) nunca entra na busca de outros gestores, verificados ou não. O gestor dono continua achando a própria gente como antes. A semente marca a "Casa de Acolhimento de Teste" como sensível.
- De abrigo de outro gestor (não sensível), a busca devolve só `{"nome", "meu_abrigo": false, "contato"}`, com `contato` fixo: "Entre em contato com a coordenação regional." (`CONTATO_OUTRO_ABRIGO` em `abrigados.py`). Não vão nome da mãe, CPF, abrigo (id, nome, município), entrada, saída nem presença. Quem já saiu não aparece para outros gestores.
- A visão do dono não muda: nos próprios abrigos a busca traz nome, nome da mãe, CPF, abrigo, entrada, saída e presença (incluindo quem saiu), e a tela de pessoas segue igual.
- Toda busca feita com escopo `todos` (o gestor tem algum abrigo verificado) grava uma linha em `buscas_abrigados_log` (id, user_id, consulta, buscado_em em UTC ISO, resultados, origem), mesmo com zero resultados. Busca só nos próprios abrigos (`meus_abrigos`) não é registrada; busca recusada (menos de 2 letras) também não. A consulta é guardada como digitada (espaços simples, até 200 caracteres); `resultados` é o total devolvido.
- Ninguém lê o registro pelo sistema: nenhuma rota da API, ação da `POLITICA` ou página o expõe, e nada é impresso. A tabela é só do Brasil e entra em `ORDEM`/`REFERENCIAS` do merge (`user_id` → `users`), então a trilha sobrevive ao merge (ADR 0002).
- A tela de pessoas mostra o resultado de outro abrigo como nome + "Em outro abrigo · <contato>", e a linha de escopo diz "Buscando em todos os abrigos, menos os sensíveis. De outros abrigos aparece só o nome."

## Consequences
Positivo: busca não revela onde está nem desde quando está quem é protegido; um gestor que use a busca para procurar alguém fica registrado. Negativo: reunir famílias depende da coordenação regional, que ainda não tem canal no sistema; homônimos de outros abrigos ficam indistinguíveis (sem nome da mãe); o registro guarda nomes buscados, então é dado pessoal e precisa de prazo de guarda e de quem pode consultá-lo, ainda não decididos. Também ainda não decidido: o resultado de outro abrigo implica que a pessoa está presente em algum abrigo, porque quem saiu é excluído. Futuro: contato público do abrigo ou canal da coordenação, e uma tela de auditoria para quem for definido (fora do papel `gestor_abrigo`).

## Emendas (revisão da onda 1)
- A busca é `POST /brasil/abrigados/busca` com `{"nome": ...}` no corpo (era `GET ...?nome=`): a URL vai para o log de acesso do servidor, e nome de abrigado não pode ir para log.
