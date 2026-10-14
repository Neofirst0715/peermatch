/* Volta Peer Match demo. All data below is made up.
   Section 1: sample data (generated from the demo data pack and the checked matches)
   Section 2: the app (Import, Review, Directory, Find a helper) */

// ---- Data: frontend/data.json is written by backend/build_data.py.
// Opened from disk (file://) browsers block fetch, so data.js (same content, as a script) is used instead.
// Served by backend/server.py, API is '' and the page can upload a CSV and save the tracker to data/<month>/.
const API=location.protocol.startsWith('http')?'':null;
let UP=null, MONTHS=null, API_KEY_SET=true, CTL=null;  // last upload result, /api/months cache, server API-key state, listeners of the running start()
function start(D,opts){
opts=opts||{};


// ---- 2. App ---------------------------------------------------------
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $=id=>document.getElementById(id);
const reduceMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
const fn=n=>n.split(' ')[0];
const S={}; const items=D.items; const P=id=>D.people.find(x=>x.id===id);
items.forEach(it=>S[it.id]={status:'pending',i:0,log:[],hist:[],reply:''});
/* Persistence. Everything Laura changes lives in S (per match), SW (swap undo), manual matches and swap links.
   snapshot() captures it; restore() puts it back. Saved to this browser after every action (localStorage,
   keyed by month) and to a file through "Save tracker". Reload order: file she loaded > browser > fresh data.json.
   With the local server, every save also goes to data/<month>/tracker-page.json, and that file wins over the browser. */
const SW={};
const STORE_KEY='vpm:'+(D.month||'month');
function snapshot(){
  return {month:D.month,saved:new Date().toISOString(),
    state:Object.fromEntries(items.map(it=>[it.id,S[it.id]])),
    swaps:Object.fromEntries(items.map(it=>[it.id,it.swap||''])),
    manual:items.filter(it=>it.manual).map(it=>({...it})),
    sw:SW};
}
function restore(snap){
  if(!snap||snap.month!==D.month)return false;
  (snap.manual||[]).forEach(m=>{if(!byId(m.id)){items.unshift(m);const p=P(m.id);if(p)p.matched=true;}
    else{const ex=byId(m.id);m.cands.forEach(c=>{if(!ex.cands.some(x=>x.ref===c.ref))ex.cands.unshift(c);});}});
  items.forEach(it=>{if(snap.state&&snap.state[it.id])S[it.id]=snap.state[it.id];if(snap.swaps&&it.id in snap.swaps)it.swap=snap.swaps[it.id];});
  Object.keys(SW).forEach(k=>delete SW[k]);Object.assign(SW,snap.sw||{});
  return true;
}
let lastSaved='', confirmReset=false, fmReady=false;
function persist(){try{const snap=snapshot();localStorage.setItem(STORE_KEY,JSON.stringify(snap));lastSaved=snap.saved;}catch(_){}pushServer();}
const trackerUrl=()=>API+'/api/tracker?month='+encodeURIComponent(D.month||'');
let putTimer=null;
function putTracker(body){return fetch(trackerUrl(),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive:true}).catch(()=>{});}
function pushServer(){if(API===null||putTimer)return;putTimer=setTimeout(()=>{putTimer=null;putTracker(snapshot());},500);}  // at most one PUT per 500ms, always the latest state
if(API!==null)addEventListener('pagehide',()=>{if(putTimer){clearTimeout(putTimer);putTimer=null;putTracker(snapshot());}},{signal:opts.signal});
function loadLocal(){try{const raw=localStorage.getItem(STORE_KEY);if(raw){const snap=JSON.parse(raw);if(restore(snap)){lastSaved=snap.saved;return true;}}}catch(_){}return false;}
const fmtTime=iso=>iso?new Date(iso).toLocaleString(undefined,{hour:'2-digit',minute:'2-digit',month:'short',day:'numeric'}):'';
const dataLine=()=>D.processed_at?`Data from ${esc(D.month||'')}, processed ${fmtTime(D.processed_at)}`:'';
const byId=id=>items.find(x=>x.id===id);
const STEPS=['Decide','Invite','Reply','Introduce'];
const stepIdx={pending:0,approved:1,sent:2,yes:3,introduced:4};
const LAURA=D.laura_email||'laura@example.com';
const gmail=(to,su,body)=>'https://mail.google.com/mail/?authuser='+encodeURIComponent(LAURA)+'&view=cm&fs=1&to='+encodeURIComponent(to).replace(/%2C/g,',').replace(/%40/g,'@')+'&su='+encodeURIComponent(su)+'&body='+encodeURIComponent(body);
const meetLine=c=>c.meet?`You are both at the next ${c.meet}, so that may be the easiest place to talk. `:'';
function introFor(it){const c=it.cands[S[it.id].i];
  return {to:it.email+','+c.to,subject:`Introduction: ${it.name} and ${c.name}`,
  body:`Hi ${fn(it.name)} and ${fn(c.name)},\n\n${fn(c.name)} has agreed to a 20-minute chat. Here is why I thought of you both:\n\n- ${fn(it.name)} is working on: ${it.stuck}\n- ${fn(c.name)} has: ${c.lived}\n\nI'll leave you two to find a time. ${meetLine(c)}Thank you both.\n\nLaura`};}
function swapIntro(a,b){const ca=a.cands[S[a.id].i],cb=b.cands[S[b.id].i];
  return {to:a.email+','+b.email,subject:`Introduction: ${a.name} and ${b.name}`,
  body:`Hi ${fn(a.name)} and ${fn(b.name)},\n\nYou have each agreed to a 20-minute chat, and you can each help the other:\n\n- ${fn(a.name)} is working on: ${a.stuck}. ${fn(b.name)} has: ${ca.lived}\n- ${fn(b.name)} is working on: ${b.stuck}. ${fn(a.name)} has: ${cb.lived}\n\nI'll leave you two to find a time. ${meetLine(ca)}Thank you both.\n\nLaura`};}
const stepper=st=>{if(!(st.status in stepIdx))return '';const n=stepIdx[st.status];
  return `<div class="steps">${STEPS.map((s,k)=>`<span class="${k<n?'done':k===n?'now':''}">${s}</span>`).join('')}</div>`;};
const emailBox=(id,to,su,b)=>`<div class="email" id="em-${id}"><b>To:</b> ${esc(to)}\n<b>Subject:</b> ${esc(su)}\n\n${esc(b)}</div>`;
const copyBtn=id=>`<button class="btn quiet" data-act="copy" data-id="${id}">Copy text</button>`;

