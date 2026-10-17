"""
FloodConnect v2 - integrated multi-hazard travel safety & disaster-response platform.
Run locally:  streamlit run app.py      (needs .streamlit/secrets.toml with DB_URL)
"""
import html
import os

import pandas as pd
import pydeck as pdk
import streamlit as st

import core
import services
import store

st.set_page_config(page_title="FloodConnect", page_icon="\U0001F30A", layout="wide", initial_sidebar_state="expanded")
esc = lambda x: html.escape("" if x is None else str(x))

# optional email settings from Streamlit secrets -> environment (used by store.send_email)
try:
    for _k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM"):
        if _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

# ================================================================== DESIGN
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1180px; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

.fc-hero { background: linear-gradient(135deg,#0B1F3A 0%,#1D4ED8 55%,#06B6D4 100%); color:#fff; border-radius:24px;
  padding:34px 40px; box-shadow:0 18px 44px rgba(13,42,92,.28); margin-bottom:22px; position:relative; overflow:hidden; }
.fc-hero:after { content:""; position:absolute; right:-60px; top:-60px; width:260px; height:260px; border-radius:50%;
  background:radial-gradient(circle,rgba(255,255,255,.22),rgba(255,255,255,0) 70%); }
.fc-hero h1 { font-size:2.15rem; font-weight:800; margin:0 0 6px; color:#fff; letter-spacing:-.5px; }
.fc-hero p { margin:0; font-size:1.02rem; opacity:.92; max-width:720px; line-height:1.55; }
.fc-pagehead h2 { font-size:1.65rem; font-weight:800; color:#0B1F3A; margin:0; letter-spacing:-.3px; }
.fc-pagehead p { color:#5B6B82; margin:2px 0 18px; }

.fc-card { background:#fff; border:1px solid #E3E9F3; border-radius:18px; padding:18px 22px;
  box-shadow:0 6px 18px rgba(15,23,42,.05); margin-bottom:14px; }
.fc-card h4 { margin:0 0 6px; font-size:1.02rem; color:#0B1F3A; font-weight:700; }
.fc-muted { color:#64748B; font-size:.86rem; }
.fc-metric { background:#fff; border:1px solid #E3E9F3; border-radius:18px; padding:16px 20px; box-shadow:0 6px 18px rgba(15,23,42,.05); }
.fc-metric .v { font-size:1.9rem; font-weight:800; color:#0B1F3A; line-height:1.1; }
.fc-metric .l { font-size:.8rem; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:.6px; }
.fc-metric .h { font-size:.8rem; color:#2563EB; margin-top:2px; }

.fc-badge { display:inline-block; padding:3px 11px; border-radius:999px; font-size:.72rem; font-weight:700; color:#fff; letter-spacing:.3px; vertical-align:middle; }
.fc-chip { display:inline-block; padding:4px 11px; border-radius:10px; font-size:.78rem; font-weight:600; background:#EEF3FB; color:#1E3A8A; margin:2px 6px 2px 0; }
.fc-bar { height:11px; background:#E8EEF7; border-radius:999px; overflow:hidden; margin:8px 0 4px; }
.fc-bar > div { height:100%; border-radius:999px; }

.fc-banner { border-radius:20px; padding:22px 28px; color:#fff; margin:6px 0 16px; box-shadow:0 12px 30px rgba(15,23,42,.18); }
.fc-banner .big { font-size:1.65rem; font-weight:800; letter-spacing:-.3px; }
.fc-banner .sub { opacity:.95; margin-top:4px; font-size:.98rem; }

.fc-alert { border-left:6px solid #94A3B8; background:#fff; border-radius:14px; padding:14px 18px; margin-bottom:10px;
  border-top:1px solid #E3E9F3; border-right:1px solid #E3E9F3; border-bottom:1px solid #E3E9F3; box-shadow:0 4px 12px rgba(15,23,42,.04); }
.fc-alert .t { font-weight:700; color:#0B1F3A; }
.fc-alert .m { color:#475569; font-size:.9rem; margin-top:3px; }

.fc-brand { padding:6px 4px 14px; }
.fc-brand .n { font-size:1.35rem; font-weight:800; color:#0B1F3A; letter-spacing:-.4px; }
.fc-brand .t { font-size:.78rem; color:#64748B; }
.fc-user { background:#F1F5FD; border-radius:14px; padding:10px 14px; margin:10px 0 6px; }
.fc-user .n { font-weight:700; color:#0B1F3A; font-size:.92rem; }

section[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid #E3E9F3; }
section[data-testid="stSidebar"] div[role="radiogroup"] { gap:2px; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label { padding:9px 12px; border-radius:12px; width:100%; transition:background .15s; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover { background:#F1F5FD; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child { display:none; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) { background:#E5EEFF; }
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p { color:#1D4ED8; font-weight:700; }

.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button { border-radius:12px; font-weight:600; }
.stTabs [data-baseweb="tab-list"] { gap:6px; border-bottom:1px solid #E3E9F3; }
.stTabs [data-baseweb="tab"] { border-radius:10px 10px 0 0; padding:8px 16px; font-weight:600; }
div[data-testid="stForm"] { border:1px solid #E3E9F3; border-radius:18px; background:#fff; padding:20px; box-shadow:0 6px 18px rgba(15,23,42,.04); }
.fc-foot { text-align:center; color:#94A3B8; font-size:.78rem; margin-top:34px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ================================================================ HELPERS
def badge(text, color):
    return f'<span class="fc-badge" style="background:{color}">{esc(text)}</span>'


def head(title, sub=""):
    st.markdown(f'<div class="fc-pagehead"><h2>{esc(title)}</h2><p>{esc(sub)}</p></div>', unsafe_allow_html=True)


def metric(col, label, value, hint=""):
    col.markdown(f'<div class="fc-metric"><div class="l">{esc(label)}</div><div class="v">{esc(value)}</div>'
                 f'<div class="h">{esc(hint)}</div></div>', unsafe_allow_html=True)


def alert_card(row):
    lvl = core.SEVERITY_TO_LEVEL.get(row["severity"], 0)
    color = core.LEVEL_COLORS[lvl]
    where = row["zone"] if isinstance(row["zone"], str) else "All monitored zones"
    src = {"manual": "Official / coordinator", "weather": "Live weather", "earthquake": "Live earthquake data"}.get(row["source"], row["source"])
    st.markdown(
        f'<div class="fc-alert" style="border-left-color:{color}"><div class="t">{badge(row["severity"].upper(), color)} &nbsp;{esc(row["title"])}</div>'
        f'<div class="m">{esc(row["message"])}</div><div class="fc-muted" style="margin-top:6px">{esc(where)} \u00b7 {esc(src)} \u00b7 {esc(str(row["created_at"])[:16])}</div></div>',
        unsafe_allow_html=True)


@st.cache_resource
def get_engine():
    return store.make_engine(st.secrets["DB_URL"])


@st.cache_data(ttl=20, show_spinner=False)
def cdf(sql, params=()):
    return store.df(get_engine(), sql, dict(params))


def refresh():
    st.cache_data.clear()


@st.cache_data(ttl=600, show_spinner=False)
def cached_quakes():
    return services.recent_quakes()


@st.cache_data(ttl=600, show_spinner=False)
def cached_forecast(lat, lon):
    return services.forecast(round(lat, 3), round(lon, 3))


def zones_df():
    return cdf("SELECT z.zone_id, z.name, z.region, z.hazard_type, z.risk_level, z.latitude, z.longitude, z.notes, c.name AS country "
               "FROM Zone z JOIN Country c ON c.country_id = z.country_id ORDER BY c.name, z.name")


def me():
    return st.session_state.get("user")


def role():
    u = me()
    return u["role"] if u else None


def go(page):
    st.session_state["nav"] = page


def need(permission):
    """Gate a page. Returns True if allowed; otherwise renders a friendly message."""
    if not me():
        st.info("Please sign in to use this section.")
        st.button("Sign in / Create account", on_click=go, args=("\U0001F510 Sign in",), key=f"need_{permission}")
        return False
    if not core.can(role(), permission):
        st.warning("Your account role does not have access to this section.")
        return False
    return True


# ===================================================================== PAGES
def page_home():
    st.markdown('<div class="fc-hero"><h1>\U0001F30A Travel safer. Respond faster.</h1>'
                '<p>FloodConnect brings live weather and earthquake signals, hazard zones, shelter capacity, community reports and '
                'volunteer coordination together for India and Japan \u2014 in one place.</p></div>', unsafe_allow_html=True)
    z = zones_df()
    sh = cdf("SELECT total_capacity, current_occupancy FROM Shelter")
    al = store.active_alerts(get_engine())
    rp = cdf("SELECT COUNT(*) AS n FROM HazardReport WHERE status = 'verified'")["n"].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    metric(c1, "Zones monitored", len(z), f"{z['country'].nunique()} countries")
    metric(c2, "Shelter spaces free", int((sh["total_capacity"] - sh["current_occupancy"]).sum()), f"of {int(sh['total_capacity'].sum())} total")
    metric(c3, "Active alerts", len(al), "live + official")
    metric(c4, "Verified field reports", int(rp), "community-sourced")
    st.write("")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### \U0001F6A8 Active alerts")
        if me():
            watched = store.watched_zone_ids(get_engine(), me()["user_id"])
            if watched:
                st.caption("Showing alerts for the zones you watch, plus region-wide alerts.")
                al = al[al["zone_id"].isin(watched) | al["zone_id"].isna()]
        if al.empty:
            st.markdown('<div class="fc-card">\u2705 No active alerts right now.</div>', unsafe_allow_html=True)
        for _, r in al.head(5).iterrows():
            alert_card(r)
    with right:
        st.markdown("#### \U0001F9ED Plan a trip")
        st.markdown('<div class="fc-card"><h4>Check before you go</h4><div class="fc-muted">Search any destination to get a live risk rating, '
                    'forecast, nearby shelters and precautions.</div></div>', unsafe_allow_html=True)
        st.button("Check my trip \u2192", on_click=go, args=("\U0001F9ED Plan a Trip",), type="primary", key="home_trip")
        if not me():
            st.markdown('<div class="fc-card"><h4>Join your community</h4><div class="fc-muted">Create a free account to report hazards, '
                        'follow zones and receive alerts.</div></div>', unsafe_allow_html=True)
            st.button("Sign in / Create account", on_click=go, args=("\U0001F510 Sign in",), key="home_login")


def assess_trip(lat, lon, label, country_hint=None):
    z = zones_df().copy()
    z["distance_km"] = z.apply(lambda r: core.haversine(lat, lon, r["latitude"], r["longitude"]), axis=1)
    z = z.sort_values("distance_km")
    near = z[z["distance_km"] <= 150]
    nearest = near.iloc[0] if not near.empty else None
    zc = core.zone_component(nearest["risk_level"], nearest["distance_km"]) if nearest is not None else 0

    fc = cached_forecast(lat, lon)
    rain = wind = None
    wl = wnl = 0
    if fc:
        rain = max([x for x in fc["rain_mm"] if x is not None] or [0])
        wind = max([x for x in fc["wind_kmh"] if x is not None] or [0])
        wl, wnl = core.classify_rain(rain), core.classify_wind(wind)

    qs = services.quakes_near(cached_quakes(), lat, lon, 300)
    ql, topq = 0, None
    for q in qs:
        lv = core.classify_quake(q["mag"], q["distance_km"])
        if lv > ql or (topq is None and lv == ql):
            ql, topq = lv, q

    al_level, alerts = 0, pd.DataFrame()
    if nearest is not None:
        a = store.active_alerts(get_engine(), [int(nearest["zone_id"])])
        alerts = a[a["zone_id"].notna()]
        if not alerts.empty:
            al_level = max(core.SEVERITY_TO_LEVEL[s] for s in alerts["severity"])

    overall = core.combine_risk(zc, max(wl, wnl), ql, al_level)
    hazard = nearest["hazard_type"] if nearest is not None else None
    shelters = pd.DataFrame()
    if nearest is not None:
        shelters = cdf("SELECT name, total_capacity, current_occupancy, contact FROM Shelter WHERE zone_id = :z",
                       (("z", int(nearest["zone_id"])),))
    country = nearest["country"] if nearest is not None else (country_hint if country_hint in core.EMERGENCY else None)
    return dict(label=label, lat=lat, lon=lon, nearest=nearest, near=near.head(3), zc=zc, fc=fc, rain=rain, wind=wind, wl=wl, wnl=wnl,
                topq=topq, ql=ql, alerts=alerts, al_level=al_level, overall=overall, hazard=hazard, shelters=shelters, country=country)


def render_trip(r):
    lvl = r["overall"]
    color = core.LEVEL_COLORS[lvl]
    icon = ["\u2705", "\u26A0\uFE0F", "\U0001F7E0", "\U0001F6A8"][lvl]
    headline = {0: "Looks fine for travel", 1: "Travel with care", 2: "High risk \u2014 reconsider or prepare well",
                3: "Severe risk \u2014 avoid non-essential travel"}[lvl]
    st.markdown(f'<div class="fc-banner" style="background:linear-gradient(135deg,{color},{color}CC)"><div class="big">{icon} {core.LEVELS[lvl]} risk \u2014 {esc(r["label"])}</div>'
                f'<div class="sub">{headline}</div></div>', unsafe_allow_html=True)

    n = r["nearest"]
    chips = []
    if n is not None:
        chips.append(f'Nearest zone: {esc(n["name"])}, {esc(n["region"])} ({n["distance_km"]:.0f} km) \u00b7 {esc(n["hazard_type"])} \u00b7 {esc(n["risk_level"])}')
    else:
        chips.append("No monitored hazard zone within 150 km")
    if r["fc"]:
        chips.append(f'Forecast: up to {r["rain"]:.0f} mm rain/day \u00b7 winds up to {r["wind"]:.0f} km/h')
    else:
        chips.append("Live forecast unavailable (showing static risk only)")
    if r["topq"]:
        chips.append(f'Recent quake M{r["topq"]["mag"]:.1f}, {r["topq"]["distance_km"]:.0f} km away')
    if not r["alerts"].empty:
        chips.append(f'{len(r["alerts"])} active alert(s) in this zone')
    st.markdown('<div class="fc-card"><h4>Why this rating</h4>' + "".join(f'<span class="fc-chip">{c}</span>' for c in chips) + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        items = core.precautions_for(r["hazard"], r["wl"], r["wnl"], r["ql"])
        st.markdown('<div class="fc-card"><h4>\U0001F9F3 Precautions for your trip</h4>' + "".join(f"<div style='margin:6px 0'>\u2610 &nbsp;{esc(i)}</div>" for i in items) + "</div>", unsafe_allow_html=True)
        if r["fc"]:
            fdf = pd.DataFrame({"Date": r["fc"]["dates"], "Rain (mm)": r["fc"]["rain_mm"], "Max wind (km/h)": r["fc"]["wind_kmh"]})
            st.markdown("**3-day forecast**")
            st.dataframe(fdf, hide_index=True, width="stretch")
    with c2:
        em = core.EMERGENCY.get(r["country"]) if r["country"] else None
        if em is None:
            em = [f"{k}: " + " / ".join(v) for k, v in core.EMERGENCY.items()]
            body = "".join(f"<div style='margin:4px 0'>{esc(x)}</div>" for x in em)
        else:
            body = "".join(f"<div style='margin:4px 0'>\U0001F4DE {esc(x)}</div>" for x in em)
        st.markdown(f'<div class="fc-card"><h4>Emergency numbers</h4>{body}<div class="fc-muted" style="margin-top:6px">Verify local numbers before travel.</div></div>', unsafe_allow_html=True)
        if not r["shelters"].empty:
            body = ""
            for _, s in r["shelters"].iterrows():
                free = int(s["total_capacity"] - s["current_occupancy"])
                st_ = core.shelter_status(s["current_occupancy"], s["total_capacity"])
                col = {"Available": "#16A34A", "Filling fast": "#F59E0B", "Full": "#DC2626"}.get(st_, "#64748B")
                body += f'<div style="margin:8px 0"><b>{esc(s["name"])}</b> {badge(st_, col)}<div class="fc-muted">{free} spaces free \u00b7 {esc(s["contact"])}</div></div>'
            st.markdown(f'<div class="fc-card"><h4>\U0001F3E0 Nearby shelters</h4>{body}</div>', unsafe_allow_html=True)
        if n is not None and me():
            watched = int(n["zone_id"]) in store.watched_zone_ids(get_engine(), me()["user_id"])
            if st.button("\u2605 Stop watching this zone" if watched else "\u2606 Watch this zone for alerts", key="watch_btn"):
                on = store.toggle_watch(get_engine(), me()["user_id"], int(n["zone_id"]))
                refresh()
                st.toast("You will now see (and be emailed, if enabled) alerts for this zone." if on else "Zone removed from your watchlist.")
                st.rerun()
        elif n is not None:
            st.caption("Sign in to watch this zone and get its alerts.")


def page_trip():
    head("Plan a Trip", "Search a destination or pick a monitored zone for a live safety check.")
    ss = st.session_state
    tab1, tab2, tab3 = st.tabs(["\U0001F50E Search a place", "\U0001F4CD Monitored zones", "\U0001F9ED Coordinates"])
    with tab1:
        q = st.text_input("Destination", placeholder="e.g. Kochi, Osaka, Shimla", key="trip_q")
        if st.button("Search", key="trip_search") and q.strip():
            res = services.geocode(q.strip())
            ss["geo_results"] = res
        res = ss.get("geo_results")
        if res is None and "geo_results" in ss:
            st.warning("Place search is unavailable right now. Use the Monitored zones or Coordinates tab.")
        elif res is not None and len(res) == 0:
            st.info("No places found. Try another spelling.")
        elif res:
            labels = [r["label"] for r in res]
            pick = st.selectbox("Select the exact place", labels, key="trip_pick")
            if st.button("Use this place", key="trip_use_search"):
                r = res[labels.index(pick)]
                ss["trip_loc"] = dict(label=r["label"], lat=r["lat"], lon=r["lon"], country=r.get("country"))
    with tab2:
        z = zones_df()
        names = [f"{r['name']} ({r['region']}, {r['country']})" for _, r in z.iterrows()]
        pick = st.selectbox("Monitored zone", names, key="trip_zone")
        if st.button("Use this zone", key="trip_use_zone"):
            r = z.iloc[names.index(pick)]
            ss["trip_loc"] = dict(label=f"{r['name']}, {r['region']}", lat=float(r["latitude"]), lon=float(r["longitude"]), country=r["country"])
    with tab3:
        a, b = st.columns(2)
        lat = a.number_input("Latitude", value=13.0827, min_value=-90.0, max_value=90.0, format="%.4f", key="trip_lat")
        lon = b.number_input("Longitude", value=80.2707, min_value=-180.0, max_value=180.0, format="%.4f", key="trip_lon")
        if st.button("Use these coordinates", key="trip_use_coord"):
            ss["trip_loc"] = dict(label=f"{lat:.3f}, {lon:.3f}", lat=lat, lon=lon, country=None)

    loc = ss.get("trip_loc")
    if loc:
        st.markdown(f'<div class="fc-card">\U0001F4CD <b>Selected:</b> {esc(loc["label"])} <span class="fc-muted">({loc["lat"]:.3f}, {loc["lon"]:.3f})</span></div>', unsafe_allow_html=True)
        if st.button("\U0001F50D Check trip risk", type="primary", key="trip_check"):
            with st.spinner("Checking hazard zones, live forecast and earthquake feed\u2026"):
                res = assess_trip(loc["lat"], loc["lon"], loc["label"], loc.get("country"))
            ss["trip_result"] = res
            try:
                zid = int(res["nearest"]["zone_id"]) if res["nearest"] is not None else None
                store.log_advisory(get_engine(), me()["user_id"] if me() else None, loc["lat"], loc["lon"], zid,
                                   core.LEVELS[res["overall"]], f"{res['label']} | hazard={res['hazard']}")
            except Exception:
                pass
    else:
        st.info("Choose a destination above to begin.")
    if ss.get("trip_result"):
        render_trip(ss["trip_result"])


def page_map():
    head("Hazard Map", "Colour shows the current level: static zone risk raised by any active alert.")
    z = zones_df().copy()
    al = store.active_alerts(get_engine())
    boost = {int(k): max(core.SEVERITY_TO_LEVEL[s] for s in g["severity"]) for k, g in al[al["zone_id"].notna()].groupby("zone_id")}
    z["level"] = z.apply(lambda r: max(core.static_level(r["risk_level"]), boost.get(int(r["zone_id"]), 0)), axis=1)
    c1, c2, c3 = st.columns(3)
    country = c1.selectbox("Country", ["All"] + sorted(z["country"].unique().tolist()))
    hazard = c2.selectbox("Hazard", ["All"] + sorted(z["hazard_type"].unique().tolist()))
    lvl = c3.selectbox("Minimum level", core.LEVELS)
    f = z.copy()
    if country != "All":
        f = f[f["country"] == country]
    if hazard != "All":
        f = f[f["hazard_type"] == hazard]
    f = f[f["level"] >= core.LEVELS.index(lvl)]
    if f.empty:
        st.info("No zones match these filters.")
        return
    hexrgb = lambda h: [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    f["color"] = f["level"].map(lambda l: hexrgb(core.LEVEL_COLORS[l]) + [210])
    f["level_name"] = f["level"].map(lambda l: core.LEVELS[l])
    f["lon"], f["lat"] = f["longitude"], f["latitude"]
    view = pdk.ViewState(latitude=float(f["lat"].mean()), longitude=float(f["lon"].mean()), zoom=3.2 if country == "All" else 4.6)
    layer = pdk.Layer("ScatterplotLayer", data=f, get_position="[lon, lat]", get_fill_color="color", get_radius=28000,
                      pickable=True, stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=2, radius_min_pixels=7)
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, map_provider="carto", map_style="light",
                             tooltip={"html": "<b>{name}</b>, {region}<br/>{hazard_type} \u00b7 {level_name}<br/><i>{notes}</i>"}), height=470)
    st.markdown("".join(badge(core.LEVELS[i], core.LEVEL_COLORS[i]) + " &nbsp;" for i in range(4)), unsafe_allow_html=True)
    st.write("")
    show = f[["name", "country", "region", "hazard_type", "risk_level", "level_name", "notes"]].rename(
        columns={"name": "Zone", "country": "Country", "region": "Region", "hazard_type": "Hazard", "risk_level": "Base risk", "level_name": "Current level", "notes": "Notes"})
    st.dataframe(show, hide_index=True, width="stretch")


def page_shelters():
    head("Shelters", "Live occupancy so evacuees go where there is space.")
    s = cdf("SELECT s.shelter_id, s.name, s.total_capacity, s.current_occupancy, s.contact, s.last_updated, z.name AS zone, c.name AS country "
            "FROM Shelter s JOIN Zone z ON z.zone_id = s.zone_id JOIN Country c ON c.country_id = z.country_id")
    c1, c2 = st.columns(2)
    country = c1.selectbox("Country", ["All"] + sorted(s["country"].unique().tolist()), key="sh_c")
    only_free = c2.checkbox("Only show shelters with space", key="sh_free")
    if country != "All":
        s = s[s["country"] == country]
    s = s.assign(free=s["total_capacity"] - s["current_occupancy"])
    if only_free:
        s = s[s["free"] > 0]
    s = s.sort_values("free", ascending=False)
    if s.empty:
        st.info("No shelters match.")
    cols = st.columns(2)
    for i, (_, r) in enumerate(s.iterrows()):
        pct = r["current_occupancy"] / r["total_capacity"]
        stt = core.shelter_status(r["current_occupancy"], r["total_capacity"])
        col = {"Available": "#16A34A", "Filling fast": "#F59E0B", "Full": "#DC2626"}.get(stt, "#64748B")
        cols[i % 2].markdown(
            f'<div class="fc-card"><h4>{esc(r["name"])} &nbsp;{badge(stt, col)}</h4><div class="fc-muted">{esc(r["zone"])}, {esc(r["country"])}</div>'
            f'<div class="fc-bar"><div style="width:{min(pct, 1) * 100:.0f}%;background:{col}"></div></div>'
            f'<div><b>{int(r["current_occupancy"])}</b> / {int(r["total_capacity"])} occupied \u00b7 <b>{int(r["free"])}</b> free</div>'
            f'<div class="fc-muted" style="margin-top:4px">\U0001F4DE {esc(r["contact"])} \u00b7 updated {esc(str(r["last_updated"])[:16])}</div></div>', unsafe_allow_html=True)


def page_alerts():
    head("Alerts", "Official notices plus automatic live weather and earthquake alerts.")
    al = store.active_alerts(get_engine())
    c1, c2 = st.columns(2)
    sev = c1.multiselect("Severity", list(core.SEVERITY_TO_LEVEL), default=list(core.SEVERITY_TO_LEVEL))
    src = c2.multiselect("Source", ["manual", "weather", "earthquake"], default=["manual", "weather", "earthquake"])
    al = al[al["severity"].isin(sev) & al["source"].isin(src)]
    if al.empty:
        st.markdown('<div class="fc-card">\u2705 No active alerts match your filters.</div>', unsafe_allow_html=True)
    for _, r in al.iterrows():
        alert_card(r)
    with st.expander("Shelter capacity events"):
        sa = cdf("SELECT sa.triggered_at, s.name AS shelter, sa.message FROM ShelterAlert sa JOIN Shelter s ON s.shelter_id = sa.shelter_id ORDER BY sa.triggered_at DESC LIMIT 25")
        st.dataframe(sa, hide_index=True, width="stretch") if len(sa) else st.caption("No shelter-full events yet.")


def page_report():
    head("Report a Hazard", "Help your community: describe what you see. A coordinator will review it.")
    if not need("report_hazard"):
        return
    z = zones_df()
    with st.form("report_form", clear_on_submit=True):
        names = [f"{r['name']} ({r['country']})" for _, r in z.iterrows()]
        zone = st.selectbox("Zone", names)
        a, b = st.columns(2)
        cat = a.selectbox("What is it?", ["Flooded road", "Bridge / structure damage", "Landslide / blocked road", "Power line down", "Shelter problem", "Other"])
        sev = b.select_slider("How serious?", options=["Minor", "Serious", "Dangerous"], value="Serious")
        desc = st.text_area("Describe what you observed", max_chars=1000, placeholder="Where exactly? Water depth? Is the road passable?")
        contact = st.text_input("Phone (optional, only shown to coordinators)")
        ok = st.form_submit_button("Submit report", type="primary")
    if ok:
        zid = int(z.iloc[names.index(zone)]["zone_id"])
        good, res = store.submit_report(get_engine(), me()["user_id"], zid, cat, {"Minor": 1, "Serious": 2, "Dangerous": 3}[sev], desc, contact or None)
        if good:
            refresh()
            st.success("Thank you \u2014 your report was submitted and is awaiting review.")
        else:
            st.error(res)
    st.markdown("#### My reports")
    mine = store.df(get_engine(), "SELECT r.reported_at, z.name AS zone, r.category, r.severity, r.status, r.description FROM HazardReport r "
                                  "JOIN Zone z ON z.zone_id = r.zone_id WHERE r.user_id = :u ORDER BY r.reported_at DESC LIMIT 20", {"u": me()["user_id"]})
    st.dataframe(mine, hide_index=True, width="stretch") if len(mine) else st.caption("You have not submitted any reports yet.")


def page_resources():
    head("Resources & Volunteers", "Relief inventory and who is deployed where.")
    if not need("view_resources"):
        return
    t1, t2 = st.tabs(["\U0001F4E6 Resources", "\U0001F9D1\u200D\U0001F91D\u200D\U0001F9D1 Volunteers"])
    t1.dataframe(cdf("SELECT type AS \"Type\", quantity AS \"Quantity\", location AS \"Location\", status AS \"Status\" FROM Resource ORDER BY type"), hide_index=True, width="stretch")
    t2.dataframe(cdf("SELECT v.name AS \"Volunteer\", v.skill AS \"Skill\", z.name AS \"Assigned zone\", v.contact AS \"Contact\" FROM Volunteer v "
                     "LEFT JOIN Zone z ON z.zone_id = v.assigned_zone_id ORDER BY v.name"), hide_index=True, width="stretch")


def page_my_tasks():
    head("My Tasks", "Tasks assigned to you by coordinators.")
    if not need("my_tasks"):
        return
    t = store.df(get_engine(), "SELECT t.task_id, t.title, t.description, t.status, z.name AS zone, r.type AS resource, t.created_at "
                               "FROM Task t JOIN Volunteer v ON v.volunteer_id = t.volunteer_id LEFT JOIN Zone z ON z.zone_id = t.zone_id "
                               "LEFT JOIN Resource r ON r.resource_id = t.resource_id WHERE v.user_id = :u ORDER BY t.created_at DESC", {"u": me()["user_id"]})
    if t.empty:
        st.markdown('<div class="fc-card">\U0001F389 No tasks assigned right now. A coordinator can register you as a volunteer and assign work.</div>', unsafe_allow_html=True)
        return
    colors = {"assigned": "#2563EB", "in_progress": "#F59E0B", "done": "#16A34A", "cancelled": "#94A3B8"}
    for _, r in t.iterrows():
        st.markdown(f'<div class="fc-card"><h4>{esc(r["title"])} &nbsp;{badge(r["status"].replace("_", " "), colors[r["status"]])}</h4>'
                    f'<div>{esc(r["description"])}</div><div class="fc-muted">Zone: {esc(r["zone"])} \u00b7 Resource: {esc(r["resource"] or "\u2014")}</div></div>', unsafe_allow_html=True)
        c1, c2 = st.columns([2, 1])
        new = c1.selectbox("Status", ["assigned", "in_progress", "done", "cancelled"], index=["assigned", "in_progress", "done", "cancelled"].index(r["status"]),
                           key=f"ts_{r['task_id']}", label_visibility="collapsed")
        if c2.button("Update", key=f"tu_{r['task_id']}"):
            store.update_task(get_engine(), me()["user_id"], int(r["task_id"]), new)
            refresh()
            st.rerun()


def page_coord():
    head("Coordinator Desk", "Manage shelters, review reports, publish alerts and assign work.")
    if not need("manage_shelters"):
        return
    eng = get_engine()
    t1, t2, t3, t4 = st.tabs(["\U0001F3E0 Shelters", "\U0001F9FE Reports", "\U0001F4E3 Alerts", "\U0001F9D1\u200D\U0001F91D\u200D\U0001F9D1 Volunteers & Tasks"])

    with t1:
        s = store.df(eng, "SELECT s.shelter_id, s.name, s.total_capacity, s.current_occupancy, z.name AS zone FROM Shelter s JOIN Zone z ON z.zone_id = s.zone_id ORDER BY s.name")
        names = [f"{r['name']} \u2014 {r['zone']}" for _, r in s.iterrows()]
        pick = st.selectbox("Shelter", names, key="cs_pick")
        row = s.iloc[names.index(pick)]
        occ = st.number_input(f"Current occupancy (capacity {int(row['total_capacity'])})", min_value=0, max_value=int(row["total_capacity"]),
                              value=int(row["current_occupancy"]), key=f"cs_occ_{row['shelter_id']}")
        if st.button("Save occupancy", type="primary", key="cs_save"):
            ok, msg = store.update_shelter(eng, me()["user_id"], int(row["shelter_id"]), int(occ))
            refresh()
            st.success("Saved. If the shelter is now full, a capacity alert was recorded automatically.") if ok else st.error(msg)

    with t2:
        if not core.can(role(), "moderate_reports"):
            st.warning("No access.")
        else:
            p = store.df(eng, "SELECT r.report_id, r.reported_at, z.name AS zone, r.category, r.severity, r.description, r.reporter_contact, u.name AS reporter "
                              "FROM HazardReport r JOIN Zone z ON z.zone_id = r.zone_id LEFT JOIN AppUser u ON u.user_id = r.user_id "
                              "WHERE r.status = 'pending' ORDER BY r.severity DESC, r.reported_at LIMIT 25")
            st.caption(f"{len(p)} report(s) awaiting review (most serious first).")
            for _, r in p.iterrows():
                sevc = core.LEVEL_COLORS[int(r["severity"])]
                st.markdown(f'<div class="fc-card"><h4>{esc(r["category"])} \u2014 {esc(r["zone"])} &nbsp;{badge("severity " + str(int(r["severity"])), sevc)}</h4>'
                            f'<div>{esc(r["description"])}</div><div class="fc-muted">By {esc(r["reporter"] or "guest")} \u00b7 {esc(r["reporter_contact"] or "no contact")} \u00b7 {esc(str(r["reported_at"])[:16])}</div></div>', unsafe_allow_html=True)
                a, b, _ = st.columns([1, 1, 4])
                if a.button("\u2705 Verify", key=f"v_{r['report_id']}"):
                    store.review_report(eng, int(r["report_id"]), me()["user_id"], "verified"); refresh(); st.rerun()
                if b.button("\u274C Reject", key=f"x_{r['report_id']}"):
                    store.review_report(eng, int(r["report_id"]), me()["user_id"], "rejected"); refresh(); st.rerun()

    with t3:
        z = zones_df()
        with st.form("alert_form"):
            zn = ["All monitored zones"] + [f"{r['name']} ({r['country']})" for _, r in z.iterrows()]
            where = st.selectbox("Zone", zn)
            sev = st.selectbox("Severity", ["advisory", "warning", "severe", "info"])
            title = st.text_input("Title", max_chars=120)
            msg = st.text_area("Message", max_chars=600)
            hrs = st.slider("Stays active for (hours)", 1, 72, 24)
            ntf = st.checkbox("Email people who watch this zone (needs SMTP settings)", value=False)
            ok = st.form_submit_button("Publish alert", type="primary")
        if ok:
            if not title.strip():
                st.error("Please enter a title.")
            else:
                zid = None if where == zn[0] else int(z.iloc[zn.index(where) - 1]["zone_id"])
                store.create_alert(eng, zid, sev, title.strip(), msg.strip(), "manual", me()["user_id"], hrs)
                sent = store.notify_watchers(eng, zid, title, msg) if (ntf and zid) else 0
                refresh()
                st.success(f"Alert published." + (f" {sent} email(s) sent." if sent else ""))
        st.markdown("##### Live data")
        if st.button("\U0001F6F0\uFE0F Scan live weather & earthquake data now", key="scan_btn"):
            with st.spinner("Scanning all zones\u2026"):
                made = store.scan_and_publish_alerts(eng)
            refresh()
            st.success(f"Scan complete \u2014 {len(made)} new alert(s) created.") if made else st.info("Scan complete \u2014 no new alerts needed (or live sources unavailable).")
        st.markdown("##### Active alerts")
        for _, r in store.active_alerts(eng).iterrows():
            alert_card(r)
            if st.button("Deactivate", key=f"da_{r['alert_id']}"):
                store.deactivate_alert(eng, me()["user_id"], int(r["alert_id"])); refresh(); st.rerun()

    with t4:
        if not core.can(role(), "manage_volunteers"):
            st.warning("No access.")
        else:
            z = zones_df()
            users = store.df(eng, "SELECT user_id, name, email, role FROM AppUser WHERE is_active AND role IN ('resident','volunteer') "
                                  "AND user_id NOT IN (SELECT user_id FROM Volunteer WHERE user_id IS NOT NULL) ORDER BY name")
            st.markdown("##### Register a community member as a volunteer")
            if users.empty:
                st.caption("No eligible users.")
            else:
                ulabels = [f"{r['name']} ({r['email']})" for _, r in users.iterrows()]
                with st.form("vol_form"):
                    u = st.selectbox("User", ulabels)
                    zz = st.selectbox("Assigned zone", [f"{r['name']} ({r['country']})" for _, r in z.iterrows()])
                    skill = st.selectbox("Skill", ["Rescue", "Medical", "Logistics", "Communication", "Shelter management"])
                    ok = st.form_submit_button("Register volunteer")
                if ok:
                    good, msg = store.link_volunteer(eng, me()["user_id"], int(users.iloc[ulabels.index(u)]["user_id"]),
                                                     int(z.iloc[[f"{r['name']} ({r['country']})" for _, r in z.iterrows()].index(zz)]["zone_id"]), skill)
                    refresh(); st.success(msg) if good else st.error(msg)
            st.markdown("##### Assign a task")
            vols = store.df(eng, "SELECT volunteer_id, name FROM Volunteer ORDER BY name")
            res = store.df(eng, "SELECT resource_id, type, location FROM Resource ORDER BY type")
            if vols.empty:
                st.caption("No volunteers yet.")
            else:
                with st.form("task_form"):
                    v = st.selectbox("Volunteer", [f"{r['name']}" for _, r in vols.iterrows()])
                    zt = st.selectbox("Zone", [f"{r['name']} ({r['country']})" for _, r in z.iterrows()], key="tz")
                    title = st.text_input("Task title", max_chars=120)
                    desc = st.text_area("Details", max_chars=500)
                    rr = st.selectbox("Resource (optional)", ["None"] + [f"{r['type']} \u2014 {r['location']}" for _, r in res.iterrows()])
                    ok = st.form_submit_button("Assign task", type="primary")
                if ok:
                    zlabels = [f"{r['name']} ({r['country']})" for _, r in z.iterrows()]
                    rid = None if rr == "None" else int(res.iloc[[f"{r['type']} \u2014 {r['location']}" for _, r in res.iterrows()].index(rr)]["resource_id"])
                    good, m = store.create_task(eng, me()["user_id"], int(vols.iloc[[r["name"] for _, r in vols.iterrows()].index(v)]["volunteer_id"]),
                                                int(z.iloc[zlabels.index(zt)]["zone_id"]), title, desc, rid)
                    refresh(); st.success("Task assigned.") if good else st.error(m)
            st.markdown("##### Task board")
            st.dataframe(store.df(eng, "SELECT t.task_id AS \"ID\", t.title AS \"Task\", v.name AS \"Volunteer\", z.name AS \"Zone\", t.status AS \"Status\", t.updated_at AS \"Updated\" "
                                       "FROM Task t LEFT JOIN Volunteer v ON v.volunteer_id = t.volunteer_id LEFT JOIN Zone z ON z.zone_id = t.zone_id ORDER BY t.updated_at DESC LIMIT 50"),
                         hide_index=True, width="stretch")


def page_admin():
    head("Admin Console", "Users, audit trail and operational evidence.")
    if not need("manage_users"):
        return
    eng = get_engine()
    t1, t2, t3 = st.tabs(["\U0001F465 Users", "\U0001F4DC Audit log", "\U0001F4CA Operations & evidence"])
    with t1:
        u = store.df(eng, "SELECT user_id, name, email, role, is_active, created_at FROM AppUser ORDER BY created_at DESC")
        st.dataframe(u, hide_index=True, width="stretch")
        if len(u):
            labels = [f"{r['name']} ({r['email']}) \u2014 {r['role']}" for _, r in u.iterrows()]
            pick = st.selectbox("User", labels, key="adm_user")
            r = u.iloc[labels.index(pick)]
            a, b, c = st.columns([2, 1, 1])
            newrole = a.selectbox("Role", core.ROLES, index=core.ROLES.index(r["role"]), key="adm_role")
            if b.button("Set role", key="adm_setrole"):
                if int(r["user_id"]) == me()["user_id"] and newrole != "admin":
                    st.error("You cannot remove your own admin role.")
                else:
                    store.set_role(eng, me()["user_id"], int(r["user_id"]), newrole); refresh(); st.success("Role updated."); st.rerun()
            if c.button("Deactivate" if r["is_active"] else "Reactivate", key="adm_active"):
                if int(r["user_id"]) == me()["user_id"]:
                    st.error("You cannot deactivate yourself.")
                else:
                    store.set_active(eng, me()["user_id"], int(r["user_id"]), not r["is_active"]); refresh(); st.rerun()
    with t2:
        st.dataframe(store.df(eng, "SELECT created_at, email, action, detail FROM AuditLog ORDER BY log_id DESC LIMIT 200"), hide_index=True, width="stretch")
    with t3:
        m = store.ops_metrics(eng)
        c = st.columns(4)
        metric(c[0], "Registered users", m["users_total"], f"{m['users_7d']} new this week")
        metric(c[1], "Logins (7 days)", m["logins_7d"])
        metric(c[2], "Trip checks", m["advisories_total"], f"{m['advisories_7d']} this week")
        metric(c[3], "Auto-generated alerts", m["alerts_auto"], f"of {m['alerts_total']} total")
        st.write("")
        c = st.columns(4)
        metric(c[0], "Field reports", m["reports_total"], f"{m['reports_verified']} verified")
        metric(c[1], "Tasks completed", m["tasks_done"])
        metric(c[2], "Avg. rating (1-5)", "\u2014" if m["avg_rating"] is None else f"{m['avg_rating']:.2f}", f"{m['feedback_n']} responses")
        sus = m["avg_sus"]
        metric(c[3], "Avg. SUS score", "\u2014" if sus is None else f"{sus:.1f}", "" if sus is None else core.sus_grade(sus) + f" ({m['sus_n']} responses)")
        st.markdown("##### Export evidence (CSV)")
        exports = {"feedback": "SELECT * FROM Feedback", "sus_responses": "SELECT * FROM SusResponse", "trip_checks": "SELECT * FROM TravelAdvisoryLog",
                   "hazard_reports": "SELECT * FROM HazardReport", "alerts": "SELECT * FROM AlertNotice", "audit_log": "SELECT * FROM AuditLog", "tasks": "SELECT * FROM Task"}
        cols = st.columns(4)
        for i, (name, sql) in enumerate(exports.items()):
            d = store.df(eng, sql)
            cols[i % 4].download_button(f"\u2B07 {name}.csv", d.to_csv(index=False).encode(), file_name=f"floodconnect_{name}.csv", mime="text/csv", key=f"dl_{name}")


def page_feedback():
    head("Feedback & Usability Survey", "Your answers help us improve FloodConnect and are used as pilot evidence.")
    if not need("give_feedback"):
        return
    eng = get_engine()
    t1, t2 = st.tabs(["\u2B50 Quick feedback", "\U0001F4DD Usability survey (SUS)"])
    with t1:
        with st.form("fb_form", clear_on_submit=True):
            page = st.selectbox("What did you try?", ["Plan a Trip", "Hazard Map", "Shelters", "Report a Hazard", "Alerts", "Other"])
            done = st.radio("Were you able to do what you wanted?", ["Yes", "Partly", "No"], horizontal=True)
            rating = st.slider("Overall rating", 1, 5, 4)
            comment = st.text_area("Comments or suggestions", max_chars=800)
            ok = st.form_submit_button("Send feedback", type="primary")
        if ok:
            store.save_feedback(eng, me()["user_id"], rating, done == "Yes", page, comment)
            refresh(); st.success("Thank you for your feedback!")
    with t2:
        st.caption("10 short statements. 1 = strongly disagree, 5 = strongly agree.")
        with st.form("sus_form", clear_on_submit=True):
            ans = [st.select_slider(f"{i + 1}. {q}", options=[1, 2, 3, 4, 5], value=3, key=f"sus_{i}") for i, q in enumerate(core.SUS_QUESTIONS)]
            ok = st.form_submit_button("Submit survey", type="primary")
        if ok:
            score = store.save_sus(eng, me()["user_id"], ans)
            refresh(); st.success(f"Thank you! Your SUS score: {score:.1f} ({core.sus_grade(score)}).")


def page_auth():
    head("Sign in", "Access reporting, watchlists and your role's tools.")
    eng = get_engine()
    u = me()
    if u:
        st.markdown(f'<div class="fc-card"><h4>You are signed in</h4><div>{esc(u["name"])} \u00b7 {esc(u["email"])} \u00b7 {badge(u["role"], "#2563EB")}</div></div>', unsafe_allow_html=True)
        if st.button("Sign out", key="auth_signout"):
            store.audit(eng, "logout", "", u["user_id"], u["email"])
            st.session_state.pop("user", None)
            st.session_state["_nav_next"] = "\U0001F3E0 Home"
            st.rerun()
        return
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        t1, t2 = st.tabs(["Sign in", "Create account"])
        with t1:
            with st.form("login_form"):
                email = st.text_input("Email", key="li_email")
                pw = st.text_input("Password", type="password", key="li_pw")
                ok = st.form_submit_button("Sign in", type="primary", width="stretch")
            if ok:
                user, msg = store.authenticate(eng, email, pw)
                if user:
                    st.session_state["user"] = user
                    st.session_state["_nav_next"] = "\U0001F3E0 Home"
                    st.rerun()
                else:
                    st.error(msg)
        with t2:
            with st.form("signup_form"):
                name = st.text_input("Full name", key="su_name")
                email2 = st.text_input("Email", key="su_email")
                pw2 = st.text_input("Password", type="password", help="At least 8 characters, with a letter and a number.", key="su_pw")
                pw3 = st.text_input("Confirm password", type="password", key="su_pw2")
                ok = st.form_submit_button("Create account", type="primary", width="stretch")
            if ok:
                if pw2 != pw3:
                    st.error("Passwords do not match.")
                else:
                    good, res = store.create_user(eng, name, email2, pw2)
                    if good:
                        st.success("Account created \u2014 you can sign in now.")
                    else:
                        st.error(res)
        st.caption("New accounts start as community members. Coordinators and admins are assigned by an administrator.")


# ===================================================================== SHELL
PAGES = {
    "\U0001F3E0 Home": (page_home, None),
    "\U0001F9ED Plan a Trip": (page_trip, None),
    "\U0001F5FA\uFE0F Hazard Map": (page_map, None),
    "\U0001F3E0 Shelters": (page_shelters, None),
    "\U0001F6A8 Alerts": (page_alerts, None),
    "\U0001F4DD Report a Hazard": (page_report, "report_hazard"),
    "\U0001F4E6 Resources & Volunteers": (page_resources, "view_resources"),
    "\u2705 My Tasks": (page_my_tasks, "my_tasks"),
    "\U0001F6E0\uFE0F Coordinator Desk": (page_coord, "manage_shelters"),
    "\U0001F6E1\uFE0F Admin Console": (page_admin, "manage_users"),
    "\u2B50 Feedback": (page_feedback, "give_feedback"),
    "\U0001F510 Sign in": (page_auth, None),
}


def visible_pages():
    out = []
    for label, (_, perm) in PAGES.items():
        if label == "\U0001F510 Sign in":
            continue
        if perm is None or (me() and core.can(role(), perm)):
            out.append(label)
    out.append("\U0001F510 Sign in" if not me() else "\U0001F464 Account")
    return out


def main():
    try:
        eng = get_engine()
    except Exception as e:
        st.error("The app could not read its database secret. In Streamlit Cloud open Manage app > Settings > Secrets and make sure it contains a line like: DB_URL = \"postgresql://...\"")
        with st.expander("Technical details"):
            st.code(f"{type(e).__name__}: {str(e)[:300]}")
        st.stop()
    try:
        store.df(eng, "SELECT 1 FROM AlertNotice LIMIT 1")
    except Exception as e:
        text_ = str(e)
        if "does not exist" in text_ or "UndefinedTable" in text_:
            st.error("The database has not been upgraded to FloodConnect v2 yet. Run migrate.py once (see README), then reload.")
        else:
            st.error("The app could not connect to the database. Check the DB_URL secret and that your Supabase project is running (free projects pause after inactivity).")
        with st.expander("Technical details"):
            st.code(f"{type(e).__name__}: {text_.splitlines()[0][:300] if text_ else ''}")
        st.stop()

    if "_nav_next" in st.session_state:          # menu changes requested by a page (login/logout)
        st.session_state["nav"] = st.session_state.pop("_nav_next")
    pages = visible_pages()
    if st.session_state.get("nav") not in pages and st.session_state.get("nav") != "\U0001F510 Sign in":
        st.session_state["nav"] = pages[0]
    with st.sidebar:
        st.markdown('<div class="fc-brand"><div class="n">\U0001F30A FloodConnect</div><div class="t">Multi-hazard safety \u00b7 India & Japan</div></div>', unsafe_allow_html=True)
        if "nav" not in st.session_state:
            st.session_state["nav"] = pages[0]
        current = st.session_state["nav"]
        options = pages if current in pages else pages + [current]
        choice = st.radio("Menu", options, key="nav", label_visibility="collapsed")
        u = me()
        if u:
            st.markdown(f'<div class="fc-user"><div class="n">{esc(u["name"])}</div>{badge(u["role"], "#2563EB")}</div>', unsafe_allow_html=True)
        st.caption("Demonstration platform. Always follow official guidance from IMD, NDMA and JMA in an emergency.")

    key = "\U0001F510 Sign in" if choice in ("\U0001F464 Account", "\U0001F510 Sign in") else choice
    PAGES[key][0]()
    st.markdown('<div class="fc-foot">FloodConnect \u00b7 BCSE302P Database Systems Lab Project \u00b7 Data: Open-Meteo, USGS</div>', unsafe_allow_html=True)


main()
