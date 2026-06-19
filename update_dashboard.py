"""
PAPANATO Dashboard Updater
Corre en GitHub Actions cada lunes.
Scrapea Google Maps + TheFork via Apify REST API y regenera index.html.
"""

import os, json, time, base64, urllib.request, urllib.error
from datetime import datetime, timedelta
from collections import defaultdict

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
TODAY = datetime.utcnow().strftime("%Y-%m-%d")

LOCALES_GMAPS = [
    ("Les Corts",       "https://www.google.com/maps/place/Papanato+%7C+Les+Corts/@41.3816,-2.1386,17z"),
    ("Sagrada Família", "https://www.google.com/maps/place/Papanato+%7C+Sagrada+Fam%C3%ADlia/@41.4036,-2.1736,17z"),
    ("Mercat Valencia", "https://www.google.com/maps/place/Papanato+Plaza+Mercado/@39.4745,-0.3779,17z"),
    ("Poblenou",        "https://www.google.com/maps/place/Papanato+Poblenou/@41.3987,-2.1929,17z"),
]

LOCALES_TF = [
    ("Sagrada Família", "https://www.thefork.com/restaurant/papanato-sagrada-familia-r642943/reviews"),
    ("Mercat Valencia", "https://www.thefork.com/restaurant/papanato-plaza-del-mercat-r660459/reviews"),
    ("Les Corts",       "https://www.thefork.com/restaurant/papanato-les-corts-r835200/reviews"),
    ("Poblenou",        "https://www.thefork.com/restaurant/papanato-poblenou-r951200/reviews"),
]

GMAPS_NAME_MAP = {
    "Papanato | Les Corts": "Les Corts",
    "Papanato | Sagrada Família": "Sagrada Família",
    "Papanato Plaza Mercado": "Mercat Valencia",
    "Papanato Poblenou": "Poblenou",
}

TF_URL_MAP = {
    "papanato-sagrada-familia": "Sagrada Família",
    "papanato-plaza-del-mercat": "Mercat Valencia",
    "papanato-les-corts": "Les Corts",
    "papanato-poblenou": "Poblenou",
}