function body(it,o){o=o||{};
  const st=S[it.id], c=it.cands[st.i];
  const pill={pending:'<span class="pill warn">Needs your decision</span>',approved:'<span class="pill">Invitation ready</span>',sent:'<span class="pill">Waiting for reply</span>',
    yes:'<span class="pill good">Helper said yes</span>',introduced:'<span class="pill good">Introduced</span>',empty:'<span class="pill bad">No helper left</span>',skipped:'<span class="pill tag">Skipped</span>'}[st.status];
  const sentInvite=['sent','yes','introduced'].includes(st.status)?`<details class="sentbox"><summary>Invitation sent to ${esc(fn(c.name))}</summary>${emailBox(it.id+'i',c.to,c.subject,c.body)}</details>`:'';
  const reply=`<div class="inbox"><b>From:</b> ${esc(c.to)}<br><b>Subject:</b> Re: ${esc(c.subject)}<br>YES, happy to. (Ref: ${esc(c.ref)})</div>`;
  let act='';
  if(st.status==='pending') act=`<div class="row actions"><button class="btn" data-act="approve" data-id="${it.id}">Approve</button><button class="btn quiet" data-act="skip" data-id="${it.id}">Skip this month</button></div>`;
  else if(st.status==='approved') act=`<span class="label">Invitation to ${esc(fn(c.name))}</span>${emailBox(it.id,c.to,c.subject,c.body)}
    <div class="row"><a class="btn" target="_blank" rel="noopener" href="${esc(c.link)}">Open in Gmail to send</a>${copyBtn(it.id)}<button class="btn ghost" data-act="sent" data-id="${it.id}">I sent it</button></div>
`;
  else if(st.status==='sent') act=sentInvite+`<div class="replybar"><span>Waiting for ${esc(fn(c.name))}. Reply arrives with Ref ${esc(c.ref)}.</span>
     <div class="row"><span class="label">Record the reply</span><button class="btn small" data-act="simyes" data-id="${it.id}">Yes</button><button class="btn ghost small" data-act="simno" data-id="${it.id}">No</button><button class="btn quiet small" data-act="noreply" data-id="${it.id}">No reply after a week</button></div></div>`;
  else if(st.status==='yes'){
    {const x=introFor(it);
      act=sentInvite+reply+`<span class="label">Introduction, names go out now</span>${emailBox(it.id,x.to,x.subject,x.body)}
      <div class="row"><a class="btn" target="_blank" rel="noopener" href="${esc(gmail(x.to,x.subject,x.body))}">Open in Gmail to send</a>${copyBtn(it.id)}<button class="btn ghost" data-act="intro" data-id="${it.id}">I sent it</button></div>`;}
  }else if(st.status==='introduced'){const x=introFor(it);
    act=sentInvite+`<details class="sentbox"><summary>Introduction sent to ${esc(fn(it.name))} and ${esc(fn(c.name))}</summary>${emailBox(it.id,x.to,x.subject,x.body)}</details>`;
  }
  else if(st.status==='empty') act=`<p class="muted actions">Everyone who fits has been asked. It goes back on the list next month.</p>`;
  else act=`<p class="muted actions">Skipped. It goes back on the list next month.</p>`;
  const log=st.log.length?`<p class="muted">${st.log.map(esc).join(' · ')}</p>`:'';
  const undo=st.hist.length?`<button class="btn quiet small" data-act="undo" data-id="${it.id}">Undo</button>`:'';
  const badge=it.swap?'<span class="pill">Swap</span>':'<span class="pill tag">One-way</span>';
  const showSteps=!['pending','skipped','empty'].includes(st.status);
  const details=st.details?`<div class="strip"><span><b>Working on:</b> ${esc(it.doing)}</span><span><b>Topic:</b> ${esc(it.topic)}</span><span><b>Helper:</b> ${esc(c.role)} at ${esc(c.company)}</span></div>`:'';
  return `<div class="head"><span class="who-line"><b title="${esc(it.name)}">${esc(it.name)}</b><span class="muted" title="${esc(it.company)}">${esc(it.company)}</span><span class="ref">${it.id}</span>${badge}${it.manual?'<span class="pill tag">Added by Laura</span>':''}</span><span class="state-line">${pill}${undo}</span></div>
    <div class="vs"><div class="box stuck"><span class="label">Stuck on</span><b class="big">${esc(it.stuck)}</b></div><div class="arrow" aria-hidden="true">→</div>
      <div class="box lived"><span class="label"><button class="lnk" data-act="detail" data-id="M${c.hid.slice(1)}">${esc(c.name)}</button> has lived through${it.cands.length>1?` · ${st.i+1} of ${it.cands.length}`:''}</span><b class="big">${esc(c.lived)}</b></div></div>
    <p class="why">${esc(c.reason)}</p>
    ${c.meet&&st.status!=='introduced'?`<p><span class="pill good">Both going to the next ${esc(c.meet)}</span></p>`:''}
    ${showSteps?stepper(st):''}${act}${log}
    <p><button class="lnk" data-act="details" data-id="${it.id}">${st.details?'Hide details':'Details'}</button></p>${details}`;}

