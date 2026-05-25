import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
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


def filter_by_date(df: pd.DataFrame, date_range: tuple) -> pd.DataFrame:
    if len(date_range) != 2:
        return df
    start, end = date_range
    mask = (df["received_at"].dt.date >= start) & (df["received_at"].dt.date <= end)
    return df[mask]


def make_chart(
    df: pd.DataFrame,
    y_label: str,
    dtick: float,
    color_col: str = "device_id",
) -> go.Figure:
    fig = go.Figure()
    for device in df[color_col].unique():
        sub = df[df[color_col] == device].sort_values("received_at")
        fig.add_trace(go.Scatter(
            x=sub["received_at"],
            y=sub["value"],
            mode="lines+markers",
            name=device,
            line=dict(shape="spline", smoothing=1.3),
            marker=dict(size=5),
        ))
    y_min = df["value"].min()
    y_max = df["value"].max()
    padding = dtick * 2
    fig.update_layout(
        xaxis_title="Czas",
        yaxis_title=y_label,
        legend_title_text="Urządzenie",
        margin=dict(t=20),
        yaxis=dict(
            dtick=dtick,
            range=[
                round(y_min / dtick - 1) * dtick - padding,
                round(y_max / dtick + 1) * dtick + padding,
            ],
        ),
    )
    return fig


def sidebar() -> tuple[APIClient, str | None, int, int, tuple]:
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

    st.sidebar.markdown("**Zakres dat**")
    today = date.today()
    date_range = st.sidebar.date_input(
        "Od — Do",
        value=(today - timedelta(days=1), today),
        format="YYYY-MM-DD",
    )

    st.sidebar.divider()
    st.sidebar.caption(f"Ostatnie odświeżenie: {datetime.now().strftime('%H:%M:%S')}")
    st.sidebar.button("Odśwież teraz", on_click=st.rerun)

    return client, device_id, limit, refresh_interval, date_range


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


def section_charts(client: APIClient, device_id: str | None, limit: int, date_range: tuple):
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
            df = filter_by_date(df, date_range)
            if df.empty:
                st.info("Brak danych temperatury w wybranym zakresie dat.")
            else:
                unit = df["unit"].iloc[0] if "unit" in df.columns else "°C"
                fig = make_chart(df, f"Temperatura [{unit}]", dtick=0.5)
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
            df = filter_by_date(df, date_range)
            if df.empty:
                st.info("Brak danych ciśnienia w wybranym zakresie dat.")
            else:
                unit = df["unit"].iloc[0] if "unit" in df.columns else "hPa"
                fig = make_chart(df, f"Ciśnienie [{unit}]", dtick=1.0)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Brak danych ciśnienia.")


def section_history(client: APIClient, device_id: str | None, limit: int, date_range: tuple):
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
    df = filter_by_date(df, date_range)
    df = df.sort_values("received_at", ascending=False)

    if df.empty:
        st.info("Brak rekordów w wybranym zakresie dat.")
        return

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

    client, device_id, limit, refresh_interval, date_range = sidebar()

    st_autorefresh(interval=refresh_interval * 1000, key="autorefresh")

    section_current(client, device_id)
    st.divider()
    section_charts(client, device_id, limit, date_range)
    st.divider()
    section_history(client, device_id, limit, date_range)


if __name__ == "__main__":
    main()
