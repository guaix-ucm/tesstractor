import threading
import time

import serial

from ..device import MAX_LINE, LineReader


def test_readline_strips_nul():
    conn = serial.serial_for_url("loop://", timeout=0.5)
    conn.write(b"\x00\x00<fm 00808><mZ -0000>\r\n")
    assert LineReader(conn).readline() == b"<fm 00808><mZ -0000>\r\n"


def test_readline_line_in_pieces():
    # The timeout expires in the middle of the line
    conn = serial.serial_for_url("loop://", timeout=0.1)
    lines = LineReader(conn)
    conn.write(b"<fm 00994><")
    assert lines.readline() == b""
    conn.write(b"mZ -0000>\r\n<fm 00")
    assert lines.readline() == b"<fm 00994><mZ -0000>\r\n"
    conn.write(b"993><mZ -0000>\r\n")
    assert lines.readline() == b"<fm 00993><mZ -0000>\r\n"


def test_readline_reset_discards_piece():
    conn = serial.serial_for_url("loop://", timeout=0.1)
    lines = LineReader(conn)
    conn.write(b"<fm 00994><")
    assert lines.readline() == b""
    lines.reset()
    conn.write(b"<fm 00993><mZ -0000>\r\n")
    assert lines.readline() == b"<fm 00993><mZ -0000>\r\n"


def test_readline_without_newline_returns():
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
        line = LineReader(conn).readline()
        elapsed = time.monotonic() - t0
    finally:
        done.set()
        thread.join()
    assert elapsed < 1.0
    assert line == b""


def test_readline_max_size():
    conn = serial.serial_for_url("loop://", timeout=0.5)
    conn.write(b"x" * (MAX_LINE + 10))
    assert len(LineReader(conn).readline()) == MAX_LINE
