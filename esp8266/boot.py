# esp8266/boot.py
"""
boot.py — Runs on every ESP8266 power-on / reset.
Connects to WiFi and prints the IP address.
"""

import network
import time
from config import WIFI_SSID, WIFI_PASSWORD


def connect_wifi():
    """Connect to WiFi. Blocks until connected or timeout."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("[WiFi] Already connected:", wlan.ifconfig()[0])
        return wlan

    print("[WiFi] Connecting to", WIFI_SSID, "...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    # Wait up to 20 seconds
    for i in range(40):
        if wlan.isconnected():
            break
        time.sleep(0.5)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("[WiFi] Connected! IP:", ip)
    else:
        print("[WiFi] FAILED to connect after 20s")
        print("[WiFi] Check SSID/password in config.py")

    return wlan


# Auto-connect on boot
wlan = connect_wifi()
