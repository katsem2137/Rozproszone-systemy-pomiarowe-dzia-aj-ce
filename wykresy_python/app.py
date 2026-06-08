import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, date, time
from streamlit_autorefresh import st_autorefresh

from api_client import APIClient, APIError
from config import (
    DEFAULT_BASE_URL,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_USERNAME,
    DEFAULT_PASSWORD,
)

# Backend zapisuje received_at w UTC (kontener bazy chodzi w UTC). Na potrzeby
# WYSWIETLANIA przeliczamy na czas lokalny (z DST). Dane w bazie zostaja w UTC.
LOCAL_TZ = "Europe/Warsaw"

st.set_page_config(
    page_title="Systemy Pomiarowe",
    page_icon="📡",
    layout="wide",
)


def parse_datetime(series: pd.Series) -> pd.Series:
    # Traktujemy wejscie jako UTC, konwertujemy na czas lokalny i zdejmujemy tz
    # (naive local) — dzieki temu wykresy, tabela i filtry dat/godzin operuja
    # na czasie, ktory widzi uzytkownik.
    dt = pd.to_datetime(series, errors="coerce", utc=True)
    return dt.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)


def to_local_str(iso_str: str) -> str:
    # Pojedynczy znacznik czasu (z /latest) UTC -> lokalny string do wyswietlenia.
    if not iso_str:
        return ""
    ts = pd.to_datetime(iso_str, errors="coerce", utc=True)
    if pd.isna(ts):
        return iso_str
    return ts.tz_convert(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def filter_by_date(df: pd.DataFrame, date_range: tuple) -> pd.DataFrame:
    if len(date_range) != 2:
        return df
    start, end = date_range
    mask = (df["received_at"].dt.date >= start) & (df["received_at"].dt.date <= end)
    return df[mask]


def filter_by_time(df: pd.DataFrame, start_t: time, end_t: time) -> pd.DataFrame:
    # Filtr po porze dnia (godzina), niezaleznie od daty. Obsluguje tez zakres
    # przechodzacy przez polnoc (np. 22:00–06:00).
    if df.empty:
        return df
    times = df["received_at"].dt.time
    if start_t <= end_t:
        mask = (times >= start_t) & (times <= end_t)
    else:
        mask = (times >= start_t) | (times <= end_t)
    return df[mask]


def make_chart(
    df: pd.DataFrame,
    y_label: str,
    dtick: float,
    x_range: list | None = None,
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
        yaxis_title=y_label,
        legend_title_text="Urządzenie",
        margin=dict(t=20),
        xaxis=dict(title="Czas", tickformat="%H:%M", range=x_range),
        yaxis=dict(
            dtick=dtick,
            range=[
                round(y_min / dtick - 1) * dtick - padding,
                round(y_max / dtick + 1) * dtick + padding,
            ],
        ),
    )
    return fig


def sidebar() -> tuple[APIClient, str | None, int, int, tuple, tuple]:
    st.sidebar.title("⚙️ Konfiguracja")

    base_url = st.sidebar.text_input("Base URL backendu", value=DEFAULT_BASE_URL)

    use_auth = st.sidebar.checkbox("Użyj Basic Auth", value=True)
    username = None
    password = None
    if use_auth:
        username = st.sidebar.text_input("Login", value=DEFAULT_USERNAME)
        password = st.sidebar.text_input("Hasło", value=DEFAULT_PASSWORD, type="password")

    client = APIClient(base_url, username, password)

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
            if use_auth:
                st.sidebar.success("Autoryzacja: OK ✓")
        except APIError:
            devices = []
            if use_auth:
                st.sidebar.error("Autoryzacja: 401 — sprawdź login/hasło")
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

    st.sidebar.markdown("**Zakres godzin**")
    filter_hours = st.sidebar.checkbox("Filtruj po godzinach", value=False)
    time_range = None
    if filter_hours:
        col_a, col_b = st.sidebar.columns(2)
        start_time = col_a.time_input("Od godziny", value=time(0, 0), step=timedelta(minutes=30))
        end_time = col_b.time_input("Do godziny", value=time(23, 30), step=timedelta(minutes=30))
        time_range = (start_time, end_time)

    st.sidebar.divider()
    st.sidebar.caption(f"Ostatnie odświeżenie: {datetime.now().strftime('%H:%M:%S')}")
    st.sidebar.button("Odśwież teraz", on_click=st.rerun)

    return client, device_id, limit, refresh_interval, date_range, time_range


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
            st.caption(to_local_str(record.get("received_at", "")))
        idx += 1

    for record in pres_data:
        with cols[idx]:
            st.metric(
                label=f"🔵 Ciśnienie — {record['device_id']}",
                value=f"{record['value']:.1f} {record.get('unit', 'hPa')}",
            )
            st.caption(to_local_str(record.get("received_at", "")))
        idx += 1


def section_charts(client: APIClient, device_id: str | None, limit: int, date_range: tuple, time_range: tuple):
    st.header("Wykresy trendu")

    x_range = None
    if time_range and len(date_range) == 2:
        x_range = [
            datetime.combine(date_range[0], time_range[0]),
            datetime.combine(date_range[1], time_range[1]),
        ]

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
            if time_range:
                df = filter_by_time(df, time_range[0], time_range[1])
            if df.empty:
                st.info("Brak danych temperatury w wybranym zakresie.")
            else:
                unit = df["unit"].iloc[0] if "unit" in df.columns else "°C"
                fig = make_chart(df, f"Temperatura [{unit}]", dtick=0.5, x_range=x_range)
                st.plotly_chart(fig, width="stretch")
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
            if time_range:
                df = filter_by_time(df, time_range[0], time_range[1])
            if df.empty:
                st.info("Brak danych ciśnienia w wybranym zakresie.")
            else:
                unit = df["unit"].iloc[0] if "unit" in df.columns else "hPa"
                fig = make_chart(df, f"Ciśnienie [{unit}]", dtick=1.0, x_range=x_range)
                st.plotly_chart(fig, width="stretch")
        else:
            st.info("Brak danych ciśnienia.")


def section_history(client: APIClient, device_id: str | None, limit: int, date_range: tuple, time_range: tuple):
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
    if time_range:
        df = filter_by_time(df, time_range[0], time_range[1])
    df = df.sort_values("received_at", ascending=False)

    if df.empty:
        st.info("Brak rekordów w wybranym zakresie.")
        return

    st.dataframe(df, width="stretch", hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Eksport CSV",
        data=csv,
        file_name=f"historia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


def main():
    st.title("📡 Rozproszone Systemy Pomiarowe")

    client, device_id, limit, refresh_interval, date_range, time_range = sidebar()

    st_autorefresh(interval=refresh_interval * 1000, key="autorefresh")

    section_current(client, device_id)
    st.divider()
    section_charts(client, device_id, limit, date_range, time_range)
    st.divider()
    section_history(client, device_id, limit, date_range, time_range)


if __name__ == "__main__":
    main()
