#!/usr/bin/env python3
"""Gera a página (pagina.html) do "Apostas do dia" a partir de UM só ficheiro de dados.

Uso:  python3 gerar.py dados.json [pasta_de_saida]
- Lê bilhetes.html (na mesma pasta do script) só para aproveitar o <head> e o CSS da página.
- Calcula as odds totais (produto das pernas, 2 casas, vírgula), os resumos e os rodapés: nunca escrever totais à mão.
- Avisa (linhas "AVISO") se alguma regra dos boletins não se cumpre.
- A página tem 3 separadores (Hoje, Histórico, Estatísticas). O histórico vive em historico.json (atualizado a cada execução,
  sem duplicar); dados_atual.json guarda o dados.json do dia; cada execução copia a página para PASTA_COPIA.
Modos auxiliares:
  gerar.py --pendentes                      pernas cujo jogo já devia ter acabado e ainda sem resultado (ignora as com mais de 3 dias)
  gerar.py --resultado JOGO MERCADO ok|no|adiado [placar]   regista uma perna (substring, sem maiúsculas)
  gerar.py --ontem [AAAA-MM-DD]             JSON com o "ontem" pronto para o dados.json e as pernas ainda por verificar
  gerar.py --teste dados.json [pasta]       gera tudo SEM tocar no histórico, em dados_atual.json nem na pasta de cópia

dados.json:
{
 "data": "Sábado · 19 de setembro de 2026", "titulo": "Apostas de hoje", "link": "<url do artifact>",
 "pausa": "Depois de domingo, ... voltam entre 9 e 10 de outubro."   (opcional),
 "ontem": [{"t": "Aposta simples segura", "e": "ganho|perdido|adiado|nao verificado", "d": "Sporting 3-0 Arouca"}],  ([] se não houver)
 "hoje": [ {"c":"t1","t":"Aposta simples segura","risco":"baixo","legs":[{"h":"20:30","j":"Sporting vence o Arouca","m":"Resultado final","o":"1,18"}]},
           {"c":"t2",...}, {"c":"t3",...,"extra":"falhar uma perde tudo"} ],
 "proximos": [ {"c":"t4","t":"Múltipla dos próximos dias","risco":"médio","legs":[{"h":"11:15","d":"DOM","j":"...","m":"...","o":"1,23"}]} ],
 "amanha": [{"h":"14:00","d":"DOM","j":"Manchester City vence o Sunderland","m":"Resultado final","o":"1,26","n":"nota curta com dados desta execução"}],  (previsão do dia seguinte, provisória; [] se não houver)
 "fora": [["Jogo (odd)","motivo"]]
}
"""
import json, sys, re, os, shutil, fcntl, tempfile
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta
from functools import reduce, lru_cache

BASE = os.environ.get("APOSTAS_BASE", os.path.dirname(os.path.abspath(__file__)))  # APOSTAS_BASE e APOSTAS_COPIA só servem para testes
TPL = os.path.join(BASE, "bilhetes.html")
BETCLIC = "https://www.betclic.pt/futebol-s1"
NOTA = "Análise informativa, não é garantia de resultado. Aposta com responsabilidade."
DIAS = {"SEG": "segunda", "TER": "terça", "QUA": "quarta", "QUI": "quinta", "SEX": "sexta", "SÁB": "sábado", "SAB": "sábado", "DOM": "domingo"}
RISCO_PONTOS = {"baixo": 1, "médio": 2, "medio": 2, "alto": 3}
HIST = os.path.join(BASE, "historico.json")
PASTA_COPIA = os.environ.get("APOSTAS_COPIA", os.path.dirname(BASE))  # recebe uma cópia da página a cada geração
DADOS_ATUAL = os.path.join(BASE, "dados_atual.json")
DUR_MIN = 105  # minutos até um jogo se dar por terminado
DIA_IDX = {"SEG": 0, "TER": 1, "QUA": 2, "QUI": 3, "SEX": 4, "SÁB": 5, "SAB": 5, "DOM": 6}
MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
ESTADOS = {"pendente": ("n", "Pendente"), "ganho": ("g", "Ganho"), "perdido": ("p", "Perdido"), "adiado": ("n", "Adiado"), "nao verificado": ("n", "Não verificado"), "não verificado": ("n", "Não verificado")}
COMP_AUTORIZADAS = os.path.join(BASE, "competicoes_autorizadas.json")
ODD_REGEX = re.compile(r"\d+,\d{2}")

@lru_cache(maxsize=1)
def carregar_competicoes():
    """Carrega a lista de competições autorizadas (em cache)."""
    if not os.path.exists(COMP_AUTORIZADAS):
        return frozenset()
    try:
        with open(COMP_AUTORIZADAS, encoding="utf-8") as f:
            data = json.load(f)
        return frozenset(c.lower() for c in data.get("competicoes", []))
    except (json.JSONDecodeError, IOError):
        return frozenset()

