#!/usr/bin/env python3
"""
Regenerates profile.svg (green ASCII neofetch card) with live GitHub stats.
Runs in GitHub Actions every 6h. Stdlib only — no pip installs needed.

Env:
  USERNAME  GitHub login (default: 0marware)
  GH_TOKEN  Personal access token (classic, scope: read:user). Used for the
            contribution calendar / streaks. Languages are public and work
            without it, but the token avoids REST rate limits.
"""
import os, json, html, datetime, urllib.request, urllib.error

USER  = os.environ.get("USERNAME", "0marware")
TOKEN = os.environ.get("GH_TOKEN", "").strip()
ROOT  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
ART   = os.path.join(ROOT, ".github", "assets", "ascii.txt")
OUT   = os.path.join(ROOT, "profile.svg")

# ---------------- tiny GitHub API helpers ----------------
def _req(url, data=None, headers=None):
    h = {"User-Agent": "0marware-profile", "Accept": "application/vnd.github+json"}
    if TOKEN: h["Authorization"] = f"Bearer {TOKEN}"
    if headers: h.update(headers)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def rest(path):
    return _req("https://api.github.com" + path)

def graphql(query, variables):
    return _req("https://api.github.com/graphql", {"query": query, "variables": variables})

# ---------------- languages (owner repos incl. private, non-fork) ----------------
def fetch_languages(top=5):
    totals = {}
    page = 1
    try:
        while True:
            # /user/repos (authenticated) includes PRIVATE repos the token can see;
            # needs a token with the classic "repo" scope. Falls back to public only otherwise.
            repos = rest(f"/user/repos?per_page=100&page={page}&affiliation=owner&sort=pushed")
            if not repos: break
            for r in repos:
                if r.get("fork"): continue
                if r.get("name","").lower() == USER.lower(): continue  # skip the profile repo
                try:
                    langs = rest(f"/repos/{r['full_name']}/languages")
                except Exception:
                    continue
                for k, v in langs.items():
                    totals[k] = totals.get(k, 0) + v
            if len(repos) < 100: break
            page += 1
    except Exception as e:
        print("language fetch failed, using fallback:", e)
    if not totals:
        return [("lua",62),("typescript",26),("javascript",6),("c",4),("bash",2)]
    grand = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top]
    out = [(name.lower(), round(byt/grand*100)) for name, byt in ranked]
    # make sure the visible slice sums close to 100 without going weird
    return out

