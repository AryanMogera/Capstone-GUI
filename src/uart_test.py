import serial
import time


PORT = "/dev/cu.usbmodem1203"  # Mac

BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=1)

print("Listening...\n")

while True:
    line = ser.readline().decode(errors='ignore').strip()
    if line:
        print("RX:", line)
