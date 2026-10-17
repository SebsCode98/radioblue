"""
audio.py - Finds out which "speaker" (in Linux terms: an audio *sink*) belongs
to the Bluetooth box.

Background for beginners:
  The Raspberry Pi uses a sound server called PipeWire. Every place where sound
  can come out (headphone jack, HDMI, a Bluetooth box, ...) is called a "sink".
  When a Bluetooth box connects, PipeWire automatically creates a new sink for
  it with a name like "bluez_output.AA_BB_CC_DD_EE_FF.1".

  We use the small command line tool "pactl" to ask PipeWire for the list of
  sinks. This file ONLY READS information - it never changes any audio settings,
  so other programs (for example Spotify / librespot) are not affected.
"""

import subprocess


def _list_sink_names():
    """Return the names of all sinks PipeWire currently knows about.

    "pactl list short sinks" prints one line per sink, for example:
        35  bluez_output.AA_BB_CC_DD_EE_FF.1  PipeWire  s16le 2ch 48000Hz  RUNNING
    The second column is the name we want.
    """
    try:
        result = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        # pactl is missing or the sound server does not answer.
        return []
    names = []
    for line in result.stdout.splitlines():
        columns = line.split("\t")
        if len(columns) >= 2:
            names.append(columns[1])
    return names


def find_bluetooth_sink(mac=None):
    """Return the sink name of a connected Bluetooth box, or None if there is none.

    mac: optional address like "AA:BB:CC:DD:EE:FF". If given, we look for
         exactly that box. If not given, we take the first Bluetooth box found.
    """
    bluetooth_sinks = [name for name in _list_sink_names() if name.startswith("bluez_output.")]
    if mac:
        # In sink names the ":" of the address are replaced by "_".
        wanted = mac.replace(":", "_").upper()
        for name in bluetooth_sinks:
            if wanted in name.upper():
                return name
        return None
    return bluetooth_sinks[0] if bluetooth_sinks else None
