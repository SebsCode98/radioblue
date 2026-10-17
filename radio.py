"""
radio.py - Plays and stops internet radio.

How it works, in short:
  To play a station we start the program "mpv" (a small, very reliable media
  player that runs without a window) and give it the stream address.
  To stop, we simply end that mpv program again.

  While mpv is running it opens a little "control socket" (a special file on
  disk that programs can talk through). We use it to change the radio volume
  and to ask which song is playing right now.

  The volume we change here is ONLY mpv's own volume. The speaker volume and
  the volume of other programs (like Spotify / librespot) stay untouched.
"""

import json
import os
import socket
import subprocess
import threading

import audio
import config


class RadioPlayer:
    """Remembers what is playing and controls the mpv player program.

    Only ONE RadioPlayer exists while the website runs (see app.py), so there
    is never more than one radio playing at the same time.
    """

    def __init__(self, volume=70):
        self._process = None          # the running mpv program (or None)
        self._station = None          # the station dict that is playing (or None)
        self._sink = None             # which speaker mpv plays to (None = default)
        self._volume = volume
        # A "lock" makes sure two button clicks at the same moment cannot
        # start two players at once. Only one piece of code may hold it.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public functions - these are called by the website (app.py)
    # ------------------------------------------------------------------

    def play(self, station):
        """Start playing a station (a dict with "id", "name" and "url").

        If something is already playing, it is stopped first.
        The sound goes straight to the connected Bluetooth box if there is
        one, otherwise to the Pi's default speaker.
        """
        with self._lock:
            self._stop_locked()
            self._sink = audio.find_bluetooth_sink()

            command = [
                "mpv",
                "--no-video",                    # audio only
                "--no-terminal",                 # do not wait for keyboard input
                "--ao=pulse",                    # talk to the PipeWire sound server
                f"--volume={self._volume}",
                f"--input-ipc-server={config.MPV_SOCKET_PATH}",
                "--cache=yes",                   # buffer a bit to avoid stutter
                "--demuxer-max-bytes=2MiB",
                "--",                            # everything after this is an address, never an option
                station["url"],
            ]
            if self._sink:
                # Send the sound directly to the Bluetooth box. This does NOT
                # change the system's default speaker, so Spotify is unaffected.
                command.insert(1, f"--audio-device=pulse/{self._sink}")

            self._process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._station = station

    def stop(self):
        """Stop the radio (does nothing if it is not playing)."""
        with self._lock:
            self._stop_locked()

    def restart_if_playing(self):
        """Start the current station again, e.g. after a Bluetooth box was
        connected, so that the sound moves over to the new box."""
        station = self._station if self.is_playing() else None
        if station:
            self.play(station)

    def set_volume(self, percent):
        """Change the radio volume (0-100). Remembered for the next station too."""
        self._volume = max(0, min(100, int(percent)))
        if self.is_playing():
            self._send_command(["set_property", "volume", self._volume])
        return self._volume

    def is_playing(self):
        """True while mpv is running. poll() returns None as long as a program
        has not finished yet."""
        return self._process is not None and self._process.poll() is None

    def status(self):
        """Return a small dictionary describing the current state, for the website."""
        playing = self.is_playing()
        return {
            "playing": playing,
            "station": self._station if playing else None,
            "volume": self._volume,
            "song": self._current_song() if playing else None,
            "output": self._sink or "default speaker",
        }

    # ------------------------------------------------------------------
    # Internal helpers - only used inside this file
    # ------------------------------------------------------------------

    def _stop_locked(self):
        """End the mpv program. Must only be called while holding self._lock."""
        if self._process is not None:
            if self._process.poll() is None:
                self._process.terminate()          # ask nicely
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()           # force it
                    self._process.wait()
            self._process = None
        self._station = None
        try:
            os.remove(config.MPV_SOCKET_PATH)
        except FileNotFoundError:
            pass

    def _current_song(self):
        """Ask mpv for the song title the station sends along ("icy-title").
        Returns None if the station does not send one."""
        answer = self._send_command(["get_property", "metadata"])
        if isinstance(answer, dict):
            # Upper/lower case differs between stations, so check both.
            return answer.get("icy-title") or answer.get("ICY-TITLE")
        return None

    def _send_command(self, command):
        """Send one command to mpv through its control socket and return mpv's
        answer ("data" field), or None if mpv did not answer.

        mpv understands simple JSON messages like:
            {"command": ["set_property", "volume", 50]}
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(config.MPV_SOCKET_PATH)
                sock.sendall((json.dumps({"command": command}) + "\n").encode())
                buffer = b""
                # mpv may also send unrelated "event" lines; we wait for the
                # line that contains the answer to our command ("error" field).
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return None
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        message = json.loads(line)
                        if "error" in message:
                            return message.get("data")
        except (OSError, ValueError):
            # Socket not there yet (mpv still starting) or a garbled answer.
            return None