def apify_get(path):
    url = f"https://api.apify.com/v2{path}{'&' if '?' in path else '?'}token={APIFY_TOKEN}"
    req = urllib.request.Request(url, headers={"User-Agent": "PAPANATO-Dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def apify_post(path, data):
    url = f"https://api.apify.com/v2{path}{'&' if '?' in path else '?'}token={APIFY_TOKEN}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body,
        headers={"User-Agent": "PAPANATO-Dashboard/1.0", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def run_actor(actor_id, input_data, label=""):
    print(f"  Starting {label}...")
    result = apify_post(f"/acts/{actor_id}/runs", input_data)
    run_id = result["data"]["id"]
    dataset_id = result["data"]["defaultDatasetId"]
    # Poll until done
    for _ in range(120):
        time.sleep(10)
        status = apify_get(f"/actor-runs/{run_id}")["data"]["status"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"  {label} failed: {status}")
            return []
    print(f"  {label} done, fetching items...")
    items = apify_get(f"/datasets/{dataset_id}/items?limit=2000")
    return items if isinstance(items, list) else items.get("items", [])


def scrape_gmaps():
    print("Scraping Google Maps...")
    start_urls = [{"url": url} for _, url in LOCALES_GMAPS]
    items = run_actor("compass/Google-Maps-Reviews-Scraper",
        {"startUrls": start_urls, "maxReviews": 150, "reviewsSort": "newest",
         "language": "es", "includeReviewId": False}, "Google Maps")
    reviews = []
    for r in items:
        local = GMAPS_NAME_MAP.get(r.get("title", ""), r.get("title", "Unknown"))
        date = (r.get("publishedAtDate") or "")[:10]
        stars = float(r.get("stars") or 0)
        text = (r.get("text") or "").strip()[:200]
        entry = {"l": local, "c": "Google", "f": date, "p": stars}
        if text:
            entry["t"] = text
        reviews.append(entry)
    print(f"  Google Maps: {len(reviews)} reviews")
    return reviews


def scrape_thefork():
    print("Scraping TheFork...")
    all_reviews = []
    for local, url in LOCALES_TF:
        items = run_actor("stealth_mode/thefork-reviews-scraper",
            {"startUrls": [{"url": url}], "maxReviews": 300}, f"TheFork {local}")
        for r in items:
            date = (r.get("meal_date") or "")[:10]
            rv = float(r.get("rating_value") or 0)
            rv5 = round(rv / 2, 2)
            body = ((r.get("review") or {}).get("review_body") or "").strip()[:200]
            entry = {"l": local, "c": "TheFork", "f": date, "p": rv5}
            if body:
                entry["t"] = body
            all_reviews.append(entry)
    print(f"  TheFork: {len(all_reviews)} reviews")
    return all_reviews


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PAPANATO — Dashboard de Reseñas</title>
<style>
:root{color-scheme:light;--naranja:#E63E00;--marron:#2F1E18;--caramelo:#BE986E;--crema:#F0D6A5;--verde:#006445;--amarillo:#F9A825;--rojo:#C62828;--bg:#1C1009;--card:#2A1A10;--card2:#341F12;--text:#F0D6A5;--text-muted:#BE986E;--border:#4a2d1a;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:Arial,sans-serif;min-height:100vh;}
.header{background:var(--marron);border-bottom:3px solid var(--naranja);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;}
.logo-text{font-size:22px;font-weight:900;color:var(--naranja);letter-spacing:2px;}
.logo-sub{font-size:10px;color:var(--caramelo);letter-spacing:3px;text-transform:uppercase;margin-top:-2px;}
.header-title{font-size:15px;color:var(--crema);font-weight:bold;}
.header-meta{font-size:12px;color:var(--text-muted);}
.filters{background:var(--card);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;flex-wrap:wrap;gap:16px;align-items:center;}
.filter-label{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;}
.chip-group{display:flex;gap:6px;flex-wrap:wrap;}
.chip{background:var(--card2);border:1px solid var(--border);color:var(--text-muted);padding:5px 13px;border-radius:20px;font-size:12px;cursor:pointer;transition:all .15s;}
.chip:hover{border-color:var(--caramelo);color:var(--crema);}
.chip.active{background:var(--naranja);border-color:var(--naranja);color:white;font-weight:bold;}
.chip.google.active{background:#4285f4;border-color:#4285f4;}
.chip.thefork.active{background:#00975F;border-color:#00975F;}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:20px 24px 12px;}
@media(max-width:800px){.kpis{grid-template-columns:repeat(2,1fr);}}
.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;position:relative;overflow:hidden;}
.kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--naranja);}
.kpi-card.verde::before{background:var(--verde);}
.kpi-card.caramelo::before{background:var(--caramelo);}
.kpi-card.amarillo::before{background:var(--amarillo);}
.kpi-label{font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;}
.kpi-value{font-size:32px;font-weight:900;color:var(--crema);line-height:1;}
.kpi-value.naranja{color:var(--naranja);}
.kpi-value.verde{color:#2ECC71;}
.kpi-value.caramelo{color:var(--caramelo);}
.kpi-sub{font-size:11px;color:var(--text-muted);margin-top:6px;}
.charts-row{display:grid;grid-template-columns:2fr 1fr;gap:16px;padding:0 24px 16px;}
@media(max-width:900px){.charts-row{grid-template-columns:1fr;}}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;}
.chart-title{font-size:13px;font-weight:bold;color:var(--caramelo);text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;}
.locales-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:0 24px 16px;}
@media(max-width:900px){.locales-row{grid-template-columns:repeat(2,1fr);}}
.local-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;}
.local-name{font-size:13px;font-weight:bold;color:var(--crema);margin-bottom:10px;border-bottom:1px solid var(--border);padding-bottom:8px;}
.local-stat{display:flex;justify-content:space-between;font-size:12px;color:var(--text-muted);margin-bottom:4px;}
.local-stat span:last-child{color:var(--crema);font-weight:bold;}
.stars-bar{height:6px;background:var(--card2);border-radius:3px;margin-top:8px;overflow:hidden;}
.stars-fill{height:100%;background:linear-gradient(90deg,var(--naranja),var(--amarillo));border-radius:3px;}
.reviews-section{padding:0 24px 24px;}
.section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}
.section-title{font-size:13px;font-weight:bold;color:var(--caramelo);text-transform:uppercase;letter-spacing:1px;}
.review-count{font-size:12px;color:var(--text-muted);}
.reviews-list{display:flex;flex-direction:column;gap:8px;max-height:400px;overflow-y:auto;}
.reviews-list::-webkit-scrollbar{width:6px;}
.reviews-list::-webkit-scrollbar-track{background:var(--card2);}
.reviews-list::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
.review-item{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 14px;display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:start;}
.review-body{font-size:12px;color:var(--text-muted);line-height:1.5;}
.review-text{color:var(--crema);margin-bottom:3px;}
.review-meta{text-align:right;font-size:11px;color:var(--text-muted);white-space:nowrap;}
.canal-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:bold;margin-bottom:4px;}
.canal-badge.google{background:#4285f420;color:#7baaf7;border:1px solid #4285f440;}
.canal-badge.thefork{background:#00975F20;color:#2ECC71;border:1px solid #00975F40;}
</style>
</head>
<body>
<div class="header">
  <div style="display:flex;align-items:center;gap:16px;">
    <div><div class="logo-text">PAPANATO</div><div class="logo-sub">Bar de Papas</div></div>
    <div><div class="header-title">Dashboard de Reseñas</div>
    <div class="header-meta">Actualizado: __TODAY__ · __TOTAL__ reseñas · Google Maps + TheFork</div></div>
  </div>
</div>
<div class="filters">
  <div style="display:flex;align-items:center;gap:8px;"><span class="filter-label">Local</span>
    <div class="chip-group" id="filter-local">
      <div class="chip active" data-val="Todos">Todos</div>
      <div class="chip" data-val="Les Corts">Les Corts</div>
      <div class="chip" data-val="Poblenou">Poblenou</div>
      <div class="chip" data-val="Sagrada Família">Sgda. Família</div>
      <div class="chip" data-val="Mercat Valencia">Mercat Valencia</div>
    </div></div>
  <div style="display:flex;align-items:center;gap:8px;"><span class="filter-label">Canal</span>
    <div class="chip-group" id="filter-canal">
      <div class="chip active" data-val="Todos">Todos</div>
      <div class="chip google" data-val="Google">Google Maps</div>
      <div class="chip thefork" data-val="TheFork">TheFork</div>
    </div></div>
  <div style="display:flex;align-items:center;gap:8px;"><span class="filter-label">Período</span>
    <div class="chip-group" id="filter-period">
      <div class="chip" data-val="7">7 días</div>
      <div class="chip" data-val="30">1 mes</div>
      <div class="chip" data-val="60">2 meses</div>
      <div class="chip active" data-val="90">3 meses</div>
    </div></div>
</div>
<div class="kpis">
  <div class="kpi-card"><div class="kpi-label">Total reseñas</div><div class="kpi-value naranja" id="kpi-total">—</div><div class="kpi-sub" id="kpi-total-sub"></div></div>
  <div class="kpi-card verde"><div class="kpi-label">Puntuación promedio</div><div class="kpi-value verde" id="kpi-avg">—</div><div class="kpi-sub">sobre 5 estrellas</div></div>
  <div class="kpi-card caramelo"><div class="kpi-label">Reseñas positivas ≥4★</div><div class="kpi-value caramelo" id="kpi-pos">—</div><div class="kpi-sub">del total del período</div></div>
  <div class="kpi-card amarillo"><div class="kpi-label">Última semana</div><div class="kpi-value" id="kpi-week">—</div><div class="kpi-sub" id="kpi-week-sub"></div></div>
</div>
<div class="charts-row">
  <div class="chart-card"><div class="chart-title">Evolución semanal — Reseñas y puntuación</div><div id="weekly-chart-container" style="height:220px;"></div></div>
  <div class="chart-card"><div class="chart-title">Distribución por puntuación</div><div id="dist-chart-container" style="height:220px;display:flex;align-items:center;justify-content:center;"></div></div>
</div>
<div class="locales-row" id="locales-row"></div>
<div class="reviews-section">
  <div class="section-header"><div class="section-title">Últimas reseñas</div><div class="review-count" id="reviews-shown"></div></div>
  <div class="reviews-list" id="reviews-list"></div>
</div>
<script>
const RAW=__DATA__;
const TODAY_STR="__TODAY__";
let state={local:'Todos',canal:'Todos',days:90};
['filter-local','filter-canal','filter-period'].forEach(id=>{
  document.getElementById(id).querySelectorAll('.chip').forEach(c=>{
    c.addEventListener('click',()=>{
      document.getElementById(id).querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
      c.classList.add('active');
      if(id==='filter-local')state.local=c.dataset.val;
      else if(id==='filter-canal')state.canal=c.dataset.val;
      else state.days=parseInt(c.dataset.val);
      update();
    });
  });
});
function getFiltered(){
  const d=new Date(TODAY_STR);d.setDate(d.getDate()-state.days);
  const cs=d.toISOString().slice(0,10);
  return RAW.reviews.filter(r=>{
    if(state.local!=='Todos'&&r.l!==state.local)return false;
    if(state.canal!=='Todos'&&r.c!==state.canal)return false;
    if(r.f<cs)return false;
    return true;
  });
}
function update(){
  const rev=getFiltered(),n=rev.length;
  const avg=n>0?rev.reduce((s,r)=>s+r.p,0)/n:0;
  const pos=n>0?Math.round(rev.filter(r=>r.p>=4).length/n*100):0;
  const wc=new Date(TODAY_STR);wc.setDate(wc.getDate()-7);
  const ws=wc.toISOString().slice(0,10);
  const wrev=rev.filter(r=>r.f>=ws);
  const wavg=wrev.length>0?wrev.reduce((s,r)=>s+r.p,0)/wrev.length:0;
  document.getElementById('kpi-total').textContent=n.toLocaleString();
  document.getElementById('kpi-total-sub').textContent=[...new Set(rev.map(r=>r.c))].join(' + ');
  document.getElementById('kpi-avg').textContent=avg.toFixed(2);
  document.getElementById('kpi-pos').textContent=pos+'%';
  document.getElementById('kpi-week').textContent=wrev.length;
  document.getElementById('kpi-week-sub').textContent=wavg>0?'avg '+wavg.toFixed(1)+'★':'';
  renderWeekly(rev);renderDist(rev);renderLocales(rev);renderReviews(rev);
}
function getWeeks(reviews){
  const today=new Date(TODAY_STR),weeks=[],nw=Math.min(12,Math.ceil(state.days/7));
  for(let i=nw-1;i>=0;i--){
    const end=new Date(today);end.setDate(end.getDate()-i*7);
    const start=new Date(end);start.setDate(start.getDate()-6);
    const s0=start.toISOString().slice(0,10),e0=end.toISOString().slice(0,10);
    const label=start.getDate()+'/'+(start.getMonth()+1);
    const wr=reviews.filter(r=>r.f>=s0&&r.f<=e0);
    const a=wr.length>0?wr.reduce((s,r)=>s+r.p,0)/wr.length:null;
    weeks.push({label,count:wr.length,avg:a});
  }
  return weeks;
}
function renderWeekly(reviews){
  const weeks=getWeeks(reviews),W=700,H=200,P={t:10,r:10,b:30,l:35};
  const cw=W-P.l-P.r,ch=H-P.t-P.b,maxC=Math.max(...weeks.map(w=>w.count),1);
  const bw=Math.floor(cw/weeks.length)-4;
  let bars='',lines='',pts='',labels='',ylines='';
  for(let i=0;i<=4;i++){const y=P.t+ch*(1-i/4);ylines+=`<line x1="${P.l}" x2="${W-P.r}" y1="${y}" y2="${y}" stroke="#4a2d1a" stroke-width="0.5"/><text x="${P.l-4}" y="${y+3}" text-anchor="end" font-size="9" fill="#BE986E">${Math.round(maxC*i/4)}</text>`;}
  for(let v=1;v<=5;v++){const y=P.t+ch*(1-(v-1)/4);ylines+=`<text x="${W-P.r+4}" y="${y+3}" text-anchor="start" font-size="9" fill="#F0D6A580">${v}</text>`;}
  weeks.forEach((w,i)=>{
    const x=P.l+i*(cw/weeks.length)+(cw/weeks.length-bw)/2;
    const bh=w.count>0?(w.count/maxC)*ch:0,by=P.t+ch-bh;
    bars+=`<rect x="${x}" y="${by}" width="${bw}" height="${bh}" fill="#E63E00" opacity="0.7" rx="2"><title>${w.label}: ${w.count} reseñas</title></rect>`;
    labels+=`<text x="${x+bw/2}" y="${H-P.b+10}" text-anchor="middle" font-size="8" fill="#BE986E">${w.label}</text>`;
  });
  const lp=weeks.map((w,i)=>{if(w.avg===null)return null;return{x:P.l+i*(cw/weeks.length)+cw/(weeks.length*2),y:P.t+ch*(1-(w.avg-1)/4),w};}).filter(Boolean);
  if(lp.length>1)for(let i=1;i<lp.length;i++)lines+=`<line x1="${lp[i-1].x}" y1="${lp[i-1].y}" x2="${lp[i].x}" y2="${lp[i].y}" stroke="#F0D6A5" stroke-width="1.5" opacity="0.8"/>`;
  lp.forEach(p=>{pts+=`<circle cx="${p.x}" cy="${p.y}" r="3" fill="#F0D6A5"><title>${p.w.avg?p.w.avg.toFixed(2)+'★':''}</title></circle>`;});
  document.getElementById('weekly-chart-container').innerHTML=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:100%;">${ylines}${bars}${lines}${pts}${labels}<line x1="${P.l}" y1="${P.t}" x2="${P.l}" y2="${P.t+ch}" stroke="#4a2d1a" stroke-width="1"/><line x1="${P.l}" y1="${P.t+ch}" x2="${W-P.r}" y2="${P.t+ch}" stroke="#4a2d1a" stroke-width="1"/></svg>`;
}
function renderDist(reviews){
  const dist=[0,0,0,0,0];
  reviews.forEach(r=>{const s=Math.round(r.p)-1;if(s>=0&&s<=4)dist[s]++;});
  const total=dist.reduce((a,b)=>a+b,0)||1;
  const colors=['#C62828','#E63E00','#F9A825','#BE986E','#006445'],labels=['1★','2★','3★','4★','5★'];
  const cx=85,cy=95,ro=70,ri=45;
  let start=0,paths='',legend='';
  dist.forEach((v,i)=>{
    const frac=v/total,angle=frac*2*Math.PI,end=start+angle;
    if(frac<0.001){start=end;return;}
    const x1=cx+ro*Math.sin(start),y1=cy-ro*Math.cos(start),x2=cx+ro*Math.sin(end),y2=cy-ro*Math.cos(end);
    const xi1=cx+ri*Math.sin(start),yi1=cy-ri*Math.cos(start),xi2=cx+ri*Math.sin(end),yi2=cy-ri*Math.cos(end);
    const lg=frac>0.5?1:0,pct=Math.round(frac*100);
    paths+=`<path d="M${xi1},${yi1} L${x1},${y1} A${ro},${ro} 0 ${lg},1 ${x2},${y2} L${xi2},${yi2} A${ri},${ri} 0 ${lg},0 ${xi1},${yi1} Z" fill="${colors[i]}" opacity="0.9"><title>${labels[i]}: ${v} (${pct}%)</title></path>`;
    start=end;
  });
  const avgAll=reviews.length>0?reviews.reduce((s,r)=>s+r.p,0)/reviews.length:0;
  paths+=`<text x="${cx}" y="${cy-6}" text-anchor="middle" font-size="18" font-weight="bold" fill="#F0D6A5">${avgAll.toFixed(1)}</text><text x="${cx}" y="${cy+12}" text-anchor="middle" font-size="10" fill="#BE986E">promedio</text>`;
  dist.forEach((v,i)=>{const pct=Math.round(v/total*100);legend+=`<div style="display:flex;align-items:center;gap:6px;font-size:11px;color:#BE986E;margin-bottom:4px;"><div style="width:10px;height:10px;border-radius:2px;background:${colors[i]};flex-shrink:0;"></div><span>${labels[i]}</span><span style="margin-left:auto;color:#F0D6A5;">${v} (${pct}%)</span></div>`;});
  document.getElementById('dist-chart-container').innerHTML=`<div style="display:flex;align-items:center;gap:16px;width:100%;"><svg viewBox="0 0 170 190" style="width:150px;flex-shrink:0;">${paths}</svg><div style="flex:1;">${legend}</div></div>`;
}
function renderLocales(allRev){
  const locales=['Les Corts','Poblenou','Sagrada Família','Mercat Valencia'],c=document.getElementById('locales-row');
  c.innerHTML='';
  locales.forEach(local=>{
    const rev=allRev.filter(r=>r.l===local),card=document.createElement('div');
    card.className='local-card';
    if(rev.length===0){card.innerHTML=`<div class="local-name">${local}</div><div style="font-size:12px;color:var(--border);text-align:center;padding:12px 0;">Sin datos en el período</div>`;}
    else{const avg=rev.reduce((s,r)=>s+r.p,0)/rev.length,pos=Math.round(rev.filter(r=>r.p>=4).length/rev.length*100),canales=[...new Set(rev.map(r=>r.c))];
    card.innerHTML=`<div class="local-name">${local}</div><div class="local-stat"><span>Reseñas</span><span>${rev.length}</span></div><div class="local-stat"><span>Promedio</span><span>${avg.toFixed(2)}/5</span></div><div class="local-stat"><span>Positivas</span><span>${pos}%</span></div><div class="local-stat"><span>Canales</span><span>${canales.join(', ')}</span></div><div class="stars-bar"><div class="stars-fill" style="width:${avg/5*100}%"></div></div>`;}
    c.appendChild(card);
  });
}
function renderReviews(reviews){
  const sorted=[...reviews].sort((a,b)=>b.f.localeCompare(a.f)),show=sorted.slice(0,50);
  document.getElementById('reviews-shown').textContent=`Mostrando ${show.length} de ${reviews.length}`;
  const c=document.getElementById('reviews-list');c.innerHTML='';
  show.forEach(r=>{
    const stars=Math.round(r.p),sc=stars>=4?'var(--verde)':stars>=3?'var(--amarillo)':'var(--rojo)';
    const d=document.createElement('div');d.className='review-item';
    d.innerHTML=`<div style="font-size:13px;color:${sc};white-space:nowrap;">★${r.p%1===0?r.p.toFixed(0):r.p.toFixed(1)}</div>
      <div class="review-body">${r.t?`<div class="review-text">${r.t.replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>`:'<div style="color:var(--border);font-style:italic;font-size:11px;">Sin comentario</div>'}
      <div style="font-size:11px;color:var(--text-muted);margin-top:3px;">${r.l}</div></div>
      <div class="review-meta"><div class="canal-badge ${r.c==='Google'?'google':'thefork'}">${r.c==='Google'?'🔍 Google':'🍴 TheFork'}</div><div>${r.f}</div></div>`;
    c.appendChild(d);
  });
}
update();
</script>
</body>
</html>"""


def build_html(reviews):
    data = json.dumps({"reviews": reviews, "scraped_at": TODAY}, ensure_ascii=False, separators=(',', ':'))
    total = len(reviews)
    html = HTML_TEMPLATE
    html = html.replace("__TODAY__", TODAY)
    html = html.replace("__TOTAL__", str(total))
    html = html.replace("__DATA__", data)
    return html


def main():
    print(f"=== PAPANATO Dashboard Update — {TODAY} ===")
    reviews = []

    try:
        reviews += scrape_gmaps()
    except Exception as e:
        print(f"Google Maps scrape failed: {e}")

    try:
        reviews += scrape_thefork()
    except Exception as e:
        print(f"TheFork scrape failed: {e}")

    if not reviews:
        print("No reviews scraped, aborting.")
        return

    # Stats
    from collections import defaultdict
    stats = defaultdict(lambda: {"n": 0, "s": 0.0})
    for r in reviews:
        k = (r["l"], r["c"])
        stats[k]["n"] += 1
        stats[k]["s"] += r["p"]
    for k, v in sorted(stats.items()):
        print(f"  {k[0]} | {k[1]}: {v['n']} reviews, avg {v['s']/v['n']:.2f}/5")
    print(f"Total: {len(reviews)}")

    html = build_html(reviews)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html written ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
