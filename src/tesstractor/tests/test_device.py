import threading
import time

import serial

from ..device import MAX_LINE, read_line


def test_read_line_strips_nul():
    conn = serial.serial_for_url("loop://", timeout=0.5)
    conn.write(b"\x00\x00<fm 00808><mZ -0000>\r\n")
    assert read_line(conn) == b"<fm 00808><mZ -0000>\r\n"


def test_read_line_without_newline_returns():
    # Bytes without newline keep arriving, as with a wrong baud rate.
    # Serial.readline would block until they stop
    conn = serial.serial_for_url("loop://", timeout=0.3)
    done = threading.Event()

    def noise():
        while not done.is_set():
            conn.write(b"\x00")
            time.sleep(0.01)

    thread = threading.Thread(target=noise)
    thread.start()
    try:
        t0 = time.monotonic()
        line = read_line(conn)
        elapsed = time.monotonic() - t0
    finally:
        done.set()
        thread.join()
    assert elapsed < 1.0
    assert b"\n" not in line


def test_read_line_max_size():
    conn = serial.serial_for_url("loop://", timeout=0.5)
    conn.write(b"x" * (MAX_LINE + 10))
    assert len(read_line(conn)) == MAX_LINE
