#!/usr/bin/env python3
"""Страница слепой сверки для человека: исходник и варианты правки под буквами А, Б, В.

Читатель отмечает самый живой вариант и варианты, где искажён факт, и копирует строку ответов
в чат. Какая буква какой вариант, знает только файл соответствия (--key), на странице этого нет.

    python3 make_blind_page.py arms/ pairs.jsonl --ids 15,24 --variants human,slovo2,plain \\
        --page page.html --key key.json
"""
import argparse
import html
import json
import random

LETTERS = "АБВГД"
HEAD = """<title>Слепая сверка правки</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=PT+Serif:wght@400;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Корректура: исходник сверху серым, варианты колонками, отметки — синий карандаш, факт — красный */
:root{--paper:#f7f8fa;--sheet:#fff;--ink:#1d2330;--muted:#5d6577;--rule:#dde1e8;--pencil:#2b5bd7;--red:#c8322a;
--serif:"PT Serif",Georgia,serif;--sans:"IBM Plex Sans",system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#14171d;--sheet:#1c2028;--ink:#e6e9ef;--muted:#9aa3b5;--rule:#2f3542;--pencil:#7da2ff;--red:#ff7a70;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#14171d;--sheet:#1c2028;--ink:#e6e9ef;--muted:#9aa3b5;--rule:#2f3542;--pencil:#7da2ff;--red:#ff7a70;color-scheme:dark}
body{background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans);padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:24px 96px}
main{max-width:1180px;margin:0 auto;display:grid;gap:40px}
h1{font:700 26px/1.2 var(--serif);margin:0;text-wrap:balance}
.intro{display:grid;gap:8px;max-width:68ch;color:var(--muted)}
.intro b{color:var(--ink)}
section{display:grid;gap:14px;border-top:1px solid var(--rule);padding-top:20px}
.n{font:600 12px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.src{font:15px/1.6 var(--serif);color:var(--muted);max-width:75ch;margin:0}
.src::before{content:"Исходник. ";font:600 12px var(--sans);letter-spacing:.06em;text-transform:uppercase}
.vars{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.v{background:var(--sheet);border:1px solid var(--rule);border-radius:6px;padding:14px 16px;display:grid;gap:12px;align-content:start;min-width:0}
.v.best{border-color:var(--pencil);box-shadow:0 0 0 1px var(--pencil)}
.v.bad{border-color:var(--red)}
.v h3{margin:0;font:700 18px var(--serif)}
.v p{margin:0;font:16px/1.6 var(--serif)}
.marks{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:14px}
.marks label{display:flex;gap:6px;align-items:center;cursor:pointer}
.marks input{accent-color:var(--pencil);width:16px;height:16px}
.marks .f input{accent-color:var(--red)}
.attr{font-size:12px;color:var(--muted)}
.attr a{color:inherit}
footer{position:fixed;inset:auto 0 0;background:var(--sheet);border-top:1px solid var(--rule);padding:10px max(16px,env(safe-area-inset-right,0px)) calc(10px + env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px));display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
#left{color:var(--muted);font-variant-numeric:tabular-nums}
button{font:600 14px var(--sans);background:var(--pencil);color:var(--sheet);border:0;border-radius:6px;padding:9px 16px;cursor:pointer}
button:focus-visible,input:focus-visible{outline:2px solid var(--pencil);outline-offset:2px}
#out{flex-basis:100%;font:12px/1.4 ui-monospace,monospace;color:var(--muted);word-break:break-all}
</style>
"""
SCRIPT = """<script>
const N=%d,KEY="slovo-blind-v1";let st={};
try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
function line(){const p=[];for(const s of document.querySelectorAll("section[data-id]")){const id=s.dataset.id,x=st[id]||{};
p.push(id+":"+(x.best||"-")+(x.bad&&x.bad.length?"!"+x.bad.join(""):""))}return "сверка "+p.join(" ")}
function paint(){let done=0;for(const s of document.querySelectorAll("section[data-id]")){const x=st[s.dataset.id]||{};if(x.best)done++;
for(const v of s.querySelectorAll(".v")){const l=v.dataset.l;v.classList.toggle("best",x.best===l);v.classList.toggle("bad",(x.bad||[]).includes(l));
v.querySelector("input[type=radio]").checked=x.best===l;v.querySelector("input[type=checkbox]").checked=(x.bad||[]).includes(l)}}
document.getElementById("left").textContent="Отмечено "+done+" из "+N;document.getElementById("out").textContent=line()}
document.addEventListener("change",e=>{const v=e.target.closest(".v");if(!v)return;const id=v.closest("section").dataset.id,l=v.dataset.l,x=st[id]||(st[id]={});
if(e.target.type==="radio")x.best=l;else{const b=new Set(x.bad||[]);e.target.checked?b.add(l):b.delete(l);x.bad=[...b].sort()}save();paint()});
document.getElementById("copy").addEventListener("click",()=>{const t=line(),b=document.getElementById("copy");
navigator.clipboard.writeText(t).then(()=>{b.textContent="Скопировано"},()=>{const r=document.createRange();r.selectNodeContents(document.getElementById("out"));
const s=getSelection();s.removeAllRanges();s.addRange(r);b.textContent="Выделено, скопируйте вручную"})});
paint();
</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arms")
    ap.add_argument("pairs")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--variants", default="human,slovo2,plain")
    ap.add_argument("--page", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    meta = {str(json.loads(l)["id"]): json.loads(l) for l in open(a.pairs)}
    ids, variants = a.ids.split(","), a.variants.split(",")
    key, secs = {}, []
    for n, i in enumerate(ids, 1):
        order = variants[:]
        random.Random(f"{a.seed}-{i}").shuffle(order)
        key[i] = dict(zip(LETTERS, order))
        cards = "".join(
            f'<div class="v" data-l="{l}"><h3>{l}</h3><p>{html.escape(open(f"{a.arms}/{i}.{v}.md").read().strip())}</p>'
            f'<div class="marks"><label><input type="radio" name="b{i}" id="b{i}{l}">живее всех</label>'
            f'<label class="f"><input type="checkbox" id="f{i}{l}">искажён факт</label></div></div>'
            for l, v in zip(LETTERS, order))
        m = meta[i]
        attr = (f'<p class="attr">Википедия, «{html.escape(m["title"])}», '
                f'<a href="https://ru.wikipedia.org/w/index.php?diff={m["revid"]}&amp;oldid={m["parentid"]}">правка</a>, CC BY-SA 4.0</p>'
                if m.get("revid") else "")
        secs.append(f'<section data-id="{i}"><div class="n">Текст {n} из {len(ids)}</div>'
                    f'<p class="src">{html.escape(open(f"{a.arms}/{i}.before.md").read().strip())}</p>'
                    f'<div class="vars">{cards}</div>{attr}</section>')
    body = ('<main><header class="intro"><h1>Слепая сверка правки</h1>'
            '<p>У каждого текста сверху исходник, ниже три правки под буквами. Кто правил, не сказано: '
            'это может быть живой редактор, slovo или модель без скилла.</p>'
            '<p><b>Отметь самую живую правку</b> и поставь «искажён факт» у тех, где пропало, сместилось или '
            'добавилось что-то по смыслу. Около минуты на текст.</p>'
            '<p>Когда закончишь, нажми «Скопировать ответы» внизу и пришли строку в чат.</p></header>'
            + "".join(secs) + '</main><footer><span id="left"></span><button id="copy" type="button">Скопировать ответы</button>'
            '<div id="out"></div></footer>')
    open(a.page, "w").write(HEAD + body + SCRIPT % len(ids))
    json.dump(key, open(a.key, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
