import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from api_client import APIClient, APIError
from config import DEFAULT_BASE_URL, DEFAULT_HISTORY_LIMIT, DEFAULT_REFRESH_INTERVAL

st.set_page_config(
    page_title="Systemy Pomiarowe",
    page_icon="📡",
    layout="wide",
)


def parse_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def sidebar() -> tuple[APIClient, str | None, int, int]:
    st.sidebar.title("⚙️ Konfiguracja")

    base_url = st.sidebar.text_input("Base URL backendu", value=DEFAULT_BASE_URL)
    client = APIClient(base_url)

    alive = client.health()
    if alive:
        st.sidebar.success("Backend: online ✓")
    else:
        st.sidebar.error("Backend: offline ✗")

    st.sidebar.divider()

    refresh_interval = st.sidebar.slider(
        "Interwał odświeżania (s)", min_value=5, max_value=60,
        value=DEFAULT_REFRESH_INTERVAL, step=5,
    )

    limit = st.sidebar.slider(
        "Limit historii", min_value=10, max_value=500,
        value=DEFAULT_HISTORY_LIMIT, step=10,
    )

    device_id = None
    if alive:
        try:
            devices = client.devices()
        except APIError:
            devices = []

        options = ["Wszystkie"] + devices
        selected = st.sidebar.selectbox("Urządzenie", options)
        device_id = None if selected == "Wszystkie" else selected

    st.sidebar.divider()
    st.sidebar.caption(f"Ostatnie odświeżenie: {datetime.now().strftime('%H:%M:%S')}")
    st.sidebar.button("Odśwież teraz", on_click=st.rerun)

    return client, device_id, limit, refresh_interval


def section_current(client: APIClient, device_id: str | None):
    st.header("Aktualne pomiary")

    try:
        temp_data = client.latest_temperature(device_id)
        pres_data = client.latest_pressure(device_id)
    except APIError as e:
        st.error(str(e))
        return

    if not temp_data and not pres_data:
        st.info("Brak danych w bazie.")
        return

    cols = st.columns(max(len(temp_data) + len(pres_data), 1))
    idx = 0

    for record in temp_data:
        with cols[idx]:
            st.metric(
                label=f"🌡️ Temperatura — {record['device_id']}",
                value=f"{record['value']:.1f} {record.get('unit', '°C')}",
            )
            st.caption(record.get("received_at", ""))
        idx += 1

    for record in pres_data:
        with cols[idx]:
            st.metric(
                label=f"🔵 Ciśnienie — {record['device_id']}",
                value=f"{record['value']:.1f} {record.get('unit', 'hPa')}",
            )
            st.caption(record.get("received_at", ""))
        idx += 1


def section_charts(client: APIClient, device_id: str | None, limit: int):
    st.header("Wykresy trendu")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🌡️ Temperatura")
        try:
            data = client.history(device_id=device_id, sensor="temperature", limit=limit)
        except APIError as e:
            st.error(str(e))
            data = []

        if data:
            df = pd.DataFrame(data)
            df["received_at"] = parse_datetime(df["received_at"])
            df = df.sort_values("received_at")
            unit = df["unit"].iloc[0] if "unit" in df.columns else "°C"
            fig = px.line(
                df, x="received_at", y="value", color="device_id",
                labels={"received_at": "Czas", "value": f"Temperatura [{unit}]", "device_id": "Urządzenie"},
                markers=True,
            )
            fig.update_layout(legend_title_text="Urządzenie", margin=dict(t=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych temperatury.")

    with col2:
        st.subheader("🔵 Ciśnienie")
        try:
            data = client.history(device_id=device_id, sensor="pressure", limit=limit)
        except APIError as e:
            st.error(str(e))
            data = []

        if data:
            df = pd.DataFrame(data)
            df["received_at"] = parse_datetime(df["received_at"])
            df = df.sort_values("received_at")
            unit = df["unit"].iloc[0] if "unit" in df.columns else "hPa"
            fig = px.line(
                df, x="received_at", y="value", color="device_id",
                labels={"received_at": "Czas", "value": f"Ciśnienie [{unit}]", "device_id": "Urządzenie"},
                markers=True,
            )
            fig.update_layout(legend_title_text="Urządzenie", margin=dict(t=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych ciśnienia.")


def section_history(client: APIClient, device_id: str | None, limit: int):
    st.header("Historia pomiarów")

    try:
        data = client.history(device_id=device_id, limit=limit)
    except APIError as e:
        st.error(str(e))
        return

    if not data:
        st.info("Brak rekordów historii.")
        return

    df = pd.DataFrame(data)
    df["received_at"] = parse_datetime(df["received_at"])
    df = df.sort_values("received_at", ascending=False)

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Eksport CSV",
        data=csv,
        file_name=f"historia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


def main():
    st.title("📡 Rozproszone Systemy Pomiarowe")

    client, device_id, limit, refresh_interval = sidebar()

    st_autorefresh(interval=refresh_interval * 1000, key="autorefresh")

    section_current(client, device_id)
    st.divider()
    section_charts(client, device_id, limit)
    st.divider()
    section_history(client, device_id, limit)


if __name__ == "__main__":
    main()
