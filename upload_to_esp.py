#!/usr/bin/env python3
"""
Upload files to ESP8266 using MicroPython RAW REPL mode.
This is the reliable method — no string escaping issues.
"""

import serial
import time
import sys
import os
import binascii


def enter_raw_repl(ser):
    """Enter MicroPython raw REPL mode."""
    ser.write(b"\x03\x03")  # Ctrl+C twice to interrupt
    time.sleep(0.3)
    ser.read(ser.in_waiting)  # flush

    ser.write(b"\x01")  # Ctrl+A = enter raw REPL
    time.sleep(0.3)
    data = ser.read(ser.in_waiting)
    if b"raw REPL" not in data:
        # try again
        ser.write(b"\x03\x03")
        time.sleep(0.3)
        ser.read(ser.in_waiting)
        ser.write(b"\x01")
        time.sleep(0.5)
        data = ser.read(ser.in_waiting)
    return b"raw REPL" in data


def exec_raw(ser, code, timeout=10):
    """Execute code in raw REPL mode and return output."""
    ser.read(ser.in_waiting)  # flush

    # Send code
    for i in range(0, len(code), 256):
        ser.write(code[i:i+256].encode())
        time.sleep(0.02)

    ser.write(b"\x04")  # Ctrl+D = execute
    time.sleep(0.1)

    # Read response
    result = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ser.in_waiting:
            result += ser.read(ser.in_waiting)
            if b"\x04>" in result:
                break
        time.sleep(0.05)

    # Parse: OK<output>\x04<error>\x04>
    text = result.decode(errors="replace")
    return text


def upload_file_raw(ser, local_path, remote_path):
    """Upload a file using raw REPL + base64 to avoid any encoding issues."""
    with open(local_path, "rb") as f:
        content = f.read()

    # Encode as hex to avoid ANY string issues
    hex_data = binascii.hexlify(content).decode()

    # Write in chunks
    chunk_size = 512  # hex chars per chunk (= 256 bytes of actual data)
    total_chunks = (len(hex_data) + chunk_size - 1) // chunk_size

    # Open file
    exec_raw(ser, f"_f = open('{remote_path}', 'wb')")

    for i in range(0, len(hex_data), chunk_size):
        chunk = hex_data[i:i+chunk_size]
        exec_raw(ser, f"_f.write(bytes.fromhex('{chunk}'))")

    exec_raw(ser, "_f.close()")


def main():
    port = "/dev/ttyUSB0"
    baud = 115200
    base = os.path.dirname(os.path.abspath(__file__))
    esp_dir = os.path.join(base, "esp8266")
    umqtt_file = "/tmp/umqtt/simple.py"

    print("═══════════════════════════════════════")
    print("  ESP8266 Uploader (Raw REPL)")
    print("═══════════════════════════════════════\n")

    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(0.5)

    print("Entering raw REPL...", end=" ", flush=True)
    if not enter_raw_repl(ser):
        print("FAILED. Trying hard reset...")
        ser.write(b"\x03\x03")
        time.sleep(1)
        ser.write(b"\x04")  # soft reboot
        time.sleep(2)
        ser.write(b"\x03")
        time.sleep(0.5)
        enter_raw_repl(ser)
    print("✓")

    # Create directories
    print("Creating directories...", end=" ", flush=True)
    exec_raw(ser, "import os")
    exec_raw(ser, """
try:
    os.mkdir('lib')
except:
    pass
""")
    exec_raw(ser, """
try:
    os.mkdir('lib/umqtt')
except:
    pass
""")
    # Create __init__.py for umqtt package
    exec_raw(ser, "_f = open('lib/umqtt/__init__.py', 'w'); _f.close()")
    print("✓")

    # Upload umqtt library
    if os.path.exists(umqtt_file):
        print("Uploading umqtt/simple.py ...", end=" ", flush=True)
        upload_file_raw(ser, umqtt_file, "lib/umqtt/simple.py")
        print("✓")

    # Upload project files
    for fname in ["config.py", "boot.py", "main.py"]:
        fpath = os.path.join(esp_dir, fname)
        if os.path.exists(fpath):
            print(f"Uploading {fname} ...", end=" ", flush=True)
            upload_file_raw(ser, fpath, fname)
            print("✓")

    # Verify
    print("\nVerifying files...", end=" ", flush=True)
    result = exec_raw(ser, "import os; print(os.listdir())")
    print("✓")
    # Extract the file list from output
    if "OK" in result:
        parts = result.split("OK", 1)
        if len(parts) > 1:
            output = parts[1].split("\x04")[0].strip()
            print(f"  Root: {output}")

    result2 = exec_raw(ser, """
import os
try:
    print(os.listdir('lib/umqtt'))
except:
    print('lib/umqtt NOT FOUND')
""")
    if "OK" in result2:
        parts = result2.split("OK", 1)
        if len(parts) > 1:
            output = parts[1].split("\x04")[0].strip()
            print(f"  lib/umqtt: {output}")

    # Exit raw REPL and soft reset
    ser.write(b"\x02")  # Ctrl+B = exit raw REPL
    time.sleep(0.3)
    print("\n✓ Upload complete! Resetting ESP8266...\n")
    ser.write(b"\x04")  # Ctrl+D = soft reset
    time.sleep(3)

    # Read boot output
    output = b""
    t0 = time.time()
    while time.time() - t0 < 10:
        if ser.in_waiting:
            output += ser.read(ser.in_waiting)
        time.sleep(0.1)

    boot_text = output.decode(errors="replace")
    print("── ESP8266 Boot Output ──")
    print(boot_text)

    ser.close()


if __name__ == "__main__":
    main()
