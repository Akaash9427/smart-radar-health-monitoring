import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import json
import queue
import time
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================

BROKER = "broker.hivemq.com"
PORT = 1883

TOPIC = "smart-radar/hackathon/20261031/team01/data"

TEMP_LIMIT = 40.0
VIBRATION_LIMIT = 1.5

# ==========================================
# PAGE SETTINGS
# ==========================================

st.set_page_config(
    page_title="Smart Radar Monitoring",
    page_icon="📡",
    layout="wide"
)

# ==========================================
# MQTT CONNECTION
# ==========================================

@st.cache_resource
def start_mqtt():

    messages = queue.Queue(maxsize=500)

    state = {
        "connected": False,
        "last_received": None,
        "error": None
    }

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        client_id="radar-dashboard-viewer-akaash"
    )

    def on_connect(client, userdata, flags, rc):

        if rc == 0:
            state["connected"] = True
            state["error"] = None
            client.subscribe(TOPIC)
        else:
            state["connected"] = False
            state["error"] = f"Connection error: {rc}"

    def on_disconnect(client, userdata, rc):

        state["connected"] = False

    def on_message(client, userdata, msg):

        try:
            data = json.loads(msg.payload.decode())

            data["received_at"] = datetime.now()

            state["last_received"] = time.time()

            try:
                messages.put_nowait(data)
            except queue.Full:
                messages.get_nowait()
                messages.put_nowait(data)

        except Exception as error:
            state["error"] = str(error)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()

    except Exception as error:
        state["error"] = str(error)

    return {
        "client": client,
        "messages": messages,
        "state": state
    }


service = start_mqtt()

# ==========================================
# SESSION STORAGE
# ==========================================

if "mqtt_history" not in st.session_state:
    st.session_state.mqtt_history = []

if "mqtt_latest" not in st.session_state:
    st.session_state.mqtt_latest = None

# ==========================================
# DASHBOARD HEADER
# ==========================================

st.title("📡 SMART RADAR EQUIPMENT HEALTH")

st.caption(
    "Real-Time Vibration and Thermal Monitoring System"
)

st.divider()

# ==========================================
# LIVE DASHBOARD
# ==========================================

