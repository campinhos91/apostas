# Apostas do dia

Gerador de uma página diária de apostas ("Apostas do dia"), com histórico e
estatísticas, disponível como página (`apostas-do-dia.html`) e como app instalável
(PWA). Tudo — página e dados da app — sai de **um único** ficheiro de
dados do dia (`dados.json`) e de **um único** script (`gerar.py`); nada é
escrito à mão.

## Estrutura do repositório

```
apostas-template/
  gerar.py            script gerador: página e dados da app
  epocas.py           resultados de épocas passadas: estatísticas por jogo e probabilidade dos boletins
  epocas/             dados descarregados por epocas.py (clubes.csv, selecoes.csv) e alias.json
  bilhetes.html        <head>/CSS de referência da página + um exemplo estático
  dados_atual.json     cópia do último dados.json usado (gerada automaticamente)
  dados_exemplo.json   exemplo de dados.json para testes
  historico.json       histórico de boletins, dia a dia (gerado/atualizado automaticamente)
docs/                  app (PWA), publicada como site estático (GitHub Pages)
  index.html            interface da app (lê docs/data/apostas.json)
  data/apostas.json     dados do dia + histórico + estatísticas, para a app
  banca.js              separador Banca (simulação e filtros), partilhado com a página
  manifest.webmanifest, sw.js, icons/   instalação e funcionamento offline
apostas-do-dia.html    cópia mais recente da página, atualizada a cada execução
```

## `gerar.py`

```
python3 gerar.py dados.json [pasta_de_saida]      # gera página e dados da app
python3 gerar.py --teste dados.json [pasta]       # como acima, mas sem tocar no histórico,
                                                   # em dados_atual.json nem na cópia
python3 gerar.py --pendentes                      # pernas cujo jogo já devia ter acabado
                                                   # e ainda sem resultado
python3 gerar.py --resultado JOGO MERCADO ok|no|adiado [placar]
                                                   # regista o resultado de uma perna
                                                   # (jogo e mercado por substring, sem maiúsculas)
python3 gerar.py --ontem [AAAA-MM-DD]             # JSON com "ontem" pronto a colar no
                                                   # próximo dados.json
```

Usa sempre `TZ=Europe/Lisbon` antes de `python3` — as horas dos jogos e a
janela de "já devia ter terminado" (`--pendentes`) são de Lisboa.

Uma execução normal (sem `--teste`):
1. lê `dados.json`, valida as regras dos boletins (avisos, nunca falhas);
2. junta os boletins de hoje ao histórico (`historico.json`) e aplica os
   resultados de "ontem" ao dia anterior, sem duplicar;
3. escreve `pagina.html` na pasta de saída;
4. guarda uma cópia de `dados.json` em `dados_atual.json`;
5. copia `pagina.html` para `apostas-do-dia.html`, na raiz do repositório;
6. exporta `docs/data/apostas.json`, lido pela app — nunca inclui emails.

### Formato de `dados.json`

Ver o cabeçalho de `apostas-template/gerar.py` (docstring) para o esquema
completo e comentado — data, título, boletins de hoje/próximos dias, o que
ficou de fora, a previsão de amanhã e o resumo de "ontem". `dados_exemplo.json`
é um exemplo completo e válido.

A múltipla arriscada (t3) e a dos próximos dias (t4) têm de ter pelo menos 25%
e 30% de probabilidade histórica de acertar (`PROB_MIN` em `gerar.py`, que
emite um AVISO quando falha). Como uma perna falhada perde o boletim todo,
variar o mercado em vez de encadear só "Resultado final": "Dupla hipótese: X ou
empate", "Mais de 1,5 golos", "Mais de 2,5 golos" ou "Ambas marcam".

## `epocas.py`: épocas passadas

```
python3 epocas.py "Casa - Fora" ["Casa - Fora" ...] [--comp "Competição"] [--neutro] [--json]
python3 epocas.py --boletim dados.json    # probabilidade de cada boletim acertar
python3 epocas.py --atualizar             # descarrega os resultados mais recentes
python3 epocas.py --avaliar               # mede o acerto do modelo contra as odds de fecho
python3 epocas.py --equipas TEXTO         # nomes das equipas tal como estão nos dados
```

Para cada jogo (equipa da casa primeiro, como na Betclic) mostra o registo em
casa e fora nas duas últimas épocas, a forma, o confronto direto e a
probabilidade estimada de cada mercado, com a odd justa correspondente. Os
dados vêm de football-data.co.uk (31 ligas de clubes, 4 épocas, com odds de
fecho) e de github.com/martj42/international_results (seleções, 12 anos).
Não cobre Colômbia, Uruguai, futebol feminino, Sub-21 nem competições europeias
de clubes: nesses casos responde "sem dados". Nomes em português que não
coincidam com os dos dados acrescentam-se em `epocas/alias.json`.

