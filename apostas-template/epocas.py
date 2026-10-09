#!/usr/bin/env python3
"""Resultados de épocas passadas ao serviço dos boletins: ver USO."""
import csv, difflib, io, json, math, os, re, sys, tempfile, unicodedata, urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

USO = """Uso:
  epocas.py "Casa - Fora" ["Casa - Fora" ...] [--comp "Competição"] [--neutro] [--json]
      estatísticas de épocas passadas e probabilidades estimadas para cada jogo
  epocas.py --boletim dados.json
      probabilidade de cada boletim acertar, pelo que odds iguais renderam em épocas passadas
  epocas.py --atualizar     descarrega os resultados mais recentes para epocas/
  epocas.py --avaliar       mede o acerto do modelo nos últimos 12 meses, contra as odds de fecho
  epocas.py --equipas TEXTO lista os nomes das equipas e seleções que contêm TEXTO"""

BASE = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(BASE, "epocas")
CLUBES = os.path.join(PASTA, "clubes.csv")
SELECOES = os.path.join(PASTA, "selecoes.csv")
ALIAS = os.path.join(PASTA, "alias.json")
FD = "https://www.football-data.co.uk"
SEL_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
LIGAS_EPOCA = {"E0": "Premier League", "E1": "Championship", "SC0": "Escócia", "D1": "Bundesliga", "D2": "2. Bundesliga",
               "I1": "Serie A", "I2": "Serie B", "SP1": "La Liga", "SP2": "La Liga 2", "F1": "Ligue 1", "F2": "Ligue 2",
               "N1": "Eredivisie", "B1": "Bélgica", "P1": "Liga Portugal", "T1": "Turquia", "G1": "Grécia"}
LIGAS_UNICAS = {"ARG": ("Argentina", "Argentina"), "AUT": ("Austria", "Áustria"), "BRA": ("Brazil", "Brasil Série A"),
                "CHN": ("China", "China"), "DNK": ("Denmark", "Dinamarca"), "FIN": ("Finland", "Finlândia"),
                "IRL": ("Ireland", "Irlanda"), "JPN": ("Japan", "Japão"), "MEX": ("Mexico", "Liga MX"),
                "NOR": ("Norway", "Noruega"), "POL": ("Poland", "Polónia"), "ROU": ("Romania", "Roménia"),
                "RUS": ("Russia", "Rússia"), "SWE": ("Sweden", "Suécia"), "USA": ("USA", "MLS")}
NOME_LIGA = {**LIGAS_EPOCA, **{k: v[1] for k, v in LIGAS_UNICAS.items()}}
COMP_LIGA = [("premier league", "E0"), ("championship", "E1"), ("2. bundesliga", "D2"), ("bundesliga", "D1"), ("la liga 2", "SP2"),
             ("laliga 2", "SP2"), ("la liga", "SP1"), ("laliga", "SP1"), ("ligue 2", "F2"), ("ligue 1", "F1"), ("eredivisie", "N1"),
             ("liga portugal", "P1"), ("serie a (it", "I1"), ("italia", "I1"), ("brasil", "BRA"), ("argentina", "ARG"),
             ("mls", "USA"), ("liga mx", "MEX"), ("mexico", "MEX"), ("escocia", "SC0"), ("turquia", "T1"), ("grecia", "G1")]
COMP_SELECOES = ("selecoes", "nacoes", "campeonato do mundo", "campeonato europeu", "eliminatorias", "copa america", "can")
SEM_DADOS = re.compile(r"women|femin|\bsub \d\d\b|\bu ?\d\d\b|\bf \|")
ANOS_CLUBES, ANOS_SELECOES = 4.3, 12
ENCHIMENTO = {"fc", "cf", "ca", "ac", "sc", "cd", "afc", "club", "de", "sad", "cp", "as", "ss", "fk", "sk"}


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))).strip()

def sem_enchimento(n):
    return " ".join(t for t in n.split() if t not in ENCHIMENTO) or n

def pct(x): return f"{round(100 * x)}%"
def virg(x, casas=2): return f"{x:.{casas}f}".replace(".", ",")
def justa(p): return "–" if p <= 0.005 else virg(1 / p) if p > 0.1 else str(round(1 / p))


# ---------------- dados ----------------
def _ler_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (apostas-do-dia)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8-sig", errors="replace")