function renderReview(){
  const all=Object.values(S), n=f=>all.filter(s=>f(s.status)).length;
  const rolling=D.total-items.length;
  const cell=(v,l,jump)=>`<div class="count ${v?'on':''}" data-jump="${jump}" role="button" tabindex="0"><b>${v}</b><span class="muted">${l}</span></div>`;
  const dl=dataLine();
  $('counts').innerHTML=`${dl?`<p class="muted">${dl}</p>`:''}<div class="counts">
    ${cell(D.total,'signed up','dir')}${cell(n(s=>s==='pending'),'to decide','todo')}${cell(n(s=>s==='approved'||s==='sent'),'invited','todo')}${cell(n(s=>s==='yes'),'said yes','todo')}${cell(n(s=>s==='introduced'),'introduced','done')}${cell(rolling+n(s=>s==='skipped'||s==='empty'),'next month','out')}</div>`;
  const swaps=items.filter(i=>i.swap&&i.id<i.swap), inSwap=new Set(swaps.flatMap(a=>[a.id,a.swap]));
  const ones=items.filter(i=>!inSwap.has(i.id));
  const done=k=>k==='introduced', out=k=>k==='skipped'||k==='empty';
  const swapBy=f=>swaps.filter(a=>f(swapPhase(a,byId(a.swap)))), oneBy=f=>ones.filter(i=>f(S[i.id].status));
  const grid=(sw,on)=>{const g=x=>x.length?`<div class="ones">${x.join('')}</div>`:'';
    const swC=sw.map(a=>swapCard(a,byId(a.swap))), onC=on.map(it=>`<div class="card ${S[it.id].status}" data-card="${it.id}">${body(it)}</div>`);
    return (swC.length?`<p class="label">Swap</p>`+g(swC):'')+(onC.length?`<p class="label">One-way</p>`+g(onC):'');};
  const sec=(id,title,pill,sw,on,empty)=>`<div class="sec" id="${id}"><div class="row"><h2>${title}</h2>${pill}</div>${sw.length||on.length?grid(sw,on):`<p class="muted">${empty}</p>`}</div>`;
  const actS=swapBy(k=>!done(k)&&!out(k)), actO=oneBy(k=>!done(k)&&!out(k));
  const donS=swapBy(done), donO=oneBy(done), outS=swapBy(out), outO=oneBy(out);
  $('exportBar').innerHTML=API!==null
    ?`<button class="btn quiet small" data-act="reset">Start month over</button><span class="muted">${lastSaved?`Saved to data/${esc(D.month)}/tracker-page.json at ${new Date(lastSaved).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:false})}`:'Nothing saved yet.'}</span>`
    :`<button class="btn quiet small" data-act="export">Save tracker to file</button><label class="btn quiet small" for="trackerFile">Load tracker file</label><input type="file" id="trackerFile" accept=".json,application/json" hidden><button class="btn quiet small" data-act="reset">Start month over</button><span class="muted">${lastSaved?'Saved in this browser '+fmtTime(lastSaved)+'.':'Nothing saved yet.'} Save the file into the month folder so the scripts see the same state.</span>`;
  $('oneSec').innerHTML=
    sec('sec-todo','To do',`<span class="pill warn">${actS.length+actO.length}</span>`,actS,actO,'Nothing waiting on you.')+
    sec('sec-done','Introduced',`<span class="pill good">${donS.length+donO.length}</span>`,donS,donO,'No introductions yet this month.')+
    sec('sec-out','Not this month',`<span class="pill tag">${outS.length+outO.length}</span>`,outS,outO,'Nothing skipped.');
  const left=D.people.filter(p=>!byId(p.id));
  $('leftSec').innerHTML=`<details><summary>${left.length} founders with no helper found</summary>
    <p class="muted" style="margin-block:8px">Left out because no helper is a clear fit. Pick one yourself in the Directory.</p>
    <div class="scroll"><table><thead><tr><th>Founder</th><th>Stuck on</th><th>Why no match</th></tr></thead><tbody>
    ${left.map(p=>{const l=D.left.find(x=>x.id===p.id);return `<tr><td>${esc(p.name)}, ${esc(p.company)}</td><td>${esc(p.stuck)}</td><td>${esc(l?l.reason:'')}</td></tr>`}).join('')}</tbody></table></div></details>`;
}


/* one card for a pair who can each help the other */
const sideBtns=(x,c)=>`<div class="row"><a class="btn" target="_blank" rel="noopener" href="${esc(c.link)}">Open in Gmail to send</a>${copyBtn(x.id)}<button class="btn ghost" data-act="swapsent" data-id="${x.id}">I sent it</button></div>`;
function swapPhase(a,b){const sa=S[a.id],sb=S[b.id],st=k=>sa.status===k&&sb.status===k;return st('pending')?'pending':st('skipped')?'skipped':st('introduced')?'introduced':'active';}
function swapCard(a,b){
  const sa=S[a.id], sb=S[b.id], ca=a.cands[sa.i], cb=b.cands[sb.i];
  const st=k=>sa.status===k&&sb.status===k, any=k=>sa.status===k||sb.status===k;
  const sent=x=>['sent','yes','introduced'].includes(S[x.id].status);
  const phase=st('pending')?'pending':st('skipped')?'skipped':st('introduced')?'introduced':st('yes')?'bothyes':(sent(a)&&sent(b))?'waiting':'invite';
  const pill={pending:'<span class="pill warn">Needs your decision</span>',invite:'<span class="pill">Invitations ready</span>',waiting:'<span class="pill">Waiting for replies</span>',
    bothyes:'<span class="pill good">Both said yes</span>',introduced:'<span class="pill good">Introduced</span>',skipped:'<span class="pill tag">Skipped</span>'}[phase];
  const stepN={pending:0,invite:1,waiting:2,bothyes:3,introduced:4}[phase];
  const steps=phase==='pending'||phase==='skipped'?'':`<div class="steps">${STEPS.map((s,k)=>`<span class="${k<stepN?'done':k===stepN?'now':''}">${s}</span>`).join('')}</div>`;
  const row=(x,c)=>`<div class="vs"><div class="box stuck"><span class="label">${esc(fn(x.name))} is stuck on</span><b class="big">${esc(x.stuck)}</b></div><div class="arrow" aria-hidden="true">→</div>
    <div class="box lived"><span class="label"><button class="lnk" data-act="detail" data-id="M${c.hid.slice(1)}">${esc(fn(c.name))}</button> has lived through</span><b class="big">${esc(c.lived)}</b></div></div><p class="why">${esc(c.reason)}</p>`;
  const invite=(x,c)=>sent(x)?`<details class="sentbox"><summary>Invitation sent to ${esc(fn(c.name))}</summary>${emailBox(x.id,c.to,c.subject,c.body)}</details>`
    :`<span class="label">Invitation to ${esc(fn(c.name))}</span>${emailBox(x.id,c.to,c.subject,c.body)}${sideBtns(x,c)}`;
  const replyRow=(x,c)=>{const y=S[x.id].status;
    return `<div class="row"><b style="min-width:90px">${esc(fn(c.name))}</b>${y==='yes'?`<span class="pill good">Said yes</span>`:
      `<button class="btn small" data-act="swapyes" data-id="${x.id}">Yes</button><button class="btn ghost small" data-act="swapno" data-id="${x.id}">No</button><button class="btn quiet small" data-act="swapnoreply" data-id="${x.id}">No reply</button>`}</div>`;};
  let act='';
  if(phase==='pending') act=`<div class="row"><button class="btn" data-act="swapapprove" data-id="${a.id}">Approve</button><button class="btn quiet" data-act="swapskip" data-id="${a.id}">Skip this month</button></div>`;
  else if(phase==='skipped') act=`<p class="muted">Skipped. Both go back on the list next month.</p>`;
  else if(phase==='invite') act=invite(a,ca)+invite(b,cb);
  else if(phase==='waiting') act=invite(a,ca)+invite(b,cb)+`<div class="replybar"><span class="label">Record the replies</span>`+replyRow(a,ca)+replyRow(b,cb)+`<span class="muted">If either says no, the pair splits into two one-way matches.</span></div>`;
  else{const x=swapIntro(a,b);
    act=invite(a,ca)+invite(b,cb);
    if(phase==='bothyes') act+=`<span class="label">Both said yes. Introduction, names go out now</span>${emailBox('sw'+a.id,x.to,x.subject,x.body)}
      <div class="row"><a class="btn" target="_blank" rel="noopener" href="${esc(gmail(x.to,x.subject,x.body))}">Open in Gmail to send</a>${copyBtn('sw'+a.id)}<button class="btn ghost" data-act="swapintro" data-id="${a.id}">I sent it</button></div>`;
    else act+=`<details class="sentbox"><summary>Introduction sent to ${esc(fn(a.name))} and ${esc(fn(b.name))}</summary>${emailBox('sw'+a.id,x.to,x.subject,x.body)}</details>`;}
  const log=[...sa.log,...sb.log]; const logP=log.length?`<p class="muted">${log.map(esc).join(' · ')}</p>`:'';
  const undo=(SW[a.id]||[]).length?`<button class="btn quiet small" data-act="swapundo" data-id="${a.id}">Undo</button>`:'';
  return `<div class="card ${phase}" data-card="${a.id}"><div class="head"><span class="who-line"><b title="${esc(a.name)} ↔ ${esc(b.name)}">${esc(fn(a.name))} ↔ ${esc(fn(b.name))}</b><span class="ref">${a.id} · ${b.id}</span><span class="pill">Swap</span></span><span class="state-line">${pill}${undo}</span></div>
    ${steps}${row(a,ca)}${row(b,cb)}${ca.meet&&phase!=='introduced'?`<p><span class="pill good">Both at the next ${esc(ca.meet)}</span></p>`:''}${act}${logP}</div>`;
}
function swapAct(act,id){
  const x=byId(id), aId=x.swap&&x.id<x.swap?x.id:x.swap, a=byId(aId), b=byId(a.swap);
  (SW[aId]=SW[aId]||[]).push(JSON.stringify({a:snap(S[a.id]),b:snap(S[b.id]),sa:a.swap,sb:b.swap}));
  const both=k=>{S[a.id].status=k;S[b.id].status=k;};
  if(act==='swapundo'){SW[aId].pop();const p=JSON.parse(SW[aId].pop());Object.assign(S[a.id],JSON.parse(p.a));Object.assign(S[b.id],JSON.parse(p.b));a.swap=p.sa;b.swap=p.sb;}
  else if(act==='swapapprove')both('approved'); else if(act==='swapskip')both('skipped');
  else if(act==='swapsent')S[x.id].status='sent';
  else if(act==='swapyes'){S[x.id].status='yes';S[x.id].log.push(x.cands[S[x.id].i].name+' replied yes');}
  else if(act==='swapno'||act==='swapnoreply'){const y=S[x.id], c=x.cands[y.i], o=x.id===a.id?b:a, yo=S[o.id];
    y.log.push(c.name+(act==='swapno'?' said no, so the swap is off':' did not reply, so the swap is off'));
    if(y.i+1<x.cands.length){y.i++;y.status='pending';}else y.status='empty';
    if(yo.status==='approved')yo.status='pending'; yo.log.push('Was part of a swap that fell through');
    S[a.id].hist=[];S[b.id].hist=[];a.swap='';b.swap='';}
  else if(act==='swapintro')both('introduced');
  persist(); renderReview();
}