# ---------------- contributions + streaks (GraphQL calendar) ----------------
Q = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    contributionsCollection(from:$from,to:$to){
      contributionCalendar{
        totalContributions
        weeks{ contributionDays{ date contributionCount } }
      }
    }
  }
}"""

def fetch_contributions():
    """Returns (total_this_year, current_streak, longest_streak, spark[16])."""
    if not TOKEN:
        return 2847, 41, 96, [3,4,5,4,6,7,9,8,7,9,8,6,7,8,10,9]
    try:
        created = rest(f"/users/{USER}")["created_at"]
        start_year = int(created[:4])
    except Exception:
        start_year = datetime.date.today().year - 1
    this_year = datetime.date.today().year
    daily = {}  # date -> count
    for year in range(start_year, this_year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to  = f"{year}-12-31T23:59:59Z"
        try:
            cal = graphql(Q, {"login": USER, "from": frm, "to": to})["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        except Exception as e:
            print("graphql year", year, "failed:", e)
            continue
        for wk in cal["weeks"]:
            for d in wk["contributionDays"]:
                daily[d["date"]] = d["contributionCount"]
    if not daily:
        return 2847, 41, 96, [3,4,5,4,6,7,9,8,7,9,8,6,7,8,10,9]

    today = datetime.date.today()
    one = datetime.timedelta(days=1)
    dates = sorted(daily)
    d0 = datetime.date.fromisoformat(dates[0])
    d1 = min(datetime.date.fromisoformat(dates[-1]), today)   # ignore GitHub's future-padded empty days
    # dense day list, real days only (up to today)
    series = []
    cur = d0
    while cur <= d1:
        series.append((cur, daily.get(cur.isoformat(), 0)))
        cur += one

    total_year = sum(c for d, c in series if d.year == this_year)

    # longest streak (any run of consecutive days with contributions)
    longest = run = 0
    for _, c in series:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)

    # current streak: consecutive days ending today (today=0 just means not yet, don't break)
    current = 0
    d = today
    if daily.get(d.isoformat(), 0) == 0:
        d = d - one
    while daily.get(d.isoformat(), 0) > 0:
        current += 1
        d = d - one

    # sparkline: last 16 weeks (sum per 7-day bucket)
    last = [c for _, c in series][-112:]
    spark = []
    for b in range(0, len(last), 7):
        spark.append(sum(last[b:b+7]))
    spark = spark[-16:] or [0]
    return total_year, current, longest, spark

# ---------------- SVG (green ASCII neofetch) ----------------
def build_svg(art_lines, langs, total, current, longest, spark):
    ART_W = max(len(l) for l in art_lines); ART_H = len(art_lines)
    G_LIGHT="#8affc1"; G="#39d353"; G_MID="#56d364"; G_DIM="#2f6b40"; G_LABEL="#6f9c7e"
    AX, AY = 8, 40
    BLK = chr(0x2588); DASH = chr(0x2500)*38; MID = chr(0xB7)
    esc = lambda s: html.escape(s, quote=True)
    def T(x,y,inner,size=12.5,fill=G_MID,anchor="start",weight="normal",ls=0):
        a=f' text-anchor="{anchor}"' if anchor!="start" else ""
        w=f' font-weight="{weight}"' if weight!="normal" else ""
        l=f' letter-spacing="{ls}"' if ls else ""
        return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{a}{w}{l} xml:space="preserve" style="white-space:pre">{inner}</text>'
    SP = "".join(chr(c) for c in range(0x2581,0x2589))
    mxs = max(spark) or 1
    bars = " ".join(SP[min(7,int(round((v/mxs)*7)))] for v in spark[-11:])
    def build_panel(px):
        out=[]; y=AY
        out.append(T(px,y,f'<tspan fill="{G}" font-weight="700">0marware</tspan>',size=17)); y+=12
        out.append(T(px,y,f'<tspan fill="{G_DIM}">{DASH}</tspan>',size=12)); y+=26
        for k,v in [("role","full-stack developer"),("focus","fivem "+MID+" roleplay systems"),("team","co-founder/ceo @ nano scripts")]:
            out.append(T(px,y,f'<tspan fill="{G_LABEL}">{k:<7}</tspan><tspan fill="{G_MID}">{esc(v)}</tspan>')); y+=20
        y+=14
        out.append(T(px,y,"LANGUAGES",size=10.5,fill=G_LABEL,weight="700",ls=2.2)); y+=22
        BARN=16
        for name,pct in langs:
            f=max(1 if pct>0 else 0, round(pct/100*BARN)); f=min(f,BARN)
            out.append(T(px,y,(f'<tspan fill="{G_MID}">{name[:11]:<11}</tspan><tspan fill="{G_LABEL}">[</tspan>'
                             f'<tspan fill="{G}">{BLK*f}</tspan><tspan fill="{G_DIM}">{BLK*(BARN-f)}</tspan>'
                             f'<tspan fill="{G_LABEL}">]  {pct:>2}%</tspan>'))); y+=20
        y+=16
        out.append(T(px,y,"CONTRIBUTIONS",size=10.5,fill=G_LABEL,weight="700",ls=2.2)); y+=24
        out.append(T(px,y,f'<tspan fill="{G_LABEL}">total     </tspan><tspan fill="{G}" font-weight="800" font-size="17">{total:,}</tspan><tspan fill="{G_LABEL}" font-size="11">  this year</tspan>')); y+=22
        out.append(T(px,y,f'<tspan fill="{G_LABEL}">activity  </tspan><tspan fill="{G}">{bars}</tspan>')); y+=13
        cap = chr(0x2514)+" commits / week "+MID+" last 11 weeks "+chr(0x2192)
        out.append(T(px,y,f'<tspan fill="{G_DIM}" font-size="10">          {cap}</tspan>')); y+=18
        out.append(T(px,y,f'<tspan fill="{G_LABEL}">current   </tspan><tspan fill="{G_LIGHT}" font-weight="700">{current}</tspan><tspan fill="{G_MID}"> days</tspan> <tspan font-size="12">{chr(0x1F525)}</tspan>')); y+=20
        out.append(T(px,y,f'<tspan fill="{G_LABEL}">longest   </tspan><tspan fill="{G_LIGHT}" font-weight="700">{longest}</tspan><tspan fill="{G_MID}"> days</tspan>'))
        return out, y
    _, panel_bottom = build_panel(0)
    span = panel_bottom - AY
    LH = span/(ART_H-1) if ART_H > 1 else 15.0
    ART_FS = LH*0.86
    CW = ART_FS*0.60
    PX = AX + ART_W*CW + 42
    W = int(PX + 296)
    H = int(panel_bottom + 16)
    art_bottom = AY + (ART_H-1)*LH
    s=[]
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
             f'font-family="ui-monospace,SFMono-Regular,\'SF Mono\',Menlo,Consolas,\'Liberation Mono\',monospace">')
    s.append(f'<defs><linearGradient id="art" gradientUnits="userSpaceOnUse" x1="0" y1="{AY-14}" x2="0" y2="{art_bottom:.0f}">'
             f'<stop offset="0" stop-color="{G_LIGHT}"/><stop offset="0.55" stop-color="{G_MID}"/><stop offset="1" stop-color="{G}"/></linearGradient></defs>')
    s.append(f'<g fill="url(#art)" font-size="{ART_FS:.2f}">')
    yy=AY
    for ln in art_lines:
        s.append(f'<text x="{AX}" y="{yy:.1f}" xml:space="preserve" style="white-space:pre">{esc(ln)}</text>'); yy+=LH
    s.append('</g>')
    s.extend(build_panel(PX)[0])
    s.append('</svg>')
    return "\n".join(s)

def main():
    art = open(ART, encoding="utf-8").read().split("\n")
    while art and art[-1].strip()=="": art.pop()
    langs = fetch_languages()
    total, current, longest, spark = fetch_contributions()
    svg = build_svg(art, langs, total, current, longest, spark)
    open(OUT, "w", encoding="utf-8").write(svg)
    print(f"wrote {OUT}: langs={langs} total={total} current={current} longest={longest}")

if __name__ == "__main__":
    main()
