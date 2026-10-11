
import streamlit as st
import pandas as pd
import math
from sqlalchemy import create_engine, text

st.set_page_config(page_title="FloodConnect", layout="wide")


DB_URL = st.secrets["DB_URL"]
if DB_URL.startswith("postgresql://"):
    DB_URL = DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
engine = create_engine(DB_URL)

PRECAUTIONS = {
    "Flood":      "Avoid low-lying roads and riverbanks. Keep an emergency kit ready. Monitor local alerts and know your nearest shelter before traveling.",
    "Cyclone":    "Check official cyclone warnings before travel. Avoid coastal roads during warnings. Keep your phone charged.",
    "Landslide":  "Avoid hill/slope roads during or after heavy rain. Watch for cracked ground or leaning trees.",
    "Heavy Rain": "Avoid non-essential travel during heavy rain warnings. Watch for waterlogged roads.",
}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

st.title("FloodConnect")
st.caption("Integrated Flood Evacuation, Resource & Hazard Reporting Platform — India & Japan demo dataset")

page = st.sidebar.radio("Navigate", ["Travel Advisory", "Hazard Map", "Shelters & Capacity", "Report a Hazard", "Resources & Volunteers"])

zones_df = pd.read_sql("SELECT * FROM Zone;", engine)

if page == "Travel Advisory":
    st.header("Check before you travel")
    city_names = zones_df["name"].tolist()
    choice = st.selectbox("Pick a known zone, or enter coordinates manually below", ["-- manual entry --"] + city_names)

    if choice != "-- manual entry --":
        row = zones_df[zones_df["name"] == choice].iloc[0]
        lat, lon = float(row["latitude"]), float(row["longitude"])
    else:
        lat = st.number_input("Latitude", value=13.08, format="%.4f")
        lon = st.number_input("Longitude", value=80.27, format="%.4f")

    if st.button("Check travel risk"):
        zones_df["distance_km"] = zones_df.apply(lambda r: haversine(lat, lon, r["latitude"], r["longitude"]), axis=1)
        nearby = zones_df[zones_df["distance_km"] <= 150].sort_values("distance_km")
        if nearby.empty:
            st.success("No known high-risk zone within 150km. Still check local news before traveling.")
        else:
            z = nearby.iloc[0]
            st.warning(f"{z['risk_level']} risk — {z['hazard_type']} zone: {z['name']}, {z['region']} ({round(z['distance_km'],1)} km away)")
            st.info(PRECAUTIONS.get(z["hazard_type"], "Stay alert and follow local authority instructions."))
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO TravelAdvisoryLog (queried_lat, queried_lon, matched_zone_id, risk_level, message)
                    VALUES (:lat, :lon, :zid, :risk, :msg)
                """), {"lat": lat, "lon": lon, "zid": int(z["zone_id"]), "risk": f"{z['risk_level']} - {z['hazard_type']}", "msg": PRECAUTIONS.get(z["hazard_type"], "")})

elif page == "Hazard Map":
    st.header("Hazard zones — India & Japan")
    st.map(zones_df.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
    st.dataframe(zones_df[["name", "region", "hazard_type", "risk_level", "notes"]], use_container_width=True)

elif page == "Shelters & Capacity":
    st.header("Shelter status")
    shelters = pd.read_sql("""
        SELECT s.name, z.name AS zone, s.current_occupancy, s.total_capacity
        FROM Shelter s JOIN Zone z ON z.zone_id = s.zone_id;
    """, engine)
    for _, row in shelters.iterrows():
        pct = row["current_occupancy"] / row["total_capacity"]
        st.write(f"**{row['name']}** ({row['zone']}) — {row['current_occupancy']}/{row['total_capacity']}")
        st.progress(min(pct, 1.0))

elif page == "Report a Hazard":
    st.header("Submit a hazard report")
    with st.form("hazard_form"):
        zone_choice = st.selectbox("Zone", zones_df["name"].tolist())
        description = st.text_area("What did you observe?")
        contact = st.text_input("Your contact (optional)")
        submitted = st.form_submit_button("Submit report")
    if submitted and description:
        zid = int(zones_df[zones_df["name"] == zone_choice]["zone_id"].iloc[0])
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO HazardReport (reporter_contact, zone_id, description, latitude, longitude)
                VALUES (:c, :z, :d, :lat, :lon)
            """), {"c": contact, "z": zid, "d": description,
                    "lat": float(zones_df[zones_df["zone_id"]==zid]["latitude"].iloc[0]),
                    "lon": float(zones_df[zones_df["zone_id"]==zid]["longitude"].iloc[0])})
        st.success("Report submitted. Thank you.")

elif page == "Resources & Volunteers":
    st.header("Resources")
    st.dataframe(pd.read_sql("SELECT * FROM Resource;", engine), use_container_width=True)
    st.header("Volunteers")
    st.dataframe(pd.read_sql("""
        SELECT v.name, v.skill, z.name AS assigned_zone
        FROM Volunteer v JOIN Zone z ON z.zone_id = v.assigned_zone_id;
    """, engine), use_container_width=True)