/* directory */
const hue=i=>(i*47+260)%360;
const initials=n=>n.split(' ').slice(0,2).map(w=>w[0]).join('');
const pin='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>';
const STAGES=['Idea','Pre-revenue','Early revenue','Growing','Post-seed','Series A'];
const byStage=(x,y)=>{const i=STAGES.indexOf(x),j=STAGES.indexOf(y);return (i<0?99:i)-(j<0?99:j)||x.localeCompare(y);};
function fillFilters(){
  const opt=(id,vals,cmp)=>{$(id).innerHTML=$(id).innerHTML+[...new Set(vals)].sort(cmp).map(v=>`<option>${esc(v)}</option>`).join('');};
  opt('ft',D.people.map(p=>p.topic),(x,y)=>x.localeCompare(y)); opt('fs',D.people.map(p=>p.stage),byStage);
}
/* Directory and Review share one notion of match status: pending/approved -> suggested,
   sent/yes -> invited, introduced -> introduced, skipped/empty -> out, no item at all -> none. */
function statusInfo(st){
  if(st==='pending'||st==='approved')return {key:'suggested',label:'Suggested'};
  if(st==='sent'||st==='yes')return {key:'invited',label:'Invited'};
  if(st==='introduced')return {key:'introduced',label:'Introduced'};
  if(st==='skipped'||st==='empty')return {key:'out',label:'Not this month'};
  return {key:'none',label:'No match yet'};
}
function matchStatus(personId){
  const it=byId(personId);
  return it?statusInfo(S[it.id].status):{key:'none',label:'No match yet'};
}
function helpingWhom(personId){
  const p=P(personId);
  if(!p)return [];
  return items.filter(it=>{
    const st=S[it.id];
    if(st.status==='skipped'||st.status==='empty')return false;
    const c=it.cands[st.i];
    return c&&c.hid===p.hid;
  }).map(it=>({founder:it.name,status:S[it.id].status,itemId:it.id}));
}
function renderDir(){
  if(!fmReady){fmReady=true;$('fm').innerHTML=
    '<option value="">Match status</option><option value="any">Any match</option><option value="suggested">Suggested</option><option value="invited">Invited</option>'+
    '<option value="introduced">Introduced</option><option value="out">Not this month</option><option value="none">No match yet</option>'+
    '<option value="helper">Is a helper</option>';}
  const dl=dataLine();
  let dirData=$('dirData');
  if(!dirData){dirData=document.createElement('p');dirData.id='dirData';dirData.className='muted';
    $('view-dir').querySelector('h1').insertAdjacentElement('afterend',dirData);}
  dirData.textContent=dl; dirData.hidden=!dl;
  const q=$('q').value.trim().toLowerCase(), t=$('ft').value, s=$('fs').value, m=$('fm').value;
  const list=D.people.filter(p=>{
    const hay=(p.name+' '+p.company+' '+p.role+' '+p.stuck+' '+p.lived+' '+p.can+' '+p.doing+' '+p.what).toLowerCase();
    const ms=matchStatus(p.id).key, isHelper=helpingWhom(p.id).length>0;
    return (!q||hay.includes(q))&&(!t||p.topic===t)&&(!s||p.stage===s)&&(!m||(m==='helper'?isHelper:m==='any'?['suggested','invited','introduced'].includes(ms):ms===m));});
  $('dcount').textContent=`${list.length} founder${list.length===1?'':'s'} found`;
  $('grid').innerHTML=list.map(p=>{const k=+p.id.slice(1), ms=matchStatus(p.id), helping=helpingWhom(p.id);
    return `<div class="pc click" data-act="detail" data-id="${p.id}" tabindex="0" role="button" aria-label="Open ${esc(p.name)}">
      <div class="ban" style="background:linear-gradient(120deg,hsl(${hue(k)} 70% 80%),hsl(${hue(k)+45} 75% 76%))"></div>
      <div class="in"><div class="av" style="background:hsl(${hue(k)} 60% 45%)">${esc(initials(p.name))}</div>
        <div><h3>${esc(p.name)}</h3><p class="muted clamp1">${esc(p.role)} at ${esc(p.company)}</p></div>
        <div class="row"><span class="pill">${esc(p.topic)}</span><span class="pill tag">${esc(p.stage)}</span></div>
        <div class="mini stuck"><span class="label">Stuck on</span><span class="clamp2">${esc(p.stuck)}</span></div>
        <div class="mini lived"><span class="label">Has lived through</span><span class="clamp2">${esc(p.lived)}</span></div>
        <div class="foot"><span><span class="dot ${ms.key}"></span>${esc(ms.label)}</span>${helping.length?`<span class="pill tag">Helping ×${helping.length}</span>`:''}<span>View</span></div></div></div>`;}).join('');
}
function renderDetail(id){
  const p=P(id), it=byId(id), ms=matchStatus(id), helping=helpingWhom(id);
  const matchBox=it?(()=>{const st=S[it.id],c=it.cands[st.i];
    return `<div class="box lived"><span class="label">This month's match</span>
      <p><b>${esc(c.name)}</b>, ${esc(c.company)}</p>
      <p class="muted">Has lived through: ${esc(c.lived)}</p>
      <p>${esc(ms.label)}</p>
      <p><button class="btn quiet small" data-act="gotocard" data-id="${esc(id)}">Open in Review</button></p></div>`;})():'';
  const helpingBox=helping.length?`<div class="box stuck"><span class="label">Asked to help</span>
      ${helping.map(h=>`<div class="row" style="justify-content:space-between"><span>Founder ${esc(h.founder)} · ${esc(statusInfo(h.status).label)}</span><button class="btn quiet small" data-act="gotocard" data-id="${esc(h.itemId)}">Open in Review</button></div>`).join('')}</div>`:'';
  $('ov').innerHTML=`<div class="panel enter" role="dialog" aria-label="${esc(p.name)}">
    <div class="row" style="justify-content:space-between"><div><h2>${esc(p.name)}</h2><p class="muted">${esc(p.role)} at ${esc(p.company)} · ${esc(p.loc)}</p></div><button class="btn quiet small" data-act="close">Close</button></div>
    <div class="row"><span class="pill">${esc(p.topic)}</span><span class="pill tag">${esc(p.stage)}</span><span class="pill tag">${esc(p.size)} people</span><span class="pill tag">Comes in ${esc(p.comes.toLowerCase())}</span></div>
    <p class="muted">${esc(p.what)}</p>
    <div class="box stuck"><span class="label">Stuck on</span>${esc(p.stuck)}</div>
    <div class="box lived"><span class="label">Has lived through</span>${esc(p.lived)}</div>
    ${matchBox}${helpingBox}
    <p><b>Can help with:</b> ${esc(p.can)}</p><p><b>Working on:</b> ${esc(p.doing)}</p>
    <p><b>Email:</b> ${esc(p.email)}</p>
    <div class="row" style="justify-content:space-between"><span><span class="dot ${ms.key}"></span>${esc(ms.label)}</span><button class="btn" data-act="find" data-id="${id}">${it?'Pick a different helper':'Find a helper'}</button></div></div>`;
  $('ov').hidden=false;
}

