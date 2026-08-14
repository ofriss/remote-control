import tkinter as tk
import socket
import threading
import struct
from PIL import Image
from io import BytesIO


CHUNK_SIZE = 1024
ADDR = ("127.0.0.1", 9999)
RECV_BUF = 65536
TAG_SIZE = 4

META_TAG = b"META"
META_HEADER_FMT = "!IHHH" # total_size (4 bytes), total_chunks (2), width (2), height (2)

DATA_TAG = b"DATA"
DATA_HEADER_FMT = "!H" # chunk_index (2 bytes); the count lives in META, so it is not repeated here
DATA_HEADER_SIZE = struct.calcsize(DATA_HEADER_FMT)

DONE_TAG = b"DONE"

MISSING_TAG = b"MISSING"
MISSING_INDEX_FMT = "H"

STALL_TIMEOUT = 0.5 # how long a silence must last before we assume packets were dropped
MAX_STALLS = 10     # give up on the frame after this many consecutive silences (~5s)


class FrameReceiver:
    """Reassembles one frame at a time from chunked UDP packets."""

    def __init__(self, sock: socket.socket) -> None:
        """Bind the receiver to a socket that already has a timeout configured."""
        self.sock = sock
        self.reset()

    def reset(self) -> None:
        """Clear all per-frame state so the receiver can be reused."""
        self.chunks: dict[int, bytes] = {}            # chunk index -> payload
        self.total_chunks: int | None = None          # from META; None means no META yet, so DATA is unusable
        self.total_size: int | None = None            # from META; used to verify the reassembled frame
        self.resolution: tuple[int, int] | None = None # from META; (width, height) of the captured screen
        self.client_addr: tuple[str, int] | None = None # remembered so we can chase chunks during a silence
        self.stalls: int = 0

    @property
    def is_complete(self) -> bool:
        """True once every expected chunk is held; safe because bogus indices are never stored."""
        return self.total_chunks is not None and len(self.chunks) == self.total_chunks

    def handle_meta(self, payload: bytes) -> None:
        """Record the size, chunk count and screen resolution announced by a META packet."""
        self.total_size, self.total_chunks, width, height = struct.unpack(META_HEADER_FMT, payload)
        self.resolution = (width, height)

    def handle_data(self, payload: bytes) -> None:
        """Store one chunk, ignoring anything that arrives before META or outside the expected range."""
        if self.total_chunks is None:
            return # no META, so the frame is unknown and its chunks are unusable; skip it

        idx = struct.unpack(DATA_HEADER_FMT, payload[:DATA_HEADER_SIZE])[0]
        if idx >= self.total_chunks:
            return # stray packet with a bogus index; ignore rather than corrupt the count

        self.chunks[idx] = payload[DATA_HEADER_SIZE:]

    def handle_stall(self) -> bool:
        """Chase the missing chunks after a silence; False once the client has gone quiet for good."""
        if self.client_addr is None:
            return True # nothing has ever arrived; keep waiting for a first frame

        self.stalls += 1
        if self.stalls > MAX_STALLS:
            return False # client went away mid-frame

        self.request_missing()
        return True

    def request_missing(self) -> None:
        """Ask the client to resend whichever chunk indices we are still waiting on."""
        if self.total_chunks is None or self.client_addr is None:
            return # heard nothing usable yet, so we cannot say what is missing

        missing = [i for i in range(self.total_chunks) if i not in self.chunks]
        if missing:
            indices = struct.pack(f"!{len(missing)}{MISSING_INDEX_FMT}", *missing)
            self.sock.sendto(MISSING_TAG + indices, self.client_addr)

    def assemble(self) -> tuple[bytes, bool]:
        """Join the collected chunks in index order, flagging any size mismatch with META."""
        assert self.total_chunks is not None and self.total_size is not None, "assemble() called before META"

        data = b"".join(self.chunks[i] for i in range(self.total_chunks))
        return data, len(data) != self.total_size

    def receive(self) -> tuple[bytes | None, bool]:
        """Block until a whole frame arrives, returning (None, True) if it is abandoned or has no META."""
        self.reset()

        while True:
            try:
                packet, addr = self.sock.recvfrom(RECV_BUF)
            except socket.timeout:
                if not self.handle_stall():
                    return None, True
                continue

            self.stalls = 0
            self.client_addr = addr
            tag, payload = packet[:TAG_SIZE], packet[TAG_SIZE:]

            if tag == META_TAG:
                self.handle_meta(payload)
            elif tag == DATA_TAG:
                self.handle_data(payload)
            else:
                continue # unknown tag; unpacking it as a header would raise struct.error

            if self.is_complete: # do we have enough chunks? doesn't guarantee matched size
                self.sock.sendto(DONE_TAG, addr)
                return self.assemble()


server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(ADDR)
server.settimeout(STALL_TIMEOUT)

if __name__ == "__main__":
    receiver = FrameReceiver(server)

    while True:
        data, corrupt = receiver.receive()
        if data is None or corrupt: # todo: render corrupt frames instead of dropping them
            continue

        img = Image.open(BytesIO(data))
        # todo: render img, sizing the window from receiver.resolution

# can it handle multiple clients? what will happen if so?
