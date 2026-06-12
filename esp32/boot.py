# boot.py - run on boot-up (ESP32)
import network
import time
from machine import Pin

# Status LED: most ESP32 dev boards have it on GPIO 2, active HIGH
# (unlike the ESP8266, where the onboard LED is inverted)
led = Pin(2, Pin.OUT)
led.value(0)  # Off


def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            led.value(1)  # Blink
            time.sleep(0.1)
            led.value(0)
            time.sleep(0.1)
    print('Network config:', wlan.ifconfig())
    led.value(1)  # On (Connected)


# Configure your WiFi here
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"

try:
    connect_wifi(SSID, PASSWORD)
except Exception as e:
    print("WiFi Connection Failed:", e)
