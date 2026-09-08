"""A browser demo of the questioning agent. **Throwaway, and not the product.**

    ./.venv/bin/python scripts/demo_questionnaire.py
    # then open http://localhost:8900

The real client is the Flutter app on a phone. This exists because the engine is
a Python library that nothing calls yet, so the only way to sit and click
through the questionnaire is a page that drives it directly.

**What it deliberately is not:**

- It is not the patient app. No consent flow, no sign-in, no hospital, no
  documents, no offline queue — none of the things §5 and §11 require before a
  real intake is collected.
- It holds sessions in a dict in memory. They die with the process, which is the
  correct amount of persistence for something that must never hold a real
  answer.
- It binds to localhost and has no authentication, because it must not be
  reachable by anything but the person who started it.

What it *is* is the engine, unmodified, with a thin page in front — including
the decision log, which is the interesting part: every question comes with its
score and the reasons it won, so you can watch it decide rather than take the
ranking on trust.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.questioning_agent.core.agent import QuestioningAgent, Turn  # noqa: E402
from app.questioning_agent.core.patient_state import PatientState  # noqa: E402
from app.questioning_agent.localization.languages import LANGUAGES  # noqa: E402
from app.questioning_agent.output.case_summary import render  # noqa: E402

CONTENT = Path(__file__).resolve().parents[2] / "clinical" / "questioning"

agent = QuestioningAgent.load(CONTENT)
app = FastAPI(title="MediKiosk questioning agent — demo", docs_url=None, redoc_url=None)


@dataclass
class Session:
    state: PatientState = field(default_factory=PatientState)
    language: str = "en"
    turn: Turn | None = None


SESSIONS: dict[str, Session] = {}


class StartRequest(BaseModel):
    language: str = "en"


class AnswerRequest(BaseModel):
    session: str
    answer: str = ""
    skip: bool = False


def _turn_payload(session: Session) -> dict[str, Any]:
    """The next question, or the finished case."""
    turn = agent.next(session.state, language=session.language)
    session.turn = turn

    if turn is None:
        summary = agent.summarise(session.state)
        return {
            "done": True,
            "stopped_early": summary.stopped_early,
            "red_flags": [f.label for f in summary.red_flags],
            "case": render(summary, agent.slots),
            "asked": len(session.state.asked_questions),
        }

    return {
        "done": False,
        "id": turn.id,
        "text": turn.text,
        "answer_type": turn.answer_type.value,
        "options": [{"id": o, "label": label} for o, label in turn.options],
        "unit": turn.question.unit,
        "units": list(turn.question.units),
        "minimum": turn.question.minimum,
        "maximum": turn.question.maximum,
        "clarifying": turn.clarifying,
        "asked": len(session.state.asked_questions),
        "decision": {
            "score": (
                "fixed"
                if turn.decision.score == float("inf")
                else round(turn.decision.score, 1)
            ),
            "reasons": list(turn.decision.reasons),
            "targets": list(turn.decision.targets),
        },
    }


@app.post("/api/start")
def start(request: StartRequest) -> dict[str, Any]:
    key = uuid.uuid4().hex
    language = request.language if request.language in LANGUAGES else "en"
    SESSIONS[key] = Session(language=language)
    return {"session": key, **_turn_payload(SESSIONS[key])}


@app.post("/api/answer")
def answer(request: AnswerRequest) -> dict[str, Any]:
    session = SESSIONS.get(request.session)
    if session is None or session.turn is None:
        return {"error": "no such session; reload the page"}

    if request.skip:
        agent.skip(session.state, session.turn)
        extracted: list[dict[str, Any]] = []
    else:
        record = agent.answer(
            session.state, session.turn, request.answer, language=session.language
        )
        extracted = [
            {
                "slot": fact.slot,
                "value": fact.value,
                "certainty": fact.certainty.value,
                "evidence": fact.evidence,
            }
            for fact in record.facts
        ]

    return {"extracted": extracted, **_turn_payload(session)}


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return PAGE


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MediKiosk — questioning agent demo</title>
<style>
  :root { --line:#d8d5cf; --ink:#1c1b19; --muted:#6b6862; --accent:#2d5f4f; --bg:#faf9f7; }
  * { box-sizing:border-box }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.5 system-ui,-apple-system,"Noto Sans",sans-serif; }
  .wrap { max-width:920px; margin:0 auto; padding:24px 16px 64px; }
  header { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;
           border-bottom:1px solid var(--line); padding-bottom:12px; margin-bottom:20px }
  h1 { font-size:18px; margin:0; font-weight:650 }
  .demo { font-size:12px; background:#8a3a2a; color:#fff; padding:2px 8px; border-radius:99px }
  .grid { display:grid; grid-template-columns:1fr 300px; gap:24px }
  @media (max-width:760px){ .grid{ grid-template-columns:1fr } }
  .card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:20px }
  .q { font-size:22px; line-height:1.35; margin:0 0 18px }
  .clarify { font-size:13px; color:#8a3a2a; margin:0 0 10px }
  button { font:inherit; cursor:pointer }
  .opt { display:block; width:100%; text-align:left; background:#fff; border:1px solid var(--line);
         border-radius:8px; padding:12px 14px; margin-bottom:8px }
  .opt:hover { border-color:var(--accent) }
  .opt.on { background:#e8f0ec; border-color:var(--accent) }
  input[type=text],input[type=number],textarea {
      font:inherit; width:100%; padding:11px 12px; border:1px solid var(--line);
      border-radius:8px; background:#fff }
  textarea { min-height:90px; resize:vertical }
  .row { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap }
  .go { background:var(--accent); color:#fff; border:0; border-radius:8px; padding:11px 20px }
  .ghost { background:#fff; border:1px solid var(--line); border-radius:8px; padding:11px 16px }
  aside h2 { font-size:12px; text-transform:uppercase; letter-spacing:.08em;
             color:var(--muted); margin:0 0 8px }
  aside .card { padding:14px; margin-bottom:14px }
  .score { font:600 24px/1 ui-monospace,monospace; color:var(--accent) }
  ul { margin:8px 0 0; padding-left:18px; font-size:13px; color:var(--muted) }
  code { font:12px/1.5 ui-monospace,monospace; background:#f0efec; padding:1px 5px; border-radius:4px }
  .fact { font:12px/1.6 ui-monospace,monospace; padding:6px 0; border-bottom:1px solid var(--line) }
  .fact:last-child { border:0 }
  .un { color:#8a3a2a }
  pre { white-space:pre-wrap; font:13px/1.6 ui-monospace,monospace; margin:0 }
  .flag { background:#8a3a2a; color:#fff; padding:12px 14px; border-radius:8px; margin-bottom:16px }
  .count { font-size:13px; color:var(--muted); margin-left:auto }
  select { font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:8px }
  .hint { font-size:13px; color:var(--muted); margin-top:10px }
</style></head><body><div class="wrap">

<header>
  <h1>MediKiosk questioning agent</h1>
  <span class="demo">demo only — not the patient app</span>
  <span class="count" id="count"></span>
</header>

<div id="setup" class="card">
  <p style="margin-top:0">Pick a language and start. Every question can be answered by
  tapping an option <em>or</em> by typing an ordinary sentence — the point of the demo is
  that both work, and that the panel on the right shows why each question was chosen and
  what was read out of your answer.</p>
  <div class="row">
    <select id="lang">
      <option value="en">English</option><option value="hi">हिन्दी</option>
      <option value="bn">বাংলা</option><option value="ta">தமிழ்</option>
      <option value="te">తెలుగు</option><option value="mr">मराठी</option>
      <option value="gu">ગુજરાતી</option><option value="kn">ಕನ್ನಡ</option>
      <option value="pa">ਪੰਜਾਬੀ</option>
    </select>
    <button class="go" onclick="start()">Start</button>
  </div>
</div>

<div class="grid" id="main" hidden>
  <div>
    <div class="card" id="qcard"></div>
  </div>
  <aside>
    <h2>Why this question</h2>
    <div class="card" id="why"></div>
    <h2>Read from your last answer</h2>
    <div class="card" id="facts"><span style="color:#6b6862;font-size:13px">nothing yet</span></div>
  </aside>
</div>

<script>
let S=null, chosen=new Set(), current=null;
const $=id=>document.getElementById(id);

async function post(path, body){
  const r = await fetch(path,{method:'POST',headers:{'content-type':'application/json'},
                             body:JSON.stringify(body)});
  return r.json();
}

async function start(){
  const d = await post('/api/start',{language:$('lang').value});
  S = d.session; $('setup').hidden = true; $('main').hidden = false; show(d);
}

async function send(answer, skip){
  const d = await post('/api/answer',{session:S, answer:answer||'', skip:!!skip});
  facts(d.extracted||[]); show(d);
}

function facts(list){
  if(!list.length){ $('facts').innerHTML='<span style="color:#6b6862;font-size:13px">nothing read</span>'; return }
  $('facts').innerHTML = list.map(f=>{
    const v = f.value===null||f.value===undefined ? '<span class="un">could not read</span>'
            : (typeof f.value==='object' ? JSON.stringify(f.value) : String(f.value));
    return `<div class="fact">${f.slot}<br>= ${v}`
         + (f.certainty!=='certain'?` <span class="un">(${f.certainty})</span>`:'')+`</div>`;
  }).join('');
}

function show(d){
  chosen = new Set(); current = d;
  $('count').textContent = d.asked!=null ? d.asked+' asked' : '';

  if(d.done){
    $('why').innerHTML = '<span style="color:#6b6862;font-size:13px">interview finished</span>';
    let head = '';
    if(d.stopped_early)
      head = `<div class="flag"><b>Stopped early.</b> ${d.red_flags.join('; ')}
              — the questionnaire does not continue past this.</div>`;
    $('qcard').innerHTML = head
      + `<div class="q">Case summary</div><pre>${esc(d.case)}</pre>
         <div class="row"><button class="ghost" onclick="location.reload()">Start again</button></div>`;
    return;
  }

  $('why').innerHTML = `<div class="score">${d.decision.score}</div>
    <ul>${d.decision.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>
    <div style="margin-top:10px;font-size:12px;color:#6b6862">fills</div>
    <div>${d.decision.targets.map(t=>`<code>${esc(t)}</code>`).join(' ')}</div>`;

  let body = '';
  if(d.clarifying) body += `<p class="clarify">I could not read that — asking again.</p>`;
  body += `<div class="q">${esc(d.text)}</div>`;

  const t = d.answer_type;
  if(t==='single_select'||t==='multi_select'||t==='boolean'){
    const opts = t==='boolean' ? [{id:'yes',label:'Yes'},{id:'no',label:'No'}] : d.options;
    body += opts.map(o=>`<button class="opt" data-id="${o.id}" onclick="pick(this,'${t}')">${esc(o.label)}</button>`).join('');
    body += `<div class="hint">…or type it in your own words instead:</div>
             <input type="text" id="free" placeholder="e.g. ${t==='boolean'?'no, not at all':'whatever fits'}"
                    onkeydown="if(event.key==='Enter')submit()">`;
  } else if(t==='numeric'||t==='scale'){
    const u = d.units.length>1 ? ' ('+d.units.join(' or ')+')' : (d.unit?' ('+d.unit+')':'');
    body += `<input type="text" id="free" placeholder="a number${esc(u)}"
                    onkeydown="if(event.key==='Enter')submit()">`;
  } else if(t==='date'){
    body += `<input type="text" id="free" placeholder="YYYY-MM-DD"
                    onkeydown="if(event.key==='Enter')submit()">`;
  } else {
    body += `<textarea id="free" placeholder="in your own words"></textarea>`;
  }

  body += `<div class="row">
      <button class="go" onclick="submit()">Answer</button>
      <button class="ghost" onclick="send('',true)">Skip / don't know</button>
    </div>`;
  $('qcard').innerHTML = body;
}

function pick(el, type){
  if(type==='multi_select'){
    el.classList.toggle('on');
    const id = el.dataset.id;
    chosen.has(id) ? chosen.delete(id) : chosen.add(id);
  } else {
    send(el.dataset.id);
  }
}

function submit(){
  const typed = ($('free')?.value || '').trim();
  if(typed) return send(typed);
  if(chosen.size) return send([...chosen].join(', '));
}

function esc(s){ return String(s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])) }
</script>
</div></body></html>
"""


if __name__ == "__main__":
    print("\n  MediKiosk questioning agent — DEMO ONLY")
    print("  Not the patient app. Sessions live in memory and die with this process.")
    print(f"  {len(agent.bank)} questions, {len(agent.slots)} slots, "
          f"{len(LANGUAGES)} languages, {len(agent.triage)} red-flag rules.\n")
    print("  http://localhost:8900\n")
    uvicorn.run(app, host="127.0.0.1", port=8900, log_level="warning")
