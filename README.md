# Apostas do dia

Gerador de uma página diária de apostas ("Apostas do dia"), com histórico e
estatísticas, publicada como Artifact e disponível também como app instalável
(PWA). Tudo — página, email e dados da app — sai de **um único** ficheiro de
dados do dia (`dados.json`) e de **um único** script (`gerar.py`); nada é
escrito à mão.

## Estrutura do repositório

```
apostas-template/
  gerar.py            script gerador: página, email e dados da app
  bilhetes.html        <head>/CSS de referência da página + um exemplo estático
  dados_atual.json     cópia do último dados.json usado (gerada automaticamente)
  dados_exemplo.json   exemplo de dados.json para testes
  historico.json       histórico de boletins, dia a dia (gerado/atualizado automaticamente)
docs/                  app (PWA), publicada como site estático (GitHub Pages)
  index.html            interface da app (lê docs/data/apostas.json)
  data/apostas.json     dados do dia + histórico + estatísticas, para a app
  manifest.webmanifest, sw.js, icons/   instalação e funcionamento offline
apostas-do-dia.html    cópia mais recente da página, atualizada a cada execução
```

## `gerar.py`

```
python3 gerar.py dados.json [pasta_de_saida]      # gera página, email e dados da app
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
3. escreve `pagina.html`, `email.html` e `email.txt` na pasta de saída;
4. guarda uma cópia de `dados.json` em `dados_atual.json`;
5. copia `pagina.html` para `apostas-do-dia.html`, na raiz do repositório;
6. exporta `docs/data/apostas.json`, lido pela app — nunca inclui emails.

### Formato de `dados.json`

Ver o cabeçalho de `apostas-template/gerar.py` (docstring) para o esquema
completo e comentado — data, título, boletins de hoje/próximos dias, o que
ficou de fora, a previsão de amanhã e o resumo de "ontem". `dados_exemplo.json`
é um exemplo completo e válido.

### Histórico (`historico.json`)

Uma lista de dias (`dia`, `rotulo`, `boletins`). Cada boletim guarda o texto,
as pernas (hora, jogo, mercado, odd) e o estado (`pendente`, `ganho`,
`perdido`, `adiado`, `nao verificado`). Uma perna só fica registada quando o
jogo termina (`--resultado`); o boletim fecha-se sozinho: falha uma perna e
perde logo, todas certas e ganha. Nunca contém valores apostados.

## A página (Artifact)

`bilhetes.html` fornece o `<head>` e o CSS partilhados; `gerar.py` monta o
corpo (resumo do dia, boletins de hoje, próximos dias, o que ficou de fora) e
acrescenta os separadores de Histórico e Estatísticas. Usa fundo cor de
relva/verde, tipografia Fraunces (títulos) + Hanken Grotesk (texto) + IBM
Plex Mono (números e horas), tema claro/escuro automático
(`prefers-color-scheme`), separadores fixos (sticky) com ícones e cartões em
forma de bilhete com micro-interações ao passar o rato/tocar.

A rotina diária publica `pagina.html` no mesmo Artifact (nunca cria um novo).

## A app (`docs/`)

Site estático (pensado para GitHub Pages) que lê `docs/data/apostas.json` e
funciona como PWA instalável: barra de navegação fixa em baixo com ícones
(Hoje/Histórico/Estatísticas), atualização manual, cache da casca da app via
`sw.js` (dados vão sempre à rede primeiro) e um estado de carregamento com
esqueleto (skeleton) em vez de texto simples. Usa o mesmo sistema visual da
página.

## Ficheiros gerados automaticamente

`dados_atual.json`, `historico.json`, `apostas-do-dia.html` e
`docs/data/apostas.json` são todos escritos por `gerar.py` — nunca editar à
mão. `.bak`, `.lock` e `.tmp` (ficheiros de escrita atómica e de segurança do
histórico) estão no `.gitignore`.
