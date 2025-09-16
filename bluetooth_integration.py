"""
Bluetooth Integration Module (Inactive Stub)
--------------------------------------------
This module is a placeholder for future Bluetooth device integrations.
Right now, all functions are no-ops that log usage.

Intended Features (future):
- Connect to cages, plugs, or toys with BLE APIs.
- Send lock/unlock signals.
- Query battery level, connection status.
"""

import logging

def connect_device(device_name: str):
    logging.info(f"[BLUETOOTH] Pretend connecting to {device_name}")
    return False  # not actually connected

def disconnect_device(device_name: str):
    logging.info(f"[BLUETOOTH] Pretend disconnecting from {device_name}")
    return False

def send_command(device_name: str, command: str):
    logging.info(f"[BLUETOOTH] Pretend sending {command} to {device_name}")
    return False

def get_status(device_name: str):
    logging.info(f"[BLUETOOTH] Pretend querying status of {device_name}")
    return {"connected": False, "battery": None}
