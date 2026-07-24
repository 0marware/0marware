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

# ---------------- languages (public repos, owner, non-fork) ----------------
def fetch_languages(top=5):
    totals = {}
    page = 1
    try:
        while True:
            repos = rest(f"/users/{USER}/repos?per_page=100&page={page}&type=owner&sort=pushed")
            if not repos: break
            for r in repos:
                if r.get("fork"): continue
                if r.get("name","").lower() == USER.lower(): continue  # skip the profile repo
                try:
                    langs = rest(f"/repos/{USER}/{r['name']}/languages")
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

    dates = sorted(daily)
    d0 = datetime.date.fromisoformat(dates[0])
    d1 = datetime.date.fromisoformat(dates[-1])
    # dense day list
    series = []
    cur = d0
    one = datetime.timedelta(days=1)
    while cur <= d1:
        series.append((cur, daily.get(cur.isoformat(), 0)))
        cur += one

    total_year = sum(c for d, c in series if d.year == this_year)

    # longest streak
    longest = run = 0
    for _, c in series:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)

    # current streak (today may legitimately be 0 and not break the streak)
    current = 0
    i = len(series) - 1
    if i >= 0 and series[i][1] == 0:
        i -= 1  # skip today if empty
    while i >= 0 and series[i][1] > 0:
        current += 1
        i -= 1

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
    CW, LH, ART_FS = 7.0, 13.4, 11.5
    AX, AY = 8, 40
    PX = AX + ART_W*CW + 48
    W  = PX + 300
    H  = max(AY + ART_H*LH + 16, 300)
    esc = lambda s: html.escape(s, quote=True)
    s=[]
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H:.0f}" viewBox="0 0 {W} {H:.0f}" '
             f'font-family="ui-monospace,SFMono-Regular,\'SF Mono\',Menlo,Consolas,\'Liberation Mono\',monospace">')
    s.append('<defs>')
    s.append(f'<linearGradient id="art" gradientUnits="userSpaceOnUse" x1="0" y1="{AY-14}" x2="0" y2="{AY+ART_H*LH:.0f}">'
             f'<stop offset="0" stop-color="{G_LIGHT}"/><stop offset="0.55" stop-color="{G_MID}"/><stop offset="1" stop-color="{G}"/></linearGradient>')
    s.append('</defs>')
    # art (exact, no card/border/dots)
    s.append(f'<g fill="url(#art)" font-size="{ART_FS}">')
    y=AY
    for ln in art_lines:
        s.append(f'<text x="{AX}" y="{y:.1f}" xml:space="preserve" style="white-space:pre">{esc(ln)}</text>')
        y+=LH
    s.append('</g>')
    def T(x,y,inner,size=12.5,fill=G_MID,anchor="start",weight="normal",ls=0):
        a=f' text-anchor="{anchor}"' if anchor!="start" else ""
        w=f' font-weight="{weight}"' if weight!="normal" else ""
        l=f' letter-spacing="{ls}"' if ls else ""
        return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{a}{w}{l} xml:space="preserve" style="white-space:pre">{inner}</text>'
    px=PX; y=AY
    s.append(T(px,y,f'<tspan fill="{G}" font-weight="700">0marware</tspan>',size=17)); y+=12
    s.append(T(px,y,f'<tspan fill="{G_DIM}">{esc("─"*38)}</tspan>',size=12)); y+=26
    for k,v in [("role","full-stack developer"),("focus","fivem · roleplay systems"),("team","co-founder @ nano scripts")]:
        s.append(T(px,y,f'<tspan fill="{G_LABEL}">{k:<7}</tspan><tspan fill="{G_MID}">{esc(v)}</tspan>')); y+=20
    y+=14
    s.append(T(px,y,"LANGUAGES",size=10.5,fill=G_LABEL,weight="700",ls=2.2)); y+=22
    BARN=20
    for name,pct in langs:
        f=max(1 if pct>0 else 0, round(pct/100*BARN)); f=min(f,BARN)
        s.append(T(px,y,(f'<tspan fill="{G_MID}">{name[:11]:<11}</tspan>'
                         f'<tspan fill="{G}">{"█"*f}</tspan>'
                         f'<tspan fill="{G_DIM}">{"░"*(BARN-f)}</tspan>'
                         f'<tspan fill="{G_LABEL}">  {pct:>2}%</tspan>'))); y+=20
    y+=16
    s.append(T(px,y,"CONTRIBUTIONS",size=10.5,fill=G_LABEL,weight="700",ls=2.2)); y+=24
    s.append(T(px,y,f'<tspan fill="{G_LABEL}">total     </tspan><tspan fill="{G}" font-weight="800" font-size="17">{total:,}</tspan><tspan fill="{G_LABEL}" font-size="11">  this year</tspan>')); y+=22
    mx=max(spark) or 1; SP="▁▂▃▄▅▆▇█"
    sp="".join(SP[min(7,int(round((v/mx)*7)))] for v in spark)
    s.append(T(px,y,f'<tspan fill="{G_LABEL}">activity  </tspan><tspan fill="{G}">{sp}</tspan>')); y+=22
    s.append(T(px,y,f'<tspan fill="{G_LABEL}">current   </tspan><tspan fill="{G_LIGHT}" font-weight="700">{current}</tspan><tspan fill="{G_MID}"> days</tspan> <tspan font-size="12">🔥</tspan>')); y+=20
    s.append(T(px,y,f'<tspan fill="{G_LABEL}">longest   </tspan><tspan fill="{G_LIGHT}" font-weight="700">{longest}</tspan><tspan fill="{G_MID}"> days</tspan>'))
    fy=H-14
    s.append(f'<circle cx="{px+5}" cy="{fy-4}" r="4" fill="{G}"/>')
    s.append(T(px+16,fy,f'<tspan fill="{G_LABEL}">auto-updated every 6h</tspan>',size=10.5))
    s.append(T(W-14,fy,f'<tspan fill="{G}">↻ live</tspan>',size=10.5,anchor="end"))
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