/* find a helper */
const FH={ask:null,q:'',helper:null,line:''};
const invited=hid=>items.some(it=>['approved','sent','yes','introduced','met'].includes(S[it.id].status)&&it.cands[S[it.id].i].hid===hid);
function renderFind(){
  const a=P(FH.ask);
  let inner=`<div class="row" style="justify-content:space-between"><h2>Find a helper for ${esc(a.name)}</h2><button class="btn quiet small" data-act="close">Close</button></div>
    <div class="box stuck"><span class="label">Stuck on</span>${esc(a.stuck)}</div>`;
  if(!FH.helper){
    const q=FH.q.trim().toLowerCase();
    const res=D.people.filter(p=>p.id!==a.id&&p.company!==a.company).map(p=>{const hay=(p.lived+' '+p.can).toLowerCase();return {p,hit:q?q.split(/\s+/).filter(w=>hay.includes(w)).length:0};})
      .filter(r=>!q||r.hit>0).sort((x,y)=>y.hit-x.hit).slice(0,6);
    inner+=`<div class="field"><label class="label" for="fq">Search what helpers have lived through or can help with</label><input id="fq" value="${esc(FH.q)}" placeholder="Try: grant, hiring, procurement" autocomplete="off"></div>
      <p class="muted">Same-company people are left out.</p>
      ${res.map(r=>`<div class="res"><div class="who" style="flex:1;min-width:200px"><p><b>${esc(r.p.name)}</b>, ${esc(r.p.company)}</p><p class="muted">Lived through: ${esc(r.p.lived)}</p><p class="muted">Can help with: ${esc(r.p.can)}</p>
        ${invited(r.p.hid)?'<p><span class="pill warn">Already has an open invitation this month</span></p>':''}</div><button class="btn small" data-act="pick" data-id="${r.p.id}">Pick</button></div>`).join('')||'<p class="muted">No one found. Try a different word.</p>'}`;
  }else{
    const h=FH.helper;
    inner+=`<p>Helper: <b>${esc(h.name)}</b>, ${esc(h.company)}</p><p class="muted">Lived through: ${esc(h.lived)}</p>
      <div class="field"><label class="label" for="fl">One sentence for the invitation</label><textarea id="fl" rows="3" placeholder="You ..., and this founder is working on ...">${esc(FH.line)}</textarea>
      <p class="muted">The helper reads this. Leave out the founder's name, company and own words.</p></div>
      <div class="row"><button class="btn" data-act="create" ${FH.line.trim()?'':'disabled'}>Add to Review</button><button class="btn quiet" data-act="back">Back to results</button></div>`;
  }
  const was=!$('ov').hidden; $('ov').innerHTML=`<div class="panel${was?'':' enter'}" role="dialog" aria-label="Find a helper">${inner}</div>`; $('ov').hidden=false;
}
function createManual(){
  const a=P(FH.ask), h=FH.helper, line=FH.line.trim(), subject='A fellow founder could use your experience';
  const ref=a.id+'-'+h.hid;
  const body=`Hi ${fn(h.name)},\n\nA fellow Volta founder is working on something where your experience could help.\n\n${line}\n\nWould you be open to a 20-minute intro? If you say yes, I'll introduce you by name. If not, nothing happens and they won't know.\n\nTo say yes, just reply YES to this email. Not a good time? You can ignore it.\n\nLaura\n\n(Ref: ${ref})`;
  const meet=(a.lunch&&h.lunch)?'Founders Lunch':(a.breakfast&&h.breakfast)?'CEO Breakfast':'';
  const cand={hid:h.hid,ref,name:h.name,company:h.company,role:h.role,lived:h.lived,reason:line,to:h.email,subject,body,link:gmail(h.email,subject,body),meet};
  const ex=byId(a.id);
  if(ex){ex.cands.unshift(cand);S[a.id]={status:'pending',i:0,log:['Picked by Laura'],hist:[],reply:''};}
  else{items.unshift({id:a.id,name:a.name,company:a.company,email:a.email,doing:a.doing,stuck:a.stuck,topic:a.topic,cands:[cand],swap:'',manual:true});
    S[a.id]={status:'pending',i:0,log:[],hist:[],reply:''};}
  a.matched=true; $('ov').hidden=true; FH.helper=null; FH.line=''; persist(); setTab('review');
}