def num(s): return float(s.replace(",", "."))
def fmt(x): return f"{x:.2f}".replace(".", ",")
def total(b):  # Decimal: sem erros de arredondamento de vírgula flutuante
    p = reduce(lambda a, l: a * Decimal(l["o"].replace(",", ".")), b["legs"], Decimal(1))
    return str(p.quantize(Decimal("0.01"), ROUND_HALF_UP)).replace(".", ",")
def rodape(b):
    n = len(b["legs"])
    base = "Uma seleção" if n == 1 else f"{n} seleções"

    # Extrair dias únicos mantendo ordem
    dias_unicos = []
    visto = set()
    for l in b["legs"]:
        d = l.get("d")
        if d and d not in visto:
            dias_unicos.append(d)
            visto.add(d)

    if dias_unicos:
        if len(dias_unicos) == 1:
            base += f" · todas no {DIAS.get(dias_unicos[0].upper(), dias_unicos[0].lower())}"
        else:
            nomes = [DIAS.get(d.upper(), d.lower()) for d in dias_unicos]
            base += " · " + ", ".join(nomes[:-1]) + " e " + nomes[-1]

    if b.get("extra"):
        base += " · " + b["extra"]

    return base
def resumo_label(c): return {"t1": "Simples", "t2": "Segura", "t3": "Arriscada", "t4": "Próximos dias"}.get(c, c)

def avisos(d):
    out = []
    comp_auth = carregar_competicoes()
    hoje = {b["c"]: b for b in d.get("hoje", [])}

    # Validações de estrutura dos boletins
    if "t1" in hoje and len(hoje["t1"]["legs"]) != 1: out.append("t1 deve ter 1 seleção")
    if "t2" in hoje:
        t2_legs = len(hoje["t2"]["legs"])
        if not 2 <= t2_legs <= 3: out.append("t2 deve ter 2 ou 3 seleções")
        if num(total(hoje["t2"])) > 2.5: out.append("t2 passa de 2,5 de odd total")
    if "t3" in hoje and len(hoje["t3"]["legs"]) < 3: out.append("t3 deve ter 3 ou mais seleções")

    # Validações de boletins obrigatórios
    if not d.get("sem_boletins_motivo"):
        for c, nome in (("t1", "Aposta simples segura"), ("t2", "Múltipla segura"), ("t3", "Múltipla arriscada")):
            if c not in hoje: out.append(f"falta o boletim '{nome}': faz sempre um de cada por dia (alarga a outras ligas e seleções); só se não houver mesmo jogos com odd disponível é que se preenche 'sem_boletins_motivo'")
        proximos = d.get("proximos", [])
        if not any(b["c"] == "t4" for b in proximos): out.append("falta a 'Múltipla dos próximos dias': faz sempre um de cada por dia (alarga a outras ligas e seleções)")

    # Validações de pernas
    for b in d.get("hoje", []) + d.get("proximos", []):
        jogos_set = set()
        for l in b["legs"]:
            # Extrair jogo para validação de duplicação
            jogo = l["j"].split(" vence ")[0].split("–")[0]
            if jogo in jogos_set:
                out.append(f"{b['c']}: jogos repetidos dentro do boletim")
                break
            jogos_set.add(jogo)

            # Validar odd
            if not ODD_REGEX.fullmatch(l["o"]):
                out.append(f"odd mal formatada: {l['o']}")

            # Validar competição autorizada
            if comp_auth and "comp" in l:
                comp_lower = l["comp"].lower()
                if comp_lower not in comp_auth:
                    out.append(f"{b['c']}: competição não autorizada '{l['comp']}' (jogo: {l['j']})")

    return out

# ---------------- histórico (separador da página) ----------------
def data_iso(d):
    m = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", d["data"])
    return f"{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
