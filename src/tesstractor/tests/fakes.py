"""Fake devices for tests"""

import collections


class FakeSerial:
    """Fake serial port, answers each command with scripted lines"""

    def __init__(self, answers):
        # answers: cmd -> list of lines, the last one is repeated
        self.answers = {cmd: collections.deque(lines) for cmd, lines in answers.items()}
        self.is_open = True
        self.pending = collections.deque()
        self.written = []
        self.opened = 0

    def open(self):
        self.is_open = True
        self.opened += 1

    def close(self):
        self.is_open = False

    def reset_input_buffer(self):
        self._check_open()
        self.pending.clear()

    def write(self, cmd):
        self._check_open()
        self.written.append(cmd)
        lines = self.answers[cmd]
        line = lines.popleft() if len(lines) > 1 else lines[0]
        self.pending.append(line)

    def readline(self):
        self._check_open()
        if self.pending:
            return self.pending.popleft()
        return b""

    def _check_open(self):
        if not self.is_open:
            raise OSError("port not open")


class StreamSerial(FakeSerial):
    """Fake serial port that sends lines continuously"""

    def __init__(self, lines):
        super().__init__({})
        self.lines = collections.deque(lines)

    def reset_input_buffer(self):
        self._check_open()

    def readline(self):
        self._check_open()
        if self.lines:
            return self.lines.popleft()
        return b""