function setTab(t){
  ['import','review','dir'].forEach(v=>{$('view-'+v).hidden=v!==t;$('tab-'+v).setAttribute('aria-selected',v===t);});
  if(t==='review')renderReview(); if(t==='dir')renderDir(); if(t==='import')renderImport();
  const v=$('view-'+t); v.classList.remove('enter'); void v.offsetWidth; v.classList.add('enter');
  scrollTo(0,0);
}
/* import */
const REQUIRED=['Name','Company','Stuck on','Lived through','Can help with'];
const OPTIONAL=['Role','Stage','Team size','Location','Happier Hour sign-up topic','Working on now','Going to next Founders Lunch','Going to next CEO Breakfast','Consent'];
const SAMPLE_COLS=['Name','Company','Role','What the company does','Stage','Team size','Location','Comes into Volta','Working on now','Lived through','Stuck on','Happier Hour sign-up topic','Can help with','Going to next Founders Lunch','Going to next CEO Breakfast'];
function renderImport(){
  const rows=D.people.map(p=>({'Name':p.name,'Company':p.company,'Stuck on':p.stuck,'Lived through':p.lived,'Can help with':p.can}));
  const chk=c=>`<span><span class="dot ${SAMPLE_COLS.includes(c)?'g':'a'}"></span>${esc(c)}</span>`;
  const prev=rows.slice(0,3).map(r=>`<tr><td class="mask">•••• ••••</td><td>${esc(r['Stuck on']||'')}</td><td>${esc(r['Lived through']||'')}</td></tr>`).join('');
  if(API!==null)renderUpload();
  if(API!==null&&!D.month){$('importOut').innerHTML='<p class="muted">No month processed yet. Upload the export above.</p>';return;}
  $('importOut').innerHTML=`
    <p><b>${esc(D.month||'this month')}/happier-hour.csv</b> · ${D.total} founder${D.total===1?'':'s'} <span class="pill good">Ready</span></p>
    <p class="muted">${API!==null?'Processed by backend/run_month.py. To load a new month, upload its export above.':'Processed by backend/run_month.py. To load a new month, put the export in data/&lt;month&gt;/ and run it again.'}</p>
    <details><summary>Column check</summary><div class="chk" style="margin-top:8px">${REQUIRED.map(chk).join('')}</div><p class="label" style="margin-top:10px">Optional</p><div class="chk" style="margin-top:6px">${OPTIONAL.map(chk).join('')}</div></details>
    <div><span class="label">Preview. Names and emails stay out of the matching.</span>
      <div class="scroll" style="margin-top:6px"><table><thead><tr><th>Name</th><th>Stuck on</th><th>Lived through</th></tr></thead><tbody>${prev}</tbody></table></div></div>
    <div class="row"><button class="btn" data-act="startmatch">Show this month's matches</button></div>`;
}
/* upload (local server only): save the CSV into data/<month>/, run run_month.py, then reload data.json */
function renderUpload(){
  const box=$('uploadBox'); box.hidden=false;
  box.innerHTML=`<div class="row"><label class="label" for="upMonth">Month</label><select id="upMonth" aria-label="Month"></select>
      <input type="text" id="upNew" placeholder="or new month, YYYY-MM" aria-label="New month" size="18" autocomplete="off"></div>
    <input type="file" id="upFile" class="sr-only" accept=".csv,text/csv" aria-label="Happier Hour export">
    <label for="upFile" class="dropzone" id="upDrop"></label>
    <p id="upCheck" class="upcheck" hidden></p>
    ${API_KEY_SET?'':'<p class="banner">The server was started without an API key. Restart it with the key set, or matches will not run.</p>'}
    <div class="row"><button class="btn" id="upGo" data-act="upload" disabled>Upload and match</button></div>
    <div id="upStatus"></div>`;
  const dz=$('upDrop');
  dz.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='copy';dz.classList.add('over');});
  dz.addEventListener('dragleave',e=>{if(!dz.contains(e.relatedTarget))dz.classList.remove('over');});
  dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('over');const f=e.dataTransfer.files[0];if(!f)return;
    try{const dt=new DataTransfer();dt.items.add(f);$('upFile').files=dt.files;}catch(_){}  // upSel is what gets uploaded either way
    pickFile(f);});
  drawDrop(); checkFile(); drawUploadStatus();
  const fill=()=>{const sel=$('upMonth');if(!sel)return;
    sel.innerHTML=(MONTHS||[]).map(m=>`<option value="${esc(m.month)}">${esc(m.month)}${m.processed?'':' (not processed)'}</option>`).join('')||'<option value="">No months yet</option>';};
  if(MONTHS){fill();return;}
  fetch(API+'/api/months',{cache:'no-store'}).then(r=>r.json()).then(j=>{MONTHS=Array.isArray(j&&j.months)?j.months:[];API_KEY_SET=j&&j.api_key_set!==false;renderUpload();}).catch(()=>{MONTHS=[];fill();});
}
let upSel=null, upOk=false;  // the chosen CSV, and whether its header passed the check
const UPLOAD_ICON='<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>';
function drawDrop(){
  const dz=$('upDrop'); if(!dz)return;
  dz.innerHTML=upSel
    ?`<b>${esc(upSel.name)}</b><span class="muted">${Math.max(1,Math.round(upSel.size/1024))} KB</span><button type="button" class="btn quiet small" data-act="upchange">Change</button>`
    :`${UPLOAD_ICON}<b>Drop the Happier Hour export here, or click to choose</b><span class="muted" style="font-size:.85rem">CSV with columns: ${REQUIRED.join(', ')}</span>`;
}
function pickFile(f){upSel=f||null;upOk=false;drawDrop();checkFile();}
const readText=blob=>new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result));r.onerror=()=>rej(r.error);r.readAsText(blob);});
function countRows(t){  // records after the header; quoted fields may hold line breaks
  let n=0,q=false,has=false;
  for(const ch of t){if(ch==='"')q=!q;if(ch==='\n'&&!q){if(has)n++;has=false;}else if(ch.trim())has=true;}
  return Math.max(0,n+(has?1:0)-1);
}
/* Before uploading, check the first line of the file has the columns the backend needs. */
async function checkFile(){
  const f=upSel, el=$('upCheck'), go=$('upGo'); if(!el||!go)return;
  go.disabled=true;
  if(!f){el.hidden=true;return;}
  let msg, ok;
  try{
    const head=(await readText(f.slice(0,2048))).replace(/^\uFEFF/,'').split(/\r?\n/)[0];
    const cols=head.split(',').map(c=>c.replace(/"/g,'').trim());
    const missing=REQUIRED.filter(c=>!cols.includes(c));
    const generated=/helpers\.csv|needs\.csv/.test(f.name.toLowerCase());
    ok=!missing.length&&!generated;
    msg=missing.length?`This does not look like the Happier Hour export. Missing: ${missing.join(', ')}.`:'';
    if(ok){const rows=countRows(await readText(f));msg=`Looks right. ${rows} row${rows===1?'':'s'}.`;}
    if(generated)msg=(msg?msg+' ':'')+'This is a file the backend generated, not the export.';
  }catch(_){ok=false;msg='Could not read that file.';}
  if(f!==upSel)return;  // another file was picked meanwhile
  upOk=ok; el.className='upcheck '+(ok?'ok':'bad'); el.textContent=msg; el.hidden=false;
  go.disabled=!ok||!!(UP&&UP.busy);
}
function drawUploadStatus(){
  const el=$('upStatus'); if(!el)return;
  if(!UP){el.innerHTML='';return;}
  if(UP.busy){el.innerHTML='<p><span class="spin" aria-hidden="true"></span> Processing, this takes about a minute…</p>';return;}
  if(UP.ok){el.innerHTML=`<p><span class="pill good">Done</span> ${esc(UP.month)}: ${UP.matches} match${UP.matches===1?'':'es'}.</p><pre class="email">${esc(UP.tail)}</pre>`;return;}
  el.innerHTML=`<p style="color:var(--bad)"><b>${esc(UP.err)}</b></p>${UP.log?`<pre class="email">${esc(UP.log)}</pre>`:''}`;
}
async function doUpload(b){
  const month=$('upNew').value.trim()||$('upMonth').value, file=upSel;
  if(!/^\d{4}-\d{2}$/.test(month)){UP={err:'Month must look like 2026-10.'};drawUploadStatus();return;}
  if(!file){UP={err:'Choose the CSV export first.'};drawUploadStatus();return;}
  b.disabled=true; UP={busy:true}; drawUploadStatus();
  const fd=new FormData(); fd.append('file',file);
  let j;
  try{const r=await fetch(API+'/api/upload?month='+encodeURIComponent(month),{method:'POST',body:fd});
    try{j=await r.json();}catch(_){j={ok:false,log:'The server answered '+r.status+' without a log.'};}
    if(!r.ok)j.ok=false;}
  catch(e){j={ok:false,log:String(e)};}
  if(!j.ok){UP={err:'Processing failed. The full log is below.',log:j.log||''};b.disabled=!upOk;drawUploadStatus();return;}
  UP={ok:true,month,matches:j.matches,tail:String(j.log||'').trim().split('\n').slice(-6).join('\n')}; MONTHS=null;
  try{const r=await fetch(API+'data.json?t='+Date.now(),{cache:'no-store'});await boot(await r.json(),'review');}
  catch(e){UP={err:'Processed, but data.json could not be reloaded. Refresh the page.',log:String(e)};b.disabled=!upOk;drawUploadStatus();}
}
function settle(id){requestAnimationFrame(()=>{const el=document.querySelector(`[data-card="${id}"]`);if(!el)return;
  el.classList.add('flash');const r=el.getBoundingClientRect();if(r.top<80||r.bottom>innerHeight)el.scrollIntoView({behavior:reduceMotion()?'auto':'smooth',block:'center'});
  setTimeout(()=>el.classList.remove('flash'),900);});}
function doJump(j){
  if(j==='dir'){setTab('dir');return;}
  const el=$('sec-'+j); if(!el)return;
  el.scrollIntoView({behavior:reduceMotion()?'auto':'smooth',block:'start'});
  const h=el.querySelector('h2'); if(h){h.classList.add('flash');setTimeout(()=>h.classList.remove('flash'),900);}
}
function ensureToTop(){
  if($('toTop'))return;
  const btn=document.createElement('button');
  btn.id='toTop'; btn.className='totop'; btn.setAttribute('aria-label','Back to top'); btn.textContent='↑';
  document.body.appendChild(btn);
  btn.addEventListener('click',()=>scrollTo({top:0,behavior:reduceMotion()?'auto':'smooth'}));
  let ticking=false;
  window.addEventListener('scroll',()=>{
    if(ticking)return; ticking=true;
    requestAnimationFrame(()=>{btn.classList.toggle('show',window.scrollY>400);ticking=false;});
  });
}
const snap=(s,sw)=>JSON.stringify({status:s.status,i:s.i,log:s.log,reply:s.reply,sw:!!sw});
document.addEventListener('click',e=>{
  const tab=e.target.closest('[data-tab]'); if(tab){setTab(tab.dataset.tab);return;}
  const jump=e.target.closest('[data-jump]'); if(jump){doJump(jump.dataset.jump);return;}
  const b=e.target.closest('[data-act]'); if(!b)return;
  const act=b.dataset.act, id=b.dataset.id;
  if(id&&!['copy','detail','find','pick','close','back','create','showmail','details','startmatch','gotocard'].includes(act)){const x=byId(id);if(x)settle(x.swap&&x.id>x.swap?x.swap:x.id);}
  if(act==='gotocard'){$('ov').hidden=true;setTab('review');const x=byId(id);settle(x&&x.swap&&x.id>x.swap?x.swap:id);return;}
  if(act==='startmatch'){setTab('review');return;}
  if(act==='upload'){doUpload(b);return;}
  if(act==='upchange'){e.preventDefault();$('upFile').click();return;}
  if(act==='reset'){if(!confirmReset){confirmReset=true;b.textContent='Click again to clear this month';setTimeout(()=>{confirmReset=false;renderReview();},4000);return;}
    try{localStorage.removeItem(STORE_KEY);}catch(_){}
    if(API!==null){clearTimeout(putTimer);putTimer=null;putTracker({}).finally(()=>location.reload());return;}
    location.reload();return;}
  if(act==='export'){const asks=items.map((it,k)=>{const st=S[it.id],c=it.cands[st.i];const map={pending:'pending',approved:'invited',sent:'invited',yes:'yes',introduced:'introduced',skipped:'skipped',empty:'exhausted'};
      return {aid:'ask-'+(k+1),ask_id:it.id,status:map[st.status]||st.status,current:c.hid,ref:c.ref,sent:['sent','yes','introduced'].includes(st.status),log:st.log};});
    const blob=new Blob([JSON.stringify({...snapshot(),asks},null,1)],{type:'application/json'});
    const u=URL.createObjectURL(blob),l=document.createElement('a');l.href=u;l.download='tracker-'+(D.month||'month')+'.json';document.body.appendChild(l);l.click();l.remove();setTimeout(()=>URL.revokeObjectURL(u),500);return;}
  if(act==='copy'){const el=$('em-'+id);const fb=()=>{const r=document.createRange();r.selectNodeContents(el);const s=getSelection();s.removeAllRanges();s.addRange(r);b.textContent='Selected, press copy';};
    try{navigator.clipboard.writeText(el.innerText).then(()=>{b.textContent='Copied'},fb);}catch(_){fb();} return;}
  if(act==='detail'){renderDetail(id);return;}
  if(act==='find'){FH.ask=id;FH.q='';FH.helper=null;FH.line='';renderFind();return;}
  if(act==='close'){$('ov').hidden=true;return;}
  if(act==='pick'){FH.helper=P(id);renderFind();return;}
  if(act==='back'){FH.helper=null;renderFind();return;}
  if(act==='create'){createManual();return;}
  if(act.startsWith('swap')){swapAct(act,id);return;}
  const st=S[id], it=byId(id); if(!it)return; const c=it.cands[st.i];
  if(act==='details'){st.details=!st.details;renderReview();return;}
  if(act==='undo'){const p=JSON.parse(st.hist.pop());if(p.sw&&it.swap){const o=S[it.swap];if(o.hist.length){const q=JSON.parse(o.hist.pop());delete q.sw;Object.assign(o,q);}}delete p.sw;Object.assign(st,p);persist();renderReview();return;}
  st.hist.push(snap(st));
  if(act==='approve')st.status='approved'; else if(act==='skip')st.status='skipped';
  else if(act==='sent'){st.status='sent';st.reply='';}
  else if(act==='simyes'){st.reply='yes';st.log.push(c.name+' replied yes');st.status='yes';}
  else if(act==='simno'||act==='noreply'){st.log.push(c.name+(act==='simno'?' said no':' did not reply'));
    if(st.i+1<it.cands.length){st.i++;st.status='pending';st.reply='';}else st.status='empty';}
  else if(act==='intro')st.status='introduced';
  persist(); renderReview();
},{signal:opts.signal});
document.addEventListener('keydown',e=>{if(e.key!=='Enter')return;
  if(e.target.classList&&e.target.classList.contains('pc')){renderDetail(e.target.dataset.id);return;}
  const jump=e.target.closest&&e.target.closest('[data-jump]'); if(jump){doJump(jump.dataset.jump);}},{signal:opts.signal});
document.addEventListener('change',e=>{
  if(e.target.id==='upFile'){pickFile(e.target.files[0]);return;}
  if(e.target.id==='trackerFile'&&e.target.files[0]){const r=new FileReader();r.onload=()=>{try{const snap=JSON.parse(String(r.result));
      if(snap.month!==D.month){alert2(`That file is for ${snap.month||'another month'}; this page is ${D.month}.`);return;}
      if(restore(snap)){lastSaved=snap.saved||new Date().toISOString();persist();renderReview();}}catch(_){alert2('Could not read that file.');}};r.readAsText(e.target.files[0]);e.target.value='';}},{signal:opts.signal});
function alert2(msg){$('exportBar').insertAdjacentHTML('beforeend',`<span class="pill bad">${esc(msg)}</span>`);}
document.addEventListener('input',e=>{
  if(['q'].includes(e.target.id)||e.target.id==='ft'||e.target.id==='fs'||e.target.id==='fm')renderDir();
  if(e.target.id==='fq'){FH.q=e.target.value;const pos=e.target.selectionStart;renderFind();const n=$('fq');n.focus();n.setSelectionRange(pos,pos);}
  if(e.target.id==='fl'){FH.line=e.target.value;const bt=document.querySelector('[data-act=create]');if(bt)bt.disabled=!FH.line.trim();}
},{signal:opts.signal});
/* the panel closes on a click on the grey backdrop (press and release both outside the panel) or on Esc; the tab stays as it is */
let downOnOv=false;
$('ov').addEventListener('mousedown',e=>{downOnOv=e.target===e.currentTarget;},{signal:opts.signal});
$('ov').addEventListener('click',e=>{if(e.target===e.currentTarget&&downOnOv)e.currentTarget.hidden=true;},{signal:opts.signal});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('ov').hidden)$('ov').hidden=true;},{signal:opts.signal});
let resumed=false;
if(API!==null&&opts.serverSnap&&restore(opts.serverSnap)){lastSaved=opts.serverSnap.saved||'';resumed=true;}
if(!resumed)resumed=loadLocal();
fillFilters(); ensureToTop(); setTab(opts.tab||(resumed?'review':'import'));
}

