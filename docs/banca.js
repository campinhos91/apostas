/* Separador Banca: simula 1 € em cada boletim, com filtros. A app carrega este ficheiro e o gerar.py embute-o na página. */
(function () {
"use strict";
var APOSTA = 1;
var TIPOS = [["t1", "Simples", "Aposta simples segura"], ["t2", "Segura", "Múltipla segura"], ["t3", "Arriscada", "Múltipla arriscada"], ["t4", "Próximos", "Múltipla dos próximos dias"]];
var ODDS = [["a", "até 1,50", 0, 1.5], ["b", "1,51–2,50", 1.5, 2.5], ["c", "2,51–5,00", 2.5, 5], ["d", "mais de 5", 5, Infinity]];
var PERNAS = [["1", "1"], ["2", "2"], ["3", "3"], ["4", "4 ou mais"]];
var PERIODOS = [["0", "Tudo"], ["7", "7 dias"], ["14", "14 dias"], ["30", "30 dias"]];
var SEM_COMP = "Sem competição registada";
var MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
var CSS = '.bf{display:flex;flex-direction:column;gap:10px;margin:16px 0 20px}' +
  '.bg{display:flex;align-items:flex-start;gap:10px;min-width:0}' +
  '.bn{flex:0 0 84px;font-size:12.5px;line-height:36px;color:var(--soft)}' +
  '.bc{display:flex;flex-wrap:wrap;gap:6px;min-width:0}' +
  '.ch{appearance:none;flex:0 0 auto;min-height:36px;padding:0 13px;border-radius:999px;border:1px solid var(--hair);background:var(--card);color:var(--ink);font-family:inherit;font-size:13px;font-weight:500;cursor:pointer;white-space:nowrap;touch-action:manipulation}' +
  '.ch[aria-pressed="true"]{background:var(--pitch-soft);border-color:var(--pitch);color:var(--pitch);font-weight:600}' +
  '.ch:focus-visible,.bg select:focus-visible,.bl:focus-visible{outline:2px solid var(--pitch);outline-offset:1px}' +
  '.bg select{flex:1 1 auto;min-width:0;max-width:340px;min-height:36px;border-radius:12px;border:1px solid var(--hair);background:var(--card);color:var(--ink);font-family:inherit;font-size:13px;padding:0 10px}' +
  '.bx{display:flex;justify-content:space-between;align-items:center;gap:12px;min-height:36px;font-size:12.5px;color:var(--soft)}' +
  '.bl{appearance:none;border:0;background:none;color:var(--pitch);font-family:inherit;font-size:13px;font-weight:600;cursor:pointer;padding:8px 0;text-decoration:underline}' +
  '.bt{margin:10px 0 0;font-size:12.5px;color:var(--soft)}' +
  '.mr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 14px;align-items:center;padding:13px var(--bp,16px);border-top:1px dashed var(--hair)}' +
  '.mr:first-child{border-top:0}.mr .sp{white-space:nowrap}.sp.z{color:var(--soft)}.sum.hs b,.sum.g2 b{white-space:nowrap}' +
  '.gb{margin:0;padding:16px var(--bp,16px) 4px}' +
  '.gp{position:relative;height:160px;touch-action:pan-y}' +
  '.gp svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}' +
  '.gl{fill:none;stroke:var(--pitch);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}' +
  '.g0{stroke:var(--grey);stroke-width:1;stroke-dasharray:3 4}' +
  '.gz,.gb figcaption,.gt b{font-family:var(--mono,"IBM Plex Mono",ui-monospace,monospace)}' +
  '.gz{position:absolute;left:0;transform:translateY(-120%);font-size:11px;color:var(--soft)}' +
  '.gd{position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;background:var(--pitch);box-shadow:0 0 0 2px var(--card)}' +
  '.gh{position:absolute;top:0;bottom:0;width:1px;background:var(--grey)}' +
  '.gt{position:absolute;top:0;z-index:2;background:var(--card);border:1px solid var(--hair);border-radius:10px;padding:6px 10px;box-shadow:var(--shadow);pointer-events:none;white-space:nowrap;display:flex;flex-direction:column;font-size:12px;color:var(--soft)}' +
  '.gt b{font-size:15px;color:var(--ink)}' +
  '.gb figcaption{display:flex;justify-content:space-between;gap:12px;margin-top:8px;font-size:11px;color:var(--soft)}' +
  '.bf [hidden],.gp [hidden]{display:none}' +
  '@media(max-width:479px){.bn{flex-basis:70px}}';

var F = filtrosVazios(), dados = [];
function filtrosVazios() { return {periodo: "0", tipos: {}, odds: {}, pernas: {}, mercado: "", comp: ""}; }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
function num(s) { return parseFloat(String(s).replace(",", ".")); }
function r2(x) { return Math.round(x * 100) / 100; }
function virg(x, casas) { return Math.abs(x).toFixed(casas).replace(".", ","); }
function sinal(x, mostra) { return x < 0 ? "−" : mostra && x > 0 ? "+" : ""; }
function eur(x, mostra) { return sinal(x, mostra) + virg(x, 2) + " €"; }
function perc(x, mostra) { return sinal(x, mostra) + virg(x, 1) + "%"; }
function ativo(o) { return Object.keys(o).length > 0; }
function faixa(t) { for (var i = 0; i < ODDS.length; i++) if (t > ODDS[i][2] && t <= ODDS[i][3]) return ODDS[i][0]; return "a"; }

function preparar(hist) {
  var bs = [];
  (hist || []).forEach(function (e) {
    var nome = String(e.rotulo || e.dia).split(" de 20")[0].replace(" · ", ", ");
    (e.boletins || []).forEach(function (b) {
      var ms = {}, cs = {};
      b.legs.forEach(function (l) { ms[String(l.m).split(":")[0].trim()] = 1; cs[l.comp || SEM_COMP] = 1; });
      bs.push({dia: e.dia, nome: nome, c: b.c, t: b.t, total: num(b.total), e: b.e, n: Math.min(b.legs.length, 4), ms: ms, cs: cs});
    });
  });
  return bs;
}
function desde() {
  if (F.periodo === "0" || !dados.length) return "";
  var ult = dados.reduce(function (m, b) { return b.dia > m ? b.dia : m; }, ""), d = new Date(ult + "T12:00:00");
  d.setDate(d.getDate() - (parseInt(F.periodo, 10) - 1));
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}
function passa(b, ini) {
  return b.dia >= ini && (!ativo(F.tipos) || F.tipos[b.c]) && (!ativo(F.odds) || F.odds[faixa(b.total)]) && (!ativo(F.pernas) || F.pernas[String(b.n)]) &&
    (!F.mercado || b.ms[F.mercado]) && (!F.comp || b.cs[F.comp]);
}
function contas(l) {
  var dec = l.filter(function (b) { return b.e === "ganho" || b.e === "perdido"; }), g = dec.filter(function (b) { return b.e === "ganho"; });
  var ap = dec.length * APOSTA, rec = r2(g.reduce(function (s, b) { return s + r2(APOSTA * b.total); }, 0));
  return {dec: dec.length, ganhos: g.length, apostado: ap, recebido: rec, saldo: r2(rec - ap), retorno: ap ? 100 * (rec - ap) / ap : 0,
    odd: g.length ? g.reduce(function (s, b) { return s + b.total; }, 0) / g.length : 0,
    adiados: l.filter(function (b) { return b.e === "adiado"; }).length, emJogo: l.filter(function (b) { return b.e !== "ganho" && b.e !== "perdido" && b.e !== "adiado"; }).length};
}
function cor(x) { return x < 0 ? " lo" : x > 0 ? "" : " z"; }
function linha(nome, c, extra) {
  var sub = c.dec ? c.ganhos + " " + (c.ganhos === 1 ? "ganho" : "ganhos") + " em " + c.dec + " (" + Math.round(100 * c.ganhos / c.dec) + "%) · retorno " + perc(c.retorno, true) : "sem boletins decididos";
  return '<div class="mr"><div class="sl"><b>' + esc(nome) + '</b><small>' + esc(sub + (extra ? " · " + extra : "")) + '</small></div><span class="sp' + cor(c.saldo) + '">' + eur(c.saldo, true) + '</span></div>';
}
function bloco(titulo, linhas, nota) {
  return linhas.length ? '<section class="hday"><div class="head"><h2>' + titulo + '</h2></div><article class="tk">' + linhas.join("") + (nota ? '<p class="pn">' + nota + '</p>' : "") + '</article></section>' : "";
}
function porChave(l, chaves, ordem) {
  var g = {};
  l.forEach(function (b) { chaves(b).forEach(function (k) { (g[k] = g[k] || []).push(b); }); });
  var ks = ordem ? ordem.filter(function (k) { return g[k]; }) : Object.keys(g).sort(function (a, b) { return g[b].length - g[a].length || a.localeCompare(b); });
  return ks.map(function (k) { return [k, contas(g[k])]; }).filter(function (x) { return x[1].dec; });
}
function diaCurto(d) { return parseInt(d.slice(8), 10) + " " + MESES[parseInt(d.slice(5, 7), 10) - 1]; }
function grafico(dias) {
  if (dias.length < 2) return "";
  var vals = [0].concat(dias.map(function (d) { return d.banca; })), lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  if (hi === lo) hi = lo + 1;
  var X = function (i) { return r2(100 * i / (vals.length - 1)); }, Y = function (v) { return r2(8 + 84 * (hi - v) / (hi - lo)); };
  var pts = [[X(0), Y(0), "Início", eur(0), ""]].concat(dias.map(function (d, i) { return [X(i + 1), Y(d.banca), d.nome, eur(d.banca, true), eur(d.saldo, true)]; }));
  var fim = pts[pts.length - 1];
  return '<figure class="gb" data-pts="' + esc(JSON.stringify(pts)) + '"><div class="gp"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' +
    '<line class="g0" x1="0" x2="100" y1="' + Y(0) + '" y2="' + Y(0) + '" vector-effect="non-scaling-stroke"/>' +
    '<path class="gl" d="M' + pts.map(function (p) { return p[0] + " " + p[1]; }).join(" L") + '" vector-effect="non-scaling-stroke"/></svg>' +
    '<span class="gz" style="top:' + Y(0) + '%">0 €</span><i class="gh" hidden></i><i class="gd" style="left:' + fim[0] + '%;top:' + fim[1] + '%"></i>' +
    '<div class="gt" hidden><small></small><b></b><span></span></div></div>' +
    '<figcaption><span>' + diaCurto(dias[0].dia) + '</span><span>máx. ' + eur(hi, true) + ' · mín. ' + eur(lo, true) + '</span><span>' + diaCurto(dias[dias.length - 1].dia) + '</span></figcaption></figure>';
}
function ligarGrafico(el) {
  var f = el.querySelector(".gb"); if (!f) return;
  var P = JSON.parse(f.dataset.pts), g = f.querySelector(".gp"), h = g.querySelector(".gh"), d = g.querySelector(".gd"), t = g.querySelector(".gt"), u = P[P.length - 1];
  function em(p, on) {
    d.style.left = p[0] + "%"; d.style.top = p[1] + "%"; h.hidden = t.hidden = !on; if (!on) return;
    h.style.left = t.style.left = p[0] + "%"; t.style.transform = p[0] > 50 ? "translateX(calc(-100% - 10px))" : "translateX(10px)"; t.style.top = Math.min(Math.max(p[1] - 20, 0), 58) + "%";
    t.children[0].textContent = p[2]; t.children[1].textContent = p[3]; t.children[2].textContent = p[4] ? "no dia " + p[4] : "";
  }
  function mv(ev) { var r = g.getBoundingClientRect(), x = 100 * (ev.clientX - r.left) / r.width, b = P[0]; for (var i = 1; i < P.length; i++) if (Math.abs(P[i][0] - x) < Math.abs(b[0] - x)) b = P[i]; em(b, true); }
  g.addEventListener("pointermove", mv); g.addEventListener("pointerdown", mv); g.addEventListener("pointerleave", function () { em(u, false); });
}

function resultado(el) {
  var ini = desde(), noPeriodo = dados.filter(function (b) { return b.dia >= ini; }), l = dados.filter(function (b) { return passa(b, ini); }), c = contas(l), tudo = contas(dados);
  var filtrado = F.periodo !== "0" || ativo(F.tipos) || ativo(F.odds) || ativo(F.pernas) || F.mercado || F.comp;
  el.querySelector(".bq").textContent = filtrado ? c.dec + " de " + tudo.dec + " boletins decididos" : tudo.dec + " boletins decididos";
  el.querySelector(".bl").hidden = !filtrado;
  var r = el.querySelector(".br");
  if (!c.dec) { r.innerHTML = '<p class="calm">' + (tudo.dec ? "Nenhum boletim decidido com estes filtros." : "Ainda não há boletins decididos para simular a banca.") + '</p>'; return; }
  var neg = c.saldo < 0 ? "p" : "";
  var h = '<div class="sum hs g2"><div class="' + neg + '"><small>Banca</small><b>' + eur(c.saldo, true) + '</b></div><div class="' + neg + '"><small>Retorno</small><b>' + perc(c.retorno, true) + '</b></div>' +
    '<div class="n"><small>Acerto · ' + c.ganhos + ' em ' + c.dec + '</small><b>' + Math.round(100 * c.ganhos / c.dec) + '%</b></div><div class="n"><small>Odd dos ganhos</small><b>' + (c.odd ? virg(c.odd, 2) : "–") + '</b></div></div>' +
    '<p class="bt">Apostado ' + eur(c.apostado) + ' · recebido ' + eur(c.recebido) + '.' + (c.odd ? ' Os boletins ganhos tinham odd média ' + virg(c.odd, 2) + ': com essa odd era preciso acertar ' + Math.round(100 / c.odd) +
      '% para não perder, e o acerto foi de ' + Math.round(100 * c.ganhos / c.dec) + '%.' : "") + '</p>';
  var porDia = {}, acum = 0;
  noPeriodo.forEach(function (b) { porDia[b.dia] = porDia[b.dia] || {dia: b.dia, nome: b.nome, l: []}; });
  l.forEach(function (b) { porDia[b.dia].l.push(b); });
  var dias = Object.keys(porDia).sort().map(function (k) { var x = contas(porDia[k].l); acum = r2(acum + x.saldo); return {dia: k, nome: porDia[k].nome, c: x, saldo: x.saldo, banca: acum}; });
  var g = grafico(dias);
  if (g) h += bloco("Evolução da banca", [g], "Banca acumulada no fim de cada dia, a partir de 0 €. Cada boletim conta no dia em que foi publicado.");
  var nomeTipo = {}, nomeOdd = {}; TIPOS.forEach(function (t) { nomeTipo[t[0]] = t[2]; }); ODDS.forEach(function (o) { nomeOdd[o[0]] = "Odd total " + o[1].replace("–", " a "); });
  var varias = "Um boletim entra em todas as linhas a que as suas pernas pertencem, por isso as linhas não somam o total.";
  h += bloco("Por tipo de boletim", porChave(l, function (b) { return [b.c]; }, TIPOS.map(function (t) { return t[0]; })).map(function (x) { return linha(nomeTipo[x[0]] || x[0], x[1]); }));
  h += bloco("Por odd total", porChave(l, function (b) { return [faixa(b.total)]; }, ODDS.map(function (o) { return o[0]; })).map(function (x) { return linha(nomeOdd[x[0]], x[1]); }));
  h += bloco("Por número de pernas", porChave(l, function (b) { return [String(b.n)]; }, ["1", "2", "3", "4"]).map(function (x) { return linha(x[0] === "1" ? "1 perna" : x[0] === "4" ? "4 ou mais pernas" : x[0] + " pernas", x[1]); }));
  h += bloco("Por competição", porChave(l, function (b) { return Object.keys(b.cs); }).map(function (x) { return linha(x[0], x[1]); }), varias);
  h += bloco("Por mercado", porChave(l, function (b) { return Object.keys(b.ms); }).map(function (x) { return linha(x[0], x[1]); }), varias);
  h += bloco("Por dia", dias.slice().reverse().map(function (d) { return linha(d.nome, d.c, "banca " + eur(d.banca, true)); }));
  var fora = [];
  if (c.emJogo) fora.push(c.emJogo + " " + (c.emJogo === 1 ? "boletim ainda por decidir" : "boletins ainda por decidir"));
  if (c.adiados) fora.push(c.adiados + " " + (c.adiados === 1 ? "adiado, com a aposta devolvida" : "adiados, com a aposta devolvida"));
  h += '<p class="note">Simulação: ' + eur(APOSTA) + ' em cada boletim, com a odd total publicada. Um boletim ganho devolve ' + eur(APOSTA) + ' × a odd; um perdido perde ' + eur(APOSTA) + '. ' +
    (fora.length ? "Ficam de fora " + fora.join(" e ") + ". " : "") + (c.dec < 20 ? "Com " + c.dec + " boletins a amostra é pequena: uma ou duas apostas mudam o resultado. " : "") +
    'É uma conta sobre o que já aconteceu, não uma sugestão de quanto apostar.</p>';
  r.innerHTML = h; ligarGrafico(r);
}

function chips(rotulo, grupo, ops) {
  return '<div class="bg" role="group" aria-label="' + rotulo + '"><span class="bn">' + rotulo + '</span><div class="bc">' + ops.map(function (o) {
    var on = grupo === "periodo" ? F.periodo === o[0] : !!F[grupo][o[0]];
    return '<button type="button" class="ch" data-g="' + grupo + '" data-v="' + o[0] + '" aria-pressed="' + on + '">' + o[1] + '</button>';
  }).join("") + '</div></div>';
}
function lista(rotulo, grupo, todas, valores) {
  return '<div class="bg"><label class="bn" for="bf-' + grupo + '">' + rotulo + '</label><select id="bf-' + grupo + '" data-g="' + grupo + '"><option value="">' + todas + '</option>' +
    valores.map(function (v) { return '<option value="' + esc(v) + '"' + (F[grupo] === v ? " selected" : "") + '>' + esc(v) + '</option>'; }).join("") + '</select></div>';
}
function valores(campo) {
  var n = {}; dados.forEach(function (b) { Object.keys(b[campo]).forEach(function (k) { n[k] = (n[k] || 0) + 1; }); });
  return Object.keys(n).sort(function (a, b) { return (a === SEM_COMP) - (b === SEM_COMP) || n[b] - n[a] || a.localeCompare(b); });
}
function montar(el, hist) {
  if (!document.getElementById("banca-css")) { var st = document.createElement("style"); st.id = "banca-css"; st.textContent = CSS; document.head.appendChild(st); }
  dados = preparar(hist);
  var cs = valores("cs"), ms = valores("ms");
  if (F.comp && cs.indexOf(F.comp) < 0) F.comp = "";
  if (F.mercado && ms.indexOf(F.mercado) < 0) F.mercado = "";
  el.innerHTML = '<div class="bf">' + chips("Período", "periodo", PERIODOS) + chips("Boletim", "tipos", TIPOS) + chips("Odd total", "odds", ODDS) + chips("Pernas", "pernas", PERNAS) +
    lista("Competição", "comp", "Todas", cs) + lista("Mercado", "mercado", "Todos", ms) +
    '<div class="bx"><span class="bq" aria-live="polite"></span><button type="button" class="bl" hidden>Limpar filtros</button></div></div><div class="br"></div>';
  el.onclick = function (ev) {
    var b = ev.target.closest(".ch"), g, v;
    if (ev.target.closest(".bl")) { F = filtrosVazios(); montar(el, hist); return; }
    if (!b) return;
    g = b.dataset.g; v = b.dataset.v;
    if (g === "periodo") { F.periodo = v; el.querySelectorAll('.ch[data-g="periodo"]').forEach(function (x) { x.setAttribute("aria-pressed", x.dataset.v === v); }); }
    else { if (F[g][v]) delete F[g][v]; else F[g][v] = 1; b.setAttribute("aria-pressed", !!F[g][v]); }
    resultado(el);
  };
  el.onchange = function (ev) { var s = ev.target.closest("select[data-g]"); if (s) { F[s.dataset.g] = s.value; resultado(el); } };
  resultado(el);
}
window.Banca = {montar: montar};
})();