def _data(s):
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try: return datetime.strptime(s.strip(), f).date()
        except ValueError: pass
    return None

def _odd(l, *chaves):
    for trio in chaves:
        try:
            v = [float(l[k]) for k in trio]
            if all(x > 1 for x in v): return [f"{x:g}" for x in v]
        except (KeyError, ValueError, TypeError): pass
    return ["", "", ""]

def _gravar(caminho, cabecalho, linhas):
    os.makedirs(PASTA, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=PASTA, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(cabecalho); w.writerows(linhas)
    os.chmod(tmp, 0o644); os.replace(tmp, caminho)

def _epocas_recentes(hoje, n=5):
    a = hoje.year if hoje.month >= 7 else hoje.year - 1
    return [f"{(a - i) % 100:02d}{(a - i + 1) % 100:02d}" for i in range(n)]

def atualizar():
    hoje = date.today()
    corte = (hoje - timedelta(days=round(365.25 * ANOS_CLUBES))).isoformat()
    jogos = {(j["liga"], j["data"].isoformat(), j["casa"], j["fora"]): [str(j["gc"]), str(j["gf"]), *j["odds"]] for j in carregar_clubes()}
    falhas = []
    def juntar(liga, url, cols, odds, pais=None):
        try: txt = _ler_url(url)
        except Exception as e: return falhas.append(f"{url}: {e}")
        for l in csv.DictReader(io.StringIO(txt)):
            if pais and (l.get("Country") or "").strip() != pais: return falhas.append(f"{url}: devolveu outra liga")
            d = _data(l.get("Date") or ""); gc, gf = (l.get(cols[2]) or "").strip(), (l.get(cols[3]) or "").strip()
            if d and gc.isdigit() and gf.isdigit():
                jogos[(liga, d.isoformat(), l[cols[0]].strip(), l[cols[1]].strip())] = [gc, gf, *_odd(l, *odds)]
    for liga in LIGAS_EPOCA:
        for ep in _epocas_recentes(hoje):
            juntar(liga, f"{FD}/mmz4281/{ep}/{liga}.csv", ("HomeTeam", "AwayTeam", "FTHG", "FTAG"), (("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A")))
    for liga, (pais, _) in LIGAS_UNICAS.items():
        juntar(liga, f"{FD}/new/{liga}.csv", ("Home", "Away", "HG", "AG"), (("AvgCH", "AvgCD", "AvgCA"), ("PSCH", "PSCD", "PSCA"), ("B365CH", "B365CD", "B365CA")), pais)
    saida = sorted([*k, *v] for k, v in jogos.items() if k[1] >= corte)
    _gravar(CLUBES, ["liga", "data", "casa", "fora", "gc", "gf", "o1", "ox", "o2"], saida)
    print(f"clubes: {len(saida)} jogos em {len({x[0] for x in saida})} ligas, até {max((x[1] for x in saida), default='–')}")
    try:
        corte_s = hoje - timedelta(days=round(365.25 * ANOS_SELECOES))
        sel = []
        for l in csv.DictReader(io.StringIO(_ler_url(SEL_URL))):
            d = _data(l["date"])
            if d and corte_s <= d <= hoje and l["home_score"].isdigit() and l["away_score"].isdigit():
                sel.append([l["date"], l["home_team"], l["away_team"], l["home_score"], l["away_score"], l["tournament"], "1" if l["neutral"].upper() == "TRUE" else "0"])
        sel.sort()
        _gravar(SELECOES, ["data", "casa", "fora", "gc", "gf", "torneio", "neutro"], sel)
        print(f"seleções: {len(sel)} jogos, até {sel[-1][0]}")
    except Exception as e:
        falhas.append(f"seleções: {e}")
    for f in falhas: print("AVISO: falhou", f)

def carregar_clubes():
    if not os.path.exists(CLUBES): return []
    with open(CLUBES, encoding="utf-8") as f:
        return [{"liga": l["liga"], "data": date.fromisoformat(l["data"]), "casa": l["casa"], "fora": l["fora"], "gc": int(l["gc"]), "gf": int(l["gf"]),
                 "odds": [l["o1"], l["ox"], l["o2"]], "neutro": False, "peso": 1.0} for l in csv.DictReader(f)]

def carregar_selecoes():
    if not os.path.exists(SELECOES): return []
    with open(SELECOES, encoding="utf-8") as f:
        return [{"liga": "SEL", "data": date.fromisoformat(l["data"]), "casa": l["casa"], "fora": l["fora"], "gc": int(l["gc"]), "gf": int(l["gf"]),
                 "torneio": l["torneio"], "neutro": l["neutro"] == "1", "peso": 0.6 if l["torneio"] == "Friendly" else 1.0} for l in csv.DictReader(f)]

def carregar_alias():
    if not os.path.exists(ALIAS): return {"clubes": {}, "selecoes": {}}
    with open(ALIAS, encoding="utf-8") as f: a = json.load(f)
    return {k: {norm(x): y for x, y in a.get(k, {}).items()} for k in ("clubes", "selecoes")}


# ---------------- nomes ----------------
def procurar(nome, universo, alias):
    """Devolve (nome nos dados, exato?) ou (None, sugestões)."""
    n = norm(nome)
    por_norm = {norm(u): u for u in universo}
    if alias.get(n) in universo: return alias[n], True
    if n in por_norm: return por_norm[n], True
    curto = {sem_enchimento(k): v for k, v in por_norm.items()}
    if sem_enchimento(n) in curto: return curto[sem_enchimento(n)], True
    perto = difflib.get_close_matches(sem_enchimento(n), list(curto), n=3, cutoff=0.72)
    if perto and difflib.SequenceMatcher(None, sem_enchimento(n), perto[0]).ratio() >= 0.9: return curto[perto[0]], False
    return None, [curto[p] for p in perto]

def liga_da_comp(comp):
    c = norm(comp or "")
    if not c: return None
    if any(k in c for k in COMP_SELECOES): return "SEL"
    return next((liga for chave, liga in COMP_LIGA if norm(chave) in c), "?")


# ---------------- modelo ----------------
def ajustar(jogos, hoje, meia_vida, janela, previo=8.0):
    """Forças de ataque e defesa por equipa (Poisson, com mais peso nos jogos recentes)."""
    js = []
    for j in jogos:
        idade = (hoje - j["data"]).days
        if 0 < idade <= janela: js.append((j["casa"], j["fora"], j["gc"], j["gf"], j["peso"] * 0.5 ** (idade / meia_vida), j["neutro"]))
    equipas = {e for j in js for e in j[:2]}
    if len(js) < 30: return None
    a = dict.fromkeys(equipas, 1.0); d = dict.fromkeys(equipas, 1.0)
    base = sum(w * (gc + gf) for *_, gc, gf, w, _ in js) / (2 * sum(j[4] for j in js)); H = 1.2
    for _ in range(40):
        na, da, nd, dd = (defaultdict(float) for _ in range(4))
        for c, f, gc, gf, w, neutro in js:
            h = 1.0 if neutro else H
            na[c] += w * gc; da[c] += w * base * h * d[f]; na[f] += w * gf; da[f] += w * base * d[c]
            nd[f] += w * gc; dd[f] += w * base * h * a[c]; nd[c] += w * gf; dd[c] += w * base * a[f]
        k = previo * base
        a = {e: (na[e] + k) / (da[e] + k) for e in equipas}; d = {e: (nd[e] + k) / (dd[e] + k) for e in equipas}
        ma, md = sum(a.values()) / len(a), sum(d.values()) / len(d)
        a = {e: v / ma for e, v in a.items()}; d = {e: v / md for e, v in d.items()}
        com_casa = [j for j in js if not j[5]]
        if com_casa: H = sum(j[4] * j[2] for j in com_casa) / sum(j[4] * base * a[j[0]] * d[j[1]] for j in com_casa)
        base = sum(w * (gc + gf) for *_, gc, gf, w, _ in js) / sum(w * ((1.0 if n else H) * a[c] * d[f] + a[f] * d[c]) for c, f, _, _, w, n in js)
    return {"a": a, "d": d, "H": H, "base": base}

RHO = -0.08  # correção dos resultados baixos (Dixon-Coles): sem ela os empates ficam subestimados
PESO_TOTAL = 0.6  # o total de golos de um jogo afasta-se da média da liga menos do que as forças das equipas sugerem

def mercados(m, casa, fora, neutro=False):
    mc = m["base"] * (1.0 if neutro else m["H"]) * m["a"][casa] * m["d"][fora]
    mf = m["base"] * m["a"][fora] * m["d"][casa]
    media = m["base"] * ((1.0 if neutro else m["H"]) + 1)
    k = (media + PESO_TOTAL * (mc + mf - media)) / (mc + mf); mc *= k; mf *= k
    pc = [math.exp(-mc) * mc ** i / math.factorial(i) for i in range(11)]
    pf = [math.exp(-mf) * mf ** i / math.factorial(i) for i in range(11)]
    g = [[pc[i] * pf[j] for j in range(11)] for i in range(11)]
    g[0][0] *= 1 - mc * mf * RHO; g[0][1] *= 1 + mc * RHO; g[1][0] *= 1 + mf * RHO; g[1][1] *= 1 - RHO
    t = sum(map(sum, g)); g = [[x / t for x in l] for l in g]
    p1 = sum(g[i][j] for i in range(11) for j in range(i)); px = sum(g[i][i] for i in range(11)); p2 = 1 - p1 - px
    tot = lambda n: sum(g[i][j] for i in range(11) for j in range(11) if i + j > n)
    return {"golos_casa": mc, "golos_fora": mf, "1": p1, "X": px, "2": p2, "1X": p1 + px, "X2": px + p2, "12": p1 + p2,
            "dnb1": p1 / (p1 + p2), "dnb2": p2 / (p1 + p2), "ambas": 1 - sum(g[0]) - sum(l[0] for l in g) + g[0][0],
            "+1,5": tot(1.5), "+2,5": tot(2.5), "+3,5": tot(3.5)}


# ---------------- estatísticas brutas ----------------
def registo(jogos, equipa, onde):
    v = e = d = gm = gs = am = m25 = 0
    for j in jogos:
        em_casa = j["casa"] == equipa
        if (onde == "casa" and not em_casa) or (onde == "fora" and em_casa): continue
        f, c = (j["gc"], j["gf"]) if em_casa else (j["gf"], j["gc"])
        v += f > c; e += f == c; d += f < c; gm += f; gs += c; am += f > 0 and c > 0; m25 += f + c > 2
    n = v + e + d
    return {"n": n, "v": v, "e": e, "d": d, "gm": gm / n if n else 0, "gs": gs / n if n else 0, "ambas": am / n if n else 0, "+2,5": m25 / n if n else 0}

def forma(jogos, equipa, n=6):
    return "".join("V" if (g := (j["gc"] - j["gf"]) * (1 if j["casa"] == equipa else -1)) > 0 else "E" if g == 0 else "D" for j in jogos[-n:])

def analisar(casa, fora, comp="", neutro=False, hoje=None):
    hoje = hoje or date.today()
    r = {"pedido": f"{casa} – {fora}", "avisos": []}
    if SEM_DADOS.search(f"{norm(comp)} | {norm(casa)} | {norm(fora)} |"):
        return {**r, "erro": "sem dados: só há épocas passadas de equipas principais masculinas"}
    alias = carregar_alias(); liga = liga_da_comp(comp)
    sel = carregar_selecoes(); nomes_sel = {e for j in sel for e in (j["casa"], j["fora"])}
    sc, sf = procurar(casa, nomes_sel, alias["selecoes"]), procurar(fora, nomes_sel, alias["selecoes"])
    if liga == "SEL" or (liga is None and sc[0] and sf[0] and sc[1] and sf[1]):
        if not (sc[0] and sf[0]):
            falta = [f"{n} (parecidos: {', '.join(x[1]) or 'nenhum'})" for n, x in ((casa, sc), (fora, sf)) if not x[0]]
            return {**r, "erro": "seleção não encontrada: " + "; ".join(falta)}
        jogos, c, f, liga, janela, meia, recente = sel, sc[0], sf[0], "SEL", 365 * 6, 730, 365 * 3
        aprox = [x for x, y in ((c, sc), (f, sf)) if not y[1]]
    else:
        clubes = carregar_clubes()
        por_liga = defaultdict(set)
        for j in clubes:
            if (hoje - j["data"]).days <= 800: por_liga[j["liga"]].update((j["casa"], j["fora"]))
        if liga == "?": return {**r, "erro": f"sem dados de épocas passadas para a competição '{comp}'"}
        cand = []
        for lg in ([liga] if liga else por_liga):
            cc, cf = procurar(casa, por_liga[lg], alias["clubes"]), procurar(fora, por_liga[lg], alias["clubes"])
            if cc[0] and cf[0]: cand.append((cc[1] + cf[1], lg, cc, cf))
        if not cand:
            todos = set().union(*por_liga.values()) if por_liga else set()
            falta = [f"{n} (parecidos: {', '.join(x[1]) or 'nenhum'})" for n in (casa, fora) if not (x := procurar(n, todos, alias["clubes"]))[0]]
            return {**r, "erro": ("equipa não encontrada: " + "; ".join(falta)) if falta else "as duas equipas não jogam na mesma liga dos dados (competições europeias e taças não estão cobertas)"}
        _, liga, cc, cf = max(cand, key=lambda x: x[0])
        jogos, c, f, janela, meia, recente = [j for j in clubes if j["liga"] == liga], cc[0], cf[0], 365 * 3, 365, 730
        aprox = [x for x, y in ((c, cc), (f, cf)) if not y[1]]
    jogos = [j for j in jogos if j["data"] < hoje]
    rec = [j for j in jogos if (hoje - j["data"]).days <= recente]
    de = lambda e, js: [j for j in js if e in (j["casa"], j["fora"])]
    nc, nf = (x if norm(x) == norm(y) else f"{y} ({x})" for x, y in ((c, casa), (f, fora)))
    r.update(jogo=f"{nc} – {nf}", liga="Seleções" if liga == "SEL" else NOME_LIGA[liga], dados_ate=max(j["data"] for j in jogos).isoformat(),
             casa={"nome": nc, "em_casa": registo(de(c, rec), c, "casa"), "total": registo(de(c, rec), c, ""), "forma": forma(de(c, jogos), c)},
             fora={"nome": nf, "fora": registo(de(f, rec), f, "fora"), "total": registo(de(f, rec), f, ""), "forma": forma(de(f, jogos), f)})
    cd = [j for j in jogos if {j["casa"], j["fora"]} == {c, f}][-8:]
    r["confronto"] = {"v_casa": sum((j["gc"] - j["gf"]) * (1 if j["casa"] == c else -1) > 0 for j in cd), "e": sum(j["gc"] == j["gf"] for j in cd),
                      "v_fora": sum((j["gc"] - j["gf"]) * (1 if j["casa"] == f else -1) > 0 for j in cd),
                      "jogos": [f'{j["data"].isoformat()} {j["casa"]} {j["gc"]}-{j["gf"]} {j["fora"]}' for j in cd]}
    if aprox: r["avisos"].append("nome aproximado, confirmar: " + ", ".join(aprox))
    for e, n in ((c, r["casa"]["total"]["n"]), (f, r["fora"]["total"]["n"])):
        if n < 12: r["avisos"].append(f"{e}: só {n} jogos recentes nos dados, estimativa pouco fiável")
    if liga == "SEL" and not neutro: r["avisos"].append("assume que a primeira seleção joga em casa; usar --neutro em campo neutro")
    m = ajustar(jogos, hoje, meia, janela)
    if m and c in m["a"] and f in m["a"]: r["modelo"] = mercados(m, c, f, neutro)
    else: r["avisos"].append("jogos insuficientes para estimar probabilidades")
    return r

def texto(r):
    if "erro" in r: return f'{r["pedido"]}\n  {r["erro"]}'
    def reg(x): return f'{x["n"]} jogos · {x["v"]}V {x["e"]}E {x["d"]}D · golos {virg(x["gm"], 1)}–{virg(x["gs"], 1)} · ambas marcam {pct(x["ambas"])} · +2,5 golos {pct(x["+2,5"])}'
    c, f, cd = r["casa"], r["fora"], r["confronto"]
    sel = r["liga"] == "Seleções"
    out = [f'{r["jogo"]} · {r["liga"]} · dados até {r["dados_ate"]}',
           f'  {c["nome"]} {"(últimos 3 anos)" if sel else "em casa (2 épocas)"}: {reg(c["total"] if sel else c["em_casa"])} · forma {c["forma"]}',
           f'  {f["nome"]} {"(últimos 3 anos)" if sel else "fora (2 épocas)"}: {reg(f["total"] if sel else f["fora"])} · forma {f["forma"]}',
           f'  Confronto direto ({len(cd["jogos"])} jogos): {cd["v_casa"]}V {cd["e"]}E {cd["v_fora"]}D para {c["nome"]}' + (" · " + "; ".join(cd["jogos"][-4:]) if cd["jogos"] else "")]
    if "modelo" in r:
        m = r["modelo"]; pj = lambda k: f"{pct(m[k])} ({justa(m[k])})"
        out += [f'  Probabilidade (odd justa): 1 {pj("1")} · X {pj("X")} · 2 {pj("2")} · 1X {pj("1X")} · X2 {pj("X2")} · 12 {pj("12")}',
                f'    empate anula: 1 {pj("dnb1")} · 2 {pj("dnb2")} · ambas marcam {pj("ambas")} · +1,5 {pj("+1,5")} · +2,5 {pj("+2,5")} · +3,5 {pj("+3,5")} · golos esperados {virg(m["golos_casa"], 1)}–{virg(m["golos_fora"], 1)}']
    return "\n".join(out + [f"  AVISO: {a}" for a in r["avisos"]])


# ---------------- avaliação ----------------
def avaliar():
    hoje = date.today(); clubes = carregar_clubes()
    por_liga = defaultdict(list)
    for j in clubes: por_liga[j["liga"]].append(j)
    prev = []
    for liga, jogos in por_liga.items():
        ini = date(hoje.year - 1, hoje.month, 1)
        while ini < hoje:
            fim = date(ini.year + (ini.month == 12), ini.month % 12 + 1, 1)
            m = ajustar(jogos, ini, 365, 365 * 3)
            for j in jogos:
                if m and ini <= j["data"] < fim and j["casa"] in m["a"] and j["fora"] in m["a"] and all(j["odds"]):
                    p = mercados(m, j["casa"], j["fora"]); o = [float(x) for x in j["odds"]]; s = sum(1 / x for x in o)
                    prev.append(([p["1"], p["X"], p["2"]], [1 / x / s for x in o], o, 0 if j["gc"] > j["gf"] else 1 if j["gc"] == j["gf"] else 2, p["+2,5"], j["gc"] + j["gf"] > 2, p["ambas"], j["gc"] > 0 and j["gf"] > 0))
            ini = fim
    if not prev: return print("sem jogos com odds para avaliar")
    ll = lambda i: -sum(math.log(max(x[i][x[3]], 1e-9)) for x in prev) / len(prev)
    print(f"{len(prev)} jogos de {len(por_liga)} ligas nos últimos 12 meses, cada um previsto só com resultados anteriores")
    print(f"erro (log-loss, menor é melhor): modelo {virg(ll(0), 3)} · odds de fecho {virg(ll(1), 3)} · palpite cego 1,099")
    print("\nfavorito do modelo: probabilidade prevista vs. vezes que ganhou")
    for a, b in ((0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)):
        g = [(max(x[0]), x[0].index(max(x[0])) == x[3]) for x in prev if a <= max(x[0]) < b]
        if g: print(f"  {pct(a)}–{pct(min(b, 1))}: {len(g):5d} jogos · previsto {pct(sum(p for p, _ in g) / len(g))} · real {pct(sum(c for _, c in g) / len(g))}")
    for nome, ip, ic in (("+2,5 golos", 4, 5), ("ambas marcam", 6, 7)):
        print(f"\n{nome}: previsto vs. real")
        for a, b in ((0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.01)):
            g = [(x[ip], x[ic]) for x in prev if a <= x[ip] < b]
            if g: print(f"  {pct(a)}–{pct(min(b, 1))}: {len(g):5d} jogos · previsto {pct(sum(p for p, _ in g) / len(g))} · real {pct(sum(c for _, c in g) / len(g))}")
    print("\napostar 1 unidade no resultado sempre que a odd de fecho supera a odd justa do modelo em 10%:")
    ap = [(x[2][i], i == x[3]) for x in prev for i in range(3) if x[0][i] * x[2][i] > 1.10 and x[0][i] > 0.35]
    if ap: print(f"  {len(ap)} apostas · acertou {pct(sum(c for _, c in ap) / len(ap))} · retorno {virg(100 * (sum(o for o, c in ap if c) - len(ap)) / len(ap), 1)}% por aposta")
    print("\nfavoritos por faixa de odd de fecho: vezes que ganharam")
    for a, b in ((1.0, 1.2), (1.2, 1.4), (1.4, 1.6), (1.6, 1.8), (1.8, 2.1), (2.1, 2.6)):
        g = [min(x[2]) == x[2][x[3]] for x in prev if a <= min(x[2]) < b]
        if g: print(f"  {virg(a)}–{virg(b)}: {len(g):5d} jogos · ganhou {pct(sum(g) / len(g))} · necessário para não perder dinheiro {pct(2 / (a + b))}")


# ---------------- odds de épocas passadas ----------------
FAIXAS = (1.0, 1.15, 1.3, 1.5, 1.75, 2.1, 2.7, 3.5, 5.0, 1e9)

def acerto_por_odd():
    """Por faixa de odd, quantas vezes ganhou realmente uma seleção com essa odd de fecho (resultado final, todas as ligas)."""
    cont = [[0, 0, 0.0] for _ in FAIXAS[:-1]]
    for j in carregar_clubes():
        if not all(j["odds"]): continue
        r = 0 if j["gc"] > j["gf"] else 1 if j["gc"] == j["gf"] else 2
        for i, o in enumerate(map(float, j["odds"])):
            f = next(k for k in range(len(cont)) if FAIXAS[k] <= o < FAIXAS[k + 1])
            cont[f][0] += 1; cont[f][1] += r == i; cont[f][2] += 1 / o
    return [(FAIXAS[k], FAIXAS[k + 1], n, g / n, g / imp) for k, (n, g, imp) in enumerate(cont) if n]

def prob_odd(o, tabela):
    """Probabilidade histórica de uma seleção com esta odd: 1/odd corrigido pela margem observada na faixa."""
    return min(0.99, next((racio for a, b, _, _, racio in tabela if a <= o < b), 0.93) / o)

def boletim(caminho):
    with open(caminho, encoding="utf-8") as f: d = json.load(f)
    tabela = acerto_por_odd()
    if not tabela: return print("sem odds de épocas passadas: correr primeiro epocas.py --atualizar")
    for b in d.get("hoje", []) + d.get("proximos", []):
        ps = [prob_odd(float(l["o"].replace(",", ".")), tabela) for l in b["legs"]]
        total = math.prod(float(l["o"].replace(",", ".")) for l in b["legs"])
        print(f'{b["c"]} {b["t"]} · odd {virg(total)} · probabilidade histórica de acertar {pct(math.prod(ps))}' + (f' (pernas: {" · ".join(pct(x) for x in ps)})' if len(ps) > 1 else ""))
    print("\nodds de fecho em épocas passadas (todas as ligas dos dados):")
    for a, b, n, real, _ in tabela:
        print(f"  odd {virg(a)}–{virg(b) if b < 1e8 else '…'}: {n:6d} seleções · ganharam {pct(real)}")


def main(args):
    if not args or "--help" in args or "-h" in args: return print(USO)
    if args[0] == "--atualizar": return atualizar()
    if args[0] == "--avaliar": return avaliar()
    if args[0] == "--boletim": return boletim(args[1]) if len(args) > 1 else print(USO)
    if args[0] == "--equipas":
        t = norm(" ".join(args[1:]))
        for nome, js in (("clubes", carregar_clubes()), ("seleções", carregar_selecoes())):
            print(nome + ":", ", ".join(sorted({e for j in js for e in (j["casa"], j["fora"]) if t in norm(e)})) or "–")
        return
    comp = args[args.index("--comp") + 1] if "--comp" in args else ""
    jogos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--comp")]
    res = []
    for j in jogos:
        partes = re.split(r"\s+(?:-|–|vs\.?|x)\s+|–", j, maxsplit=1)
        res.append(analisar(partes[0].strip(), partes[1].strip(), comp, "--neutro" in args) if len(partes) == 2 else {"pedido": j, "erro": 'escreve o jogo como "Casa - Fora"', "avisos": []})
    print(json.dumps(res, ensure_ascii=False, indent=1) if "--json" in args else "\n\n".join(texto(r) for r in res))

if __name__ == "__main__":
    main(sys.argv[1:])