O que os números valem (`--avaliar`, 9 mil jogos dos últimos 12 meses): a
probabilidade do favorito está bem calibrada, mas as odds de fecho preveem
melhor do que o modelo, e apostar onde o modelo "vê valor" perde dinheiro. Por
isso o modelo serve para dar contexto e travar escolhas sem base, não para
contrariar a odd. Os mercados de golos e "ambas marcam" são os menos fiáveis.

`--boletim` usa outra medida, mais sólida: quantas vezes ganharam, em épocas
passadas, seleções com a mesma odd. Nos primeiros 20 dias de histórico essa
conta previu 13% para a arriscada (ganhou 12%) e 23% para a dos próximos dias
(ganhou 21%): os boletins rendem o que a odd total deles diz.

### Histórico (`historico.json`)

Uma lista de dias (`dia`, `rotulo`, `boletins`). Cada boletim guarda o texto,
as pernas (hora, jogo, mercado, odd, competição) e o estado (`pendente`, `ganho`,
`perdido`, `adiado`, `nao verificado`). Uma perna só fica registada quando o
jogo termina (`--resultado`); o boletim fecha-se sozinho: falha uma perna e
perde logo, todas certas e ganha. Nunca contém valores apostados.

### Banca

O separador Banca simula 1 € em cada boletim (`APOSTA` em `docs/banca.js`): um
boletim ganho devolve 1 € × a odd total publicada, um perdido perde 1 €. Mostra
o saldo acumulado a partir de 0 €, o retorno, a percentagem de acerto, a
evolução dia a dia e as contas por tipo de boletim, odd total, número de pernas,
competição, mercado e dia.

Tudo se recalcula no browser conforme os filtros: período (tudo, 7, 14 ou 30
dias a contar do último dia com boletins), tipo de boletim, faixa de odd total,
número de pernas, competição e mercado. Os filtros de competição e de mercado
apanham os boletins com pelo menos uma perna dessa competição ou mercado.

Só contam os boletins decididos: os adiados devolvem a aposta e os pendentes
ficam de fora. Cada boletim conta no dia em que foi publicado. É calculado a
partir do `historico.json`, que continua sem guardar valores. `docs/banca.js` é
o mesmo código na app e na página: a app carrega-o e o `gerar.py` embute-o.

## A página

`bilhetes.html` fornece o `<head>` e o CSS partilhados; `gerar.py` monta o
corpo (resumo do dia, boletins de hoje, próximos dias, o que ficou de fora) e
acrescenta os separadores de Histórico, Estatísticas e Banca. Usa fundo cor de
relva/verde, tipografia Fraunces (títulos) + Hanken Grotesk (texto) + IBM
Plex Mono (números e horas), tema claro/escuro automático
(`prefers-color-scheme`), separadores fixos (sticky) com ícones e cartões em
forma de bilhete com micro-interações ao passar o rato/tocar.

## Rotinas na nuvem

Duas rotinas do claude.ai (Rotinas) clonam este repositório, correm o `gerar.py`
e fazem commit e push para `main`; a app (GitHub Pages) lê o resultado:

- **Geração 00:00** (Lisboa): verifica o dia anterior, lê as odds da Betclic,
  gera os 4 boletins, a previsão de amanhã e o "Ficaram de fora".
- **Resultados** (às 00:54 e de 2 em 2 horas das 14:54 às 22:54, hora de
  Lisboa): regista os resultados dos jogos que já terminaram (`--pendentes` / `--resultado`) e regenera a página e a app.

Os horários das rotinas são em UTC e não acompanham a mudança de hora.

## A app (`docs/`)

Site estático (pensado para GitHub Pages) que lê `docs/data/apostas.json` e
funciona como PWA instalável: barra de navegação fixa em baixo com ícones
(Hoje/Histórico/Estatísticas/Banca), atualização manual, cache da casca da app via
`sw.js` (dados vão sempre à rede primeiro) e um estado de carregamento com
esqueleto (skeleton) em vez de texto simples. Usa o mesmo sistema visual da
página.

## Ficheiros gerados automaticamente

`dados_atual.json`, `historico.json`, `apostas-do-dia.html` e
`docs/data/apostas.json` são todos escritos por `gerar.py`, e
`epocas/clubes.csv` e `epocas/selecoes.csv` por `epocas.py --atualizar` — nunca
editar à mão. `.bak`, `.lock` e `.tmp` (ficheiros de escrita atómica e de segurança do
histórico) estão no `.gitignore`.