/* (Re)start the page with a data set. With the server, the tracker file for the month is read first.
   A restart drops the previous start()'s listeners and the filter options it added. */
async function boot(D,tab){
  let serverSnap=null;
  if(API!==null&&D.month){try{const r=await fetch(API+'/api/tracker?month='+encodeURIComponent(D.month),{cache:'no-store'});if(r.ok)serverSnap=await r.json();}catch(_){}}
  if(CTL){CTL.abort();document.getElementById('ft').innerHTML='<option value="">Topic</option>';document.getElementById('fs').innerHTML='<option value="">Stage</option>';}
  CTL=new AbortController();
  start(D,{tab,serverSnap,signal:CTL.signal});
}

(async()=>{
  if(API!==null){  // served: data.json only; with none yet, start empty so the upload is still there
    try{const r=await fetch(API+'data.json?t='+Date.now(),{cache:'no-store'});if(r.ok){await boot(await r.json());return;}}catch(_){}
    await boot({month:'',items:[],people:[],left:[],total:0},'import');return;}
  try{const r=await fetch('data.json',{cache:'no-store'});if(r.ok){start(await r.json());return;}}catch(_){}
  if(window.VPM_DATA){start(window.VPM_DATA);return;}
  document.querySelector('.wrap').innerHTML='<div class="bar"><h2>No data yet</h2><p class="muted">Run <code>python backend/run_month.py --folder data/2026-10</code> to create frontend/data.json.</p></div>';
})();