@contextmanager
def bloqueio():
    """Evita que duas execuções (rotina das 08:02 e verificação de resultados) escrevam o histórico ao mesmo tempo."""
    os.makedirs(BASE, exist_ok=True)
    with open(os.path.join(BASE, ".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(f, fcntl.LOCK_UN)
def gravar_hist(h):
    """Escrita atómica, com cópia de segurança da versão anterior (historico.json.bak)."""
    if os.path.exists(HIST): shutil.copy(HIST, HIST + ".bak")
    fd, tmp = tempfile.mkstemp(dir=BASE, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(h, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644); os.replace(tmp, HIST)
def carregar_hist():
    if not os.path.exists(HIST): return []
    return json.load(open(HIST, encoding="utf-8"))  # se estiver corrompido, falha alto em vez de apagar o histórico
def atualizar_hist(d):
    """Junta os boletins de hoje ao histórico e aplica os estados de 'ontem' ao dia anterior. Repetir a execução no mesmo dia não duplica nada."""
    h = carregar_hist(); hoje = data_iso(d)
    antigo = next((e for e in h if e["dia"] == hoje), None)
    h = [e for e in h if e["dia"] != hoje]
    ant = [e for e in h if e["dia"] < hoje]
    if ant and d.get("ontem"):
        e = max(ant, key=lambda x: x["dia"])
        for r in d["ontem"]:
            for b in e["boletins"]:
                if b["t"] == r["t"]: b["e"], b["d"] = r["e"], r["d"]
    todos = d.get("hoje", []) + d.get("proximos", [])
    if todos:
        h.append({"dia": hoje, "rotulo": d["data"], "boletins": [
            {"t": b["t"], "c": b["c"], "total": total(b), "e": "pendente", "d": "",
             "legs": [{k: l[k] for k in ("h", "d", "j", "m", "o") if k in l} for l in b["legs"]]} for b in todos]})
        if antigo:
            for b in h[-1]["boletins"]:
                ob = next((x for x in antigo["boletins"] if x["t"] == b["t"]), None)
                if not ob: continue
                b["e"], b["d"] = ob["e"], ob.get("d", "")
                for l in b["legs"]:
                    ol = next((x for x in ob["legs"] if x["j"] == l["j"] and x["m"] == l["m"]), None)
                    if ol:
                        for k in ("r", "x"):
                            if k in ol: l[k] = ol[k]
    h.sort(key=lambda x: x["dia"], reverse=True)
    resolver(h)
    return h
def resolver(h):
    """Fecha o estado de um boletim assim que as pernas o permitem: uma perna falhada perde já, todas certas ganha."""
    for e in h:
        for b in e["boletins"]:
            auto = b["e"] == "perdido" and b.get("d", "").startswith("Falhou: ")  # perdido pelo resolver: a frase acompanha as pernas que vão fechando
            if b["e"] not in ("pendente", "nao verificado", "adiado") and not auto: continue
            legs = b["legs"]; rs = [l.get("r") for l in legs]
            if not any(rs): continue
            ok = rs.count("ok")
            falhou = [f'{l["j"]}{" (" + l["x"] + ")" if l.get("x") else ""}' for l in legs if l.get("r") == "no"]
            if falhou: b["e"] = "perdido"; b["d"] = "Falhou: " + "; ".join(falhou) + f" · {ok} {'certa' if ok == 1 else 'certas'}" + (f", {rs.count(None)} por jogar" if rs.count(None) else "")
            elif all(r == "ok" for r in rs): b["e"] = "ganho"; b["d"] = "Todas as pernas certas: " + "; ".join(f'{l["j"]}{" (" + l["x"] + ")" if l.get("x") else ""}' for l in legs)
            elif "adiado" in rs: b["e"] = "adiado"; b["d"] = "Há um jogo adiado; boletim por decidir"
            else: b["d"] = f"{ok} de {len(legs)} pernas certas até agora"
def inicio_perna(e, l):
    dia = datetime.strptime(e["dia"], "%Y-%m-%d").date()
    if l.get("d"):
        alvo = DIA_IDX.get(l["d"].upper())
        if alvo is not None: dia += timedelta(days=(alvo - dia.weekday()) % 7)
    hh, mm = map(int, l["h"].split(":"))
    return datetime(dia.year, dia.month, dia.day, hh, mm)
def pendentes():
    """Pernas por resolver cujo jogo já devia ter terminado."""
    agora = datetime.now(); out = []
    for e in carregar_hist():
        for b in e["boletins"]:
            for l in b["legs"]:
                if l.get("r") or not l.get("h"): continue
                ini = inicio_perna(e, l)
                if ini + timedelta(minutes=DUR_MIN) <= agora <= ini + timedelta(days=3):
                    out.append((e["dia"], l["h"], l["j"], l["m"], b["t"]))
    return out
def ontem_json(dia=None):
    h = carregar_hist(); hoje = date.today().isoformat()
    ant = [e for e in h if e["dia"] < (dia or hoje) or e["dia"] == dia]
    if not ant: return {"dia": None, "ontem": [], "por_verificar": []}
    e = next((x for x in h if x["dia"] == dia), None) if dia else max(ant, key=lambda x: x["dia"])
    if not e: return {"dia": dia, "ontem": [], "por_verificar": []}
    ontem = [{"t": b["t"], "e": "nao verificado" if b["e"] == "pendente" else b["e"], "d": b.get("d") or "Ainda sem resultados dos jogos"} for b in e["boletins"]]
    falta = [{"j": l["j"], "m": l["m"], "h": l.get("h", ""), "d": l.get("d", ""), "boletim": b["t"]} for b in e["boletins"] for l in b["legs"] if not l.get("r")]
    return {"dia": e["dia"], "ontem": ontem, "por_verificar": falta}
def registar(jogo, mercado, r, x=""):
    """Marca a perna (jogo e mercado por substring, sem maiúsculas) como ok|no|adiado e guarda o resultado."""
    n = 0
    with bloqueio():
        h = carregar_hist()
        for e in h:
            for b in e["boletins"]:
                for l in b["legs"]:
                    if not l.get("r") and jogo.lower() in l["j"].lower() and mercado.lower() in l["m"].lower():
                        l["r"] = r; n += 1
                        if x: l["x"] = x
        resolver(h); gravar_hist(h)
    return n
def pag_hist(h):
    if not h: return '<p class="calm">Ainda não há apostas no histórico.</p>'
    bs = [b for e in h for b in e["boletins"]]
    ng = sum(b["e"] == "ganho" for b in bs); npd = sum(b["e"] == "perdido" for b in bs); nv = len(bs) - ng - npd
    out = (f'<div class="sum hs"><div><small>Boletins</small><b>{len(bs)}</b></div><div><small>Ganhos</small><b>{ng}</b></div>'
           f'<div class="p"><small>Perdidos</small><b>{npd}</b></div><div class="n"><small>Por verificar</small><b>{nv}</b></div></div>')
    for e in h:
        rows = ""
        for b in e["boletins"]:
            k, lb = ESTADOS[b["e"]]
            legs = "".join(f'<li class="{l.get("r", "")}">{(l["d"].capitalize() + " ") if l.get("d") else ""}{l["h"] + " · " if l.get("h") else ""}{l["j"]} · {l["m"]} · {l["o"]}' + (f' <em>{l["x"]}</em>' if l.get("x") else "") + "</li>" for l in b["legs"])
            det = f'<small>{b["d"]}</small>' if b.get("d") and not any(l.get("r") for l in b["legs"]) else ""
            rows += (f'<li class="hr"><div class="hh"><b>{b["t"]}</b><span class="od">{b["total"]}</span><span class="st {k}">{lb}</span></div>{det}<ul class="hl">{legs}</ul></li>')
        out += f'<section class="hday"><div class="head"><h2>{e["rotulo"].replace(" · ", ", ", 1)}</h2></div><article class="tk"><ul class="hlist">{rows}</ul></article></section>'
    return out + '<p class="note">Só ganho ou perdido, sem valores. Cada dia é acrescentado automaticamente pela rotina.</p>'
HIST_CSS = """
<style>
.tabs{position:sticky;top:0;z-index:5;border-bottom:1px solid var(--hair);background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
.tabs .in{padding-top:14px;padding-bottom:0;display:flex;gap:6px}
.tab{appearance:none;background:none;border:0;border-bottom:3px solid transparent;font:inherit;font-weight:600;font-size:15px;color:var(--soft);padding:10px 16px 11px;cursor:pointer;border-radius:10px 10px 0 0;display:inline-flex;align-items:center;gap:7px;transition:color .12s ease}
.tab:before{content:"";width:16px;height:16px;flex:0 0 auto;background:currentColor;-webkit-mask:var(--ico) center/contain no-repeat;mask:var(--ico) center/contain no-repeat;opacity:.85}
.tab[data-p="hoje"]{--ico:url('data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"%3E%3Crect x="3" y="4" width="18" height="17" rx="3"/%3E%3Cpath d="M3 9h18M8 2v4M16 2v4"/%3E%3C/svg%3E')}
.tab[data-p="hist"]{--ico:url('data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"%3E%3Ccircle cx="12" cy="12" r="9"/%3E%3Cpath d="M12 7v5l3.5 2"/%3E%3C/svg%3E')}
.tab[data-p="est"]{--ico:url('data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"%3E%3Cpath d="M4 20V10M12 20V4M20 20v-7"/%3E%3C/svg%3E')}
.tab[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--pitch)}
.tab:focus-visible{outline:2px solid var(--pitch);outline-offset:-2px}
.hs{max-width:640px;margin:0 0 32px}
.hday{margin:0 0 32px}
.hlist{list-style:none;margin:0;padding:0}
.tk li.hr{display:block;padding:16px 20px;border-top:1px dashed var(--hair)}
.tk li.hr:first-child{border-top:0}
.tk .hl li{display:block;padding:0;border:0}
.hh{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.hh b{font-weight:600;margin-right:auto}
.hr>small{display:block;color:var(--soft);font-size:12.5px;margin-top:4px}
.hl{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-direction:column;gap:2px;font-size:13px;color:var(--soft)}
.hl li:before{content:"\\00b7\\00a0\\00a0"}
.hl li.ok{color:var(--pitch)}.hl li.no{color:var(--warn)}
.hl em{font-style:normal;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
.hr .od{padding:4px 12px;font-size:15px}
.hs div.n b{color:var(--soft)}
.hs div.p b{color:var(--warn)}
.tk ul.hlist,.tk ul.hl{padding:0}
@media(max-width:640px){.sum.c3{grid-template-columns:repeat(3,1fr);gap:8px}.sum.c3 a{padding:10px 12px}.sum.c3 b{font-size:19px}.tabs .in{padding-top:10px}.tk li.hr{padding:14px 16px}.tab{padding:9px 12px 10px}}
</style>
"""
TAB_JS = """<script>
(function(){var t=document.querySelectorAll('.tab'),K=['hoje','hist','est'],H={'#historico':'hist','#estatisticas':'est'},U={hist:'#historico',est:'#estatisticas'};
function show(k){for(var i=0;i<t.length;i++){t[i].setAttribute('aria-selected',t[i].dataset.p===k?'true':'false')}for(var j=0;j<K.length;j++){var e=document.getElementById('p-'+K[j]);if(e)e.hidden=K[j]!==k;}}
function fromHash(){var h=location.hash;if(H[h]){show(H[h]);return}if(h.length>1){var el=document.getElementById(h.slice(1));if(el&&document.getElementById('p-hoje').contains(el)){show('hoje');el.scrollIntoView()}}}
for(var i=0;i<t.length;i++)t[i].addEventListener('click',function(){var k=this.dataset.p;show(k);try{history.replaceState(null,'',U[k]||location.pathname+location.search)}catch(e){}});
var L=document.querySelectorAll('.sum a[href^="#"]');for(var k=0;k<L.length;k++)L[k].addEventListener('click',function(ev){var el=document.getElementById(this.getAttribute('href').slice(1));if(!el)return;ev.preventDefault();show('hoje');el.scrollIntoView({behavior:'smooth',block:'start'})});
window.addEventListener('hashchange',fromHash);fromHash();
})();
</script>"""

# ---------------- estatísticas (separador da página) ----------------
def _pct(a, b): return f"{round(100 * a / b)}%" if b else "–"
def _linha(rotulo, ok, dec, extra="", perna=False):
    larg = round(100 * ok / dec) if dec else 0
    base = f"{ok} certas em {dec}" if perna else f"{ok} {'ganho' if ok == 1 else 'ganhos'} em {dec} decididos"
    sub = base + (f" · {extra}" if extra else "") if dec else (extra or "sem dados ainda")
    cor = " lo" if dec and larg < 50 else ""
    return f'<div class="sr"><div class="sl"><b>{rotulo}</b><small>{sub}</small></div><div class="sb" aria-hidden="true"><i class="{cor.strip()}" style="width:{larg}%"></i></div><span class="sp{cor}">{_pct(ok, dec)}</span></div>'
def _bloco(titulo, linhas, nota=""):
    n = f'<p class="pn">{nota}</p>' if nota else ""
    return f'<section class="hday"><div class="head"><h2>{titulo}</h2></div><article class="tk">{"".join(linhas)}{n}</article></section>'
def pag_est(h):
    if not h: return '<p class="calm">Ainda não há apostas para estatísticas.</p>'
    bs = [(e, b) for e in h for b in e["boletins"]]
    dec = [b for _, b in bs if b["e"] in ("ganho", "perdido")]; gan = sum(b["e"] == "ganho" for b in dec)
    # pernas únicas (jogo + mercado), só as já decididas
    vistas = {}
    for e, b in bs:
        for l in b["legs"]:
            if l.get("r") in ("ok", "no"): vistas[(l["j"], l["m"])] = l
    pernas = list(vistas.values()); pok = sum(l["r"] == "ok" for l in pernas)
    odds = [num(l["o"]) for l in pernas]
    chips = (f'<div class="sum hs"><div><small>Boletins decididos</small><b>{len(dec)}</b></div><div><small>Boletins ganhos</small><b>{_pct(gan, len(dec))}</b></div>'
             f'<div><small>Pernas certas</small><b>{_pct(pok, len(pernas))}</b></div><div class="n"><small>Dias</small><b>{len(h)}</b></div></div>')
    tipos = []
    for c, nome in (("t1", "Aposta simples segura"), ("t2", "Múltipla segura"), ("t3", "Múltipla arriscada"), ("t4", "Múltipla dos próximos dias")):
        grupo = [b for _, b in bs if b["c"] == c]
        if not grupo: continue
        d_ = [b for b in grupo if b["e"] in ("ganho", "perdido")]; pend = len(grupo) - len(d_)
        tipos.append(_linha(nome, sum(b["e"] == "ganho" for b in d_), len(d_), f"{pend} por decidir" if pend else ""))
    merc = {}
    for l in pernas: merc.setdefault(l["m"], []).append(l)
    mercs = [_linha(m, sum(x["r"] == "ok" for x in ls), len(ls), perna=True) for m, ls in sorted(merc.items(), key=lambda kv: -len(kv[1]))]
    faixas = [("Odd até 1,25", lambda o: o <= 1.25), ("Odd de 1,26 a 1,45", lambda o: 1.25 < o <= 1.45), ("Odd acima de 1,45", lambda o: o > 1.45)]
    fx = []
    for nome, f in faixas:
        ls = [l for l in pernas if f(num(l["o"]))]
        fx.append(_linha(nome, sum(l["r"] == "ok" for l in ls), len(ls), perna=True))
    dias = []
    for e in h:
        d_ = [b for b in e["boletins"] if b["e"] in ("ganho", "perdido")]; pend = len(e["boletins"]) - len(d_)
        dias.append(_linha(e["rotulo"].split(" de 20")[0].replace(" · ", ", ", 1), sum(b["e"] == "ganho" for b in d_), len(d_), f"{pend} por decidir" if pend else ""))
    media = f"odd média das pernas {fmt(sum(odds) / len(odds))}" if odds else ""
    amostra = (f"Amostra pequena: {len(pernas)} pernas decididas em {len(h)} dias{(' (' + media + ')') if media else ''}. "
               "As percentagens só descrevem o que já aconteceu e não garantem nada sobre os próximos jogos. Sem valores nem contas de dinheiro.")
    return (chips + _bloco("Por tipo de boletim", tipos, "Um boletim só conta como decidido quando ganha ou perde; os pendentes ficam de fora.")
            + _bloco("Por mercado", mercs, "Conta cada jogo e mercado uma só vez, mesmo que apareça em vários boletins.")
            + _bloco("Por faixa de odd", fx) + _bloco("Por dia", dias) + f'<p class="note">{amostra}</p>')
EST_CSS = """
<style>
.sr{display:grid;grid-template-columns:minmax(0,1fr) 140px 48px;gap:6px 16px;align-items:center;padding:14px 20px;border-top:1px dashed var(--hair)}
.sr:first-child{border-top:0}
.sl b{display:block;font-weight:600}
.sl small{display:block;color:var(--soft);font-size:12.5px}
.sb{height:8px;border-radius:999px;background:var(--wash);border:1px solid var(--hair);overflow:hidden}
.sb i{display:block;height:100%;background:var(--pitch);border-radius:999px;transition:width .3s ease}
.sb i.lo{background:var(--warn)}
.sp{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:16px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums;color:var(--pitch)}
.sp.lo{color:var(--warn)}
@media(max-width:640px){.sr{grid-template-columns:minmax(0,1fr) 48px;padding:12px 16px}.sb{grid-column:1 / -1;grid-row:2}.sp{grid-row:1;grid-column:2}}
</style>
"""

# ---------------- página ----------------
def pag_leg(l):
    dia = f'<u>{l["d"].capitalize()}</u>' if l.get("d") else ""
    return f'<li><span class="tm">{dia}{l["h"]}</span><span class="lg"><b>{l["j"]}</b><small>{l["m"]}</small></span><span class="od">{l["o"]}</span></li>'
def pag_card(b):
    p = RISCO_PONTOS[b["risco"]]
    dots = "".join('<i class="on"></i>' if i < p else "<i></i>" for i in range(3))
    return (f'<article class="tk {b["c"]}" id="{b["c"]}"><header><h3>{b["t"]}</h3><span class="risk" aria-label="Risco {b["risco"]}">{dots}<em>{b["risco"]}</em></span></header>'
            f'<ul>{"".join(pag_leg(l) for l in b["legs"])}</ul><div class="perf"></div>'
            f'<div class="foot"><span>{rodape(b)}</span><div class="tt"><small>Odd total</small><b>{total(b)}</b></div></div></article>')
def pag_ontem(d):
    if d.get("ontem"):
        n = sum(1 for r in d["ontem"] if r["e"] == "ganho")
        rows = ""
        for r in d["ontem"]:
            k, lb = ESTADOS[r["e"]]
            rows += f'<li class="r"><span class="lg"><b>{r["t"]}</b><small>{r["d"]}</small></span><span class="st {k}">{lb}</span></li>'
        cnt = f'<span class="cnt">{n} de {len(d["ontem"])} ganhos</span>'
    else:
        rows = '<li class="r"><span class="lg"><b>Sem apostas de ontem para verificar</b></span></li>'; cnt = ""
    return f'<div class="wide"><article class="tk"><header><h3>Como correram as apostas de ontem</h3>{cnt}</header><ul>{rows}</ul></article></div>'
def pag_amanha(d):
    if not d.get("amanha"): return ""
    rows = "".join(f'<li><span class="tm"><u>{l["d"].capitalize()}</u>{l["h"]}</span><span class="lg"><b>{l["j"]}</b><small>{l["m"]} · {l["n"]}</small></span><span class="od">{l["o"]}</span></li>' for l in d["amanha"])
    return f'<article class="tk prev" id="amanha"><header><h3>Previsão para amanhã</h3><span class="st n">Provisório</span></header><ul>{rows}</ul><p class="pn">Odds, lesões e equipas podem mudar. A rotina de amanhã confirma tudo.</p></article>'
def pag_fora(d):
    if not d.get("fora"): return ""
    lis = "".join(f'<li class="r"><span class="lg"><b>{a}</b><small>{b}</small></span></li>' for a, b in d["fora"])
    return f'<div class="wide next fora"><article class="tk"><header><h3>Ficaram de fora</h3></header><ul>{lis}</ul></article></div>'
def pagina(d, hist=None):
    src = open(TPL, encoding="utf-8").read()
    head = src[: src.index("</style>") + len("</style>")]
    head = re.sub(r"<title>.*?</title>", "<title>Apostas do dia</title>", head, count=1) + HIST_CSS + EST_CSS
    todos = d.get("hoje", []) + d.get("proximos", [])
    chips = "".join(f'<a href="#{b["c"]}"><small>{resumo_label(b["c"])}</small><b>{total(b)}</b></a>' if b["c"] != "t3" else f'<a class="w" href="#{b["c"]}"><small>{resumo_label(b["c"])}</small><b>{total(b)}</b></a>' for b in todos)
    body = f'\n<div class="top"><div class="in"><p class="date">{d["data"]}</p><h1>{d["titulo"]}</h1>' + (f'<div class="sum c{len(todos)}">{chips}</div>' if chips else "") + "</div></div>\n<div class=\"in\">\n"
    body = body[: body.rindex('<div class="in">')] + '<div class="tabs"><div class="in" role="tablist" aria-label="Secções"><button class="tab" role="tab" id="tab-hoje" data-p="hoje" aria-selected="true">Hoje</button><button class="tab" role="tab" id="tab-hist" data-p="hist" aria-selected="false">Histórico</button><button class="tab" role="tab" id="tab-est" data-p="est" aria-selected="false">Estatísticas</button></div></div>\n<div class="in" id="p-hoje" role="tabpanel" aria-labelledby="tab-hoje">\n'
    body += pag_ontem(d) + "\n"
    body += f'<div class="head"><h2>Apostas de hoje</h2><span class="src">Odds da <a href="{BETCLIC}">Betclic</a>, a confirmar</span></div>\n'
    if d.get("hoje"):
        by = {b["c"]: b for b in d["hoje"]}
        if "t1" in by and "t2" in by:
            cards = f'<div class="stack">{pag_card(by["t1"])}{pag_card(by["t2"])}</div>' + "".join(pag_card(b) for b in d["hoje"] if b["c"] not in ("t1", "t2"))
        else: cards = "".join(pag_card(b) for b in d["hoje"])
        body += f'<div class="grid hoje">{cards}</div>\n'
    else: body += '<p class="calm">Hoje não há jogos com dados suficientes.</p>\n'
    if d.get("proximos") or d.get("amanha") or d.get("pausa"):
        body += f'<div class="head next"><h2>Próximos dias</h2><span class="src">{d.get("pausa", "")}</span></div>\n<div class="grid one">{"".join(pag_card(b) for b in d.get("proximos", []))}{pag_amanha(d)}</div>\n'
    body += pag_fora(d) + f'\n<p class="note">{NOTA}</p>\n</div>\n'
    body += f'<div class="in" id="p-hist" role="tabpanel" aria-labelledby="tab-hist" hidden>\n{pag_hist(hist if hist is not None else [])}\n</div>\n<div class="in" id="p-est" role="tabpanel" aria-labelledby="tab-est" hidden>\n{pag_est(hist if hist is not None else [])}\n</div>\n' + TAB_JS + "\n"
    return head + body

# ---------------- app (PWA): dados em JSON ----------------
APP_DATA = os.environ.get("APOSTAS_APP_DATA", os.path.join(os.path.dirname(BASE), "docs", "data", "apostas.json"))
def _grp(ok, dec, **extra): return {"ok": ok, "dec": dec, "pct": round(100 * ok / dec) if dec else None, **extra}
def estatisticas(h):
    """Mesmos números do separador Estatísticas da página, em estrutura para a app."""
    if not h: return None
    bs = [(e, b) for e in h for b in e["boletins"]]
    dec = [b for _, b in bs if b["e"] in ("ganho", "perdido")]
    vistas = {}
    for e, b in bs:
        for l in b["legs"]:
            if l.get("r") in ("ok", "no"): vistas[(l["j"], l["m"])] = l
    pernas = list(vistas.values()); pok = sum(l["r"] == "ok" for l in pernas)
    nomes = (("t1", "Aposta simples segura"), ("t2", "Múltipla segura"), ("t3", "Múltipla arriscada"), ("t4", "Múltipla dos próximos dias"))
    tipos = []
    for c, nome in nomes:
        g = [b for _, b in bs if b["c"] == c]
        if not g: continue
        d_ = [b for b in g if b["e"] in ("ganho", "perdido")]
        tipos.append(_grp(sum(b["e"] == "ganho" for b in d_), len(d_), nome=nome, pend=len(g) - len(d_)))
    merc = {}
    for l in pernas: merc.setdefault(l["m"], []).append(l)
    mercados = [_grp(sum(x["r"] == "ok" for x in ls), len(ls), nome=m) for m, ls in sorted(merc.items(), key=lambda kv: -len(kv[1]))]
    faixas = []
    for nome, f in (("Odd até 1,25", lambda o: o <= 1.25), ("Odd de 1,26 a 1,45", lambda o: 1.25 < o <= 1.45), ("Odd acima de 1,45", lambda o: o > 1.45)):
        ls = [l for l in pernas if f(num(l["o"]))]
        faixas.append(_grp(sum(l["r"] == "ok" for l in ls), len(ls), nome=nome))
    dias = []
    for e in h:
        d_ = [b for b in e["boletins"] if b["e"] in ("ganho", "perdido")]
        dias.append(_grp(sum(b["e"] == "ganho" for b in d_), len(d_), nome=e["rotulo"].split(" de 20")[0].replace(" · ", ", ", 1), pend=len(e["boletins"]) - len(d_)))
    odds = [num(l["o"]) for l in pernas]
    return {"decididos": len(dec), "ganhos": sum(b["e"] == "ganho" for b in dec), "pernas": len(pernas), "pernas_ok": pok, "dias": len(h),
            "odd_media": fmt(sum(odds) / len(odds)) if odds else None, "tipos": tipos, "mercados": mercados, "faixas": faixas, "por_dia": dias}
def boletim_app(b):
    return {"c": b["c"], "t": b["t"], "risco": b.get("risco", ""), "legs": b["legs"], "total": total(b), "rodape": rodape(b)}
def exportar_app(d, hist):
    """Escreve docs/data/apostas.json (lido pela app). Só as apostas; nunca emails nem endereços."""
    dados = {"atualizado": datetime.now().astimezone().isoformat(timespec="seconds"), "dia": data_iso(d), "rotulo": d["data"], "titulo": d.get("titulo", "Apostas de hoje"),
             "provisorio": bool(d.get("provisorio")), "aviso": d.get("aviso", ""), "pausa": d.get("pausa", ""),
             "ontem": d.get("ontem", []), "hoje": [boletim_app(b) for b in d.get("hoje", [])], "proximos": [boletim_app(b) for b in d.get("proximos", [])],
             "amanha": d.get("amanha", []), "fora": d.get("fora", []), "historico": hist, "estatisticas": estatisticas(hist)}
    os.makedirs(os.path.dirname(APP_DATA), exist_ok=True)
    tmp = APP_DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, APP_DATA)
    return APP_DATA

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--pendentes":
    ps = pendentes()
    print(f"{len(ps)} pernas por verificar")
    for p in ps: print(" | ".join(p))
elif __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--ontem":
    print(json.dumps(ontem_json(sys.argv[2] if len(sys.argv) > 2 else None), ensure_ascii=False, indent=1))
elif __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--resultado":
    # --resultado "<jogo>" "<mercado>" ok|no|adiado ["placar"]
    print(registar(*sys.argv[2:6]), "pernas atualizadas")
elif __name__ == "__main__":
    TESTE = sys.argv[1] == "--teste"
    if TESTE: sys.argv.pop(1)
    d = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(out, exist_ok=True)
    for a in avisos(d): print("AVISO:", a)
    if not TESTE and os.path.abspath(sys.argv[1]) != DADOS_ATUAL:
        try: shutil.copy(sys.argv[1], DADOS_ATUAL)
        except Exception as ex: print("AVISO: não consegui guardar dados_atual.json:", ex)
    if TESTE:
        hist = atualizar_hist(d); print("modo teste: histórico, dados_atual.json e pasta de cópia ficam intocados")
    else:
        with bloqueio():
            hist = atualizar_hist(d); gravar_hist(hist)
    c = pagina(d, hist)
    open(os.path.join(out, "pagina.html"), "w", encoding="utf-8").write(c); print("pagina.html", len(c), "bytes")
    if not TESTE and os.path.isdir(PASTA_COPIA):
        try:
            shutil.copy(os.path.join(out, "pagina.html"), os.path.join(PASTA_COPIA, ".apostas-do-dia.tmp")); os.replace(os.path.join(PASTA_COPIA, ".apostas-do-dia.tmp"), os.path.join(PASTA_COPIA, "apostas-do-dia.html")); print("cópia atualizada em", PASTA_COPIA)
        except Exception as ex: print("AVISO: não consegui copiar a página para", PASTA_COPIA, ex)
    if not TESTE:
        try: print("app:", exportar_app(d, hist))
        except Exception as ex: print("AVISO: não consegui exportar os dados da app:", ex)
    print("totais:", {b["c"]: total(b) for b in d.get("hoje", []) + d.get("proximos", [])})