@st.fragment(run_every="1s")
def live_dashboard():

    messages = service["messages"]
    state = service["state"]

    # Collect incoming MQTT data

    while True:
        try:
            data = messages.get_nowait()

            st.session_state.mqtt_latest = data

            st.session_state.mqtt_history.append(data)

            st.session_state.mqtt_history = (
                st.session_state.mqtt_history[-300:]
            )

        except queue.Empty:
            break

    # --------------------------------------
    # COMMUNICATION STATUS
    # --------------------------------------

    st.subheader("Communication Status")

    if state["connected"]:
        st.success("MQTT Broker Connected")
    else:
        st.warning("Connecting to MQTT Broker...")

    st.caption("Broker: broker.hivemq.com")
    st.caption(f"Topic: {TOPIC}")

    latest = st.session_state.mqtt_latest

    if latest is None:
        st.info(
            "Waiting for ESP32 sensor readings. "
            "Start your Wokwi simulation."
        )
        return

    last_received = state["last_received"]

    if last_received and time.time() - last_received <= 10:
        st.success("Receiving sensor data")
    else:
        st.warning("No recent sensor data received.")

    # --------------------------------------
    # READ SENSOR VALUES
    # --------------------------------------

    temp1 = latest.get("temp1")
    temp2 = latest.get("temp2")
    vibration = latest.get("vibration_rms")

    status = str(latest.get("status", "UNKNOWN")).upper()

    # --------------------------------------
    # ANOMALY DETECTION
    # --------------------------------------

    temperature_fault = (
        (temp1 is not None and temp1 > TEMP_LIMIT)
        or
        (temp2 is not None and temp2 > TEMP_LIMIT)
    )

    vibration_fault = (
        vibration is not None
        and vibration > VIBRATION_LIMIT
    )

    degraded = (
        status == "DEGRADED"
        or temperature_fault
        or vibration_fault
    )

    # --------------------------------------
    # EQUIPMENT HEALTH
    # --------------------------------------

    st.subheader("Equipment Health Status")

    if degraded:
        st.error("⚠️ DEGRADED - Abnormal condition detected!")
    elif status == "NORMAL":
        st.success("✅ NORMAL - Equipment operating within limits")
    else:
        st.warning("Equipment status unavailable")

    # --------------------------------------
    # SENSOR READINGS
    # --------------------------------------

    st.subheader("Live Sensor Readings")

    col1, col2, col3 = st.columns(3)

    def display_value(value, unit):

        if value is None:
            return "Unavailable"

        return f"{float(value):.2f} {unit}"

    col1.metric(
        "Temperature Sensor 1",
        display_value(temp1, "°C")
    )

    col2.metric(
        "Temperature Sensor 2",
        display_value(temp2, "°C")
    )

    col3.metric(
        "Vibration RMS",
        display_value(vibration, "m/s²")
    )

    st.caption(
        "Data source: "
        + str(latest.get("data_source", "Wokwi simulation"))
    )

    # --------------------------------------
    # ALERT PANEL
    # --------------------------------------

    st.subheader("Anomaly Alerts")

    if temp1 is None or temp2 is None:
        st.warning("Temperature sensor reading unavailable.")

    if temp1 is not None and temp1 > TEMP_LIMIT:
        st.error("Temperature Sensor 1 exceeds the limit!")

    if temp2 is not None and temp2 > TEMP_LIMIT:
        st.error("Temperature Sensor 2 exceeds the limit!")

    if vibration_fault:
        st.error("Excessive vibration detected!")

    if not degraded:
        st.success("No configured anomaly detected.")

    # --------------------------------------
    # MONITORING HISTORY
    # --------------------------------------

    st.subheader("Monitoring History")

    history = st.session_state.mqtt_history

    if history:

        df = pd.DataFrame(history)

        df = df.rename(columns={
            "received_at": "Time",
            "temp1": "Temperature 1",
            "temp2": "Temperature 2",
            "vibration_rms": "Vibration RMS",
            "status": "Equipment Status"
        })

        # Recent readings table

        display_columns = [
            "Time",
            "Temperature 1",
            "Temperature 2",
            "Vibration RMS",
            "Equipment Status"
        ]

        st.dataframe(
            df[display_columns].tail(20),
            use_container_width=True,
            hide_index=True
        )

        # Temperature graph

        st.subheader("🌡️ Temperature Trend")

        chart_df = df.set_index("Time")[
            ["Temperature 1", "Temperature 2"]
        ]

        st.line_chart(chart_df)

        # Vibration graph

        st.subheader("📊 Vibration Trend")

        vibration_df = df.set_index("Time")[
            ["Vibration RMS"]
        ]

        st.line_chart(vibration_df)

        # Download history

        csv = df[display_columns].to_csv(index=False)

        st.download_button(
            label="Download Monitoring History",
            data=csv,
            file_name="radar_monitoring_history.csv",
            mime="text/csv"
        )

        if st.button("Clear Monitoring History"):
            st.session_state.mqtt_history = []
            st.rerun(scope="fragment")

    else:
        st.info("Waiting for monitoring records...")

    # --------------------------------------
    # THRESHOLD INFORMATION
    # --------------------------------------

    st.divider()

    st.subheader("Configured Detection Thresholds")

    col1, col2 = st.columns(2)

    col1.metric(
        "Temperature Limit",
        f"{TEMP_LIMIT:.1f} °C"
    )

    col2.metric(
        "Vibration Limit",
        f"{VIBRATION_LIMIT:.2f} m/s²"
    )


live_dashboard()

# ==========================================
# FOOTER
# ==========================================

st.divider()

st.caption(
    "SMART RADAR HEALTH MONITORING | "
    "ESP32 + MQTT + PYTHON + STREAMLIT"
)