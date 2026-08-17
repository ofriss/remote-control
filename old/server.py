import tkinter as tk
import socket
import threading
import struct
import time
from PIL import Image
from io import BytesIO

from old.protocol import (
    RECV_BUF, TAG_SIZE,
    META_TAG, META_HEADER_FMT,
    DATA_TAG, DATA_HEADER_FMT, DATA_HEADER_SIZE,
    HELO_TAG, DONE_TAG, GO_TAG, WAIT_TAG,
    MISSING_TAG, MISSING_INDEX_FMT,
    ADDR, STALL_TIMEOUT, MAX_STALLS, CLIENT_TTL,
)


class FrameReceiver:
    """Reassembles one frame at a time from the single client currently holding the floor."""

    def __init__(self, sock: socket.socket) -> None:
        """Bind the receiver to a socket that already has a timeout configured."""
        self.sock = sock
        self.clients: dict[tuple[str, int], float] = {} # addr -> when we last heard from it
        self._active: tuple[str, int] | None = None      # what the active property was last set to
        self.owner: tuple[str, int] | None = None        # who the loop is actually serving right now
        self.reset()

    def reset(self) -> None:
        """Clear all per-frame state so the receiver can be reused; the floor and registry survive."""
        self.chunks: dict[int, bytes] = {}            # chunk index -> payload
        self.total_chunks: int | None = None          # from META; None means no META yet, so DATA is unusable
        self.total_size: int | None = None            # from META; used to verify the reassembled frame
        self.resolution: tuple[int, int] | None = None # from META; (width, height) of the captured screen
        self.stalls: int = 0

    @property
    def active(self) -> tuple[str, int] | None:
        """The client allowed to feed the receiver; safe to set from another thread at any time."""
        return self._active

    @active.setter
    def active(self, addr: tuple[str, int] | None) -> None:
        """Request the floor for a client; the receive loop performs the switch on its next pass."""
        self._active = addr # only recorded here, so the loop owns every send and every reset

    @property
    def is_complete(self) -> bool:
        """True once every expected chunk is held; safe because bogus indices are never stored."""
        return self.total_chunks is not None and len(self.chunks) == self.total_chunks

    def prune_clients(self) -> None:
        """Forget parked clients that have gone quiet; the owner is judged by MAX_STALLS instead."""
        cutoff = time.monotonic() - CLIENT_TTL
        self.clients = {addr: seen for addr, seen in self.clients.items()
                        if seen > cutoff or addr == self.owner}

        if self._active is not None and self._active not in self.clients:
            self._active = None # told to use a client that has since gone quiet

    def release_floor(self) -> None:
        """Drop an owner that died mid-frame; it has to say HELO again to be given the floor back."""
        if self.owner is not None:
            self.clients.pop(self.owner, None)

        self._active = None
        self.owner = None

    def sync_active(self) -> None:
        """Hand the floor to whoever the active property names, discarding any half-received frame."""
        target = self._active # snapshot, since the setter may run on another thread mid-switch
        if target == self.owner:
            return

        if self.owner is not None:
            self.sock.sendto(WAIT_TAG, self.owner)
        if target is not None:
            self.sock.sendto(GO_TAG, target)

        self.reset() # chunks from the old client must not carry into the new one's frame
        self.owner = target

    def handle_bystander(self, addr: tuple[str, int], tag: bytes) -> None:
        """Stand down a client that is streaming without the floor, once per frame it tries to start."""
        if tag == META_TAG:
            self.sock.sendto(WAIT_TAG, addr) # its WAIT was lost; the DATA that follows is dropped in silence

    def handle_meta(self, payload: bytes) -> None:
        """Record the size, chunk count and screen resolution announced by a META packet."""
        self.chunks.clear() # META marks a frame boundary; leftovers would break assemble()
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
        """Chase the missing chunks after a silence; False once the owner has gone quiet for good."""
        if self.owner is None:
            return True # nobody holds the floor; idle instead of counting silences

        self.stalls += 1
        if self.stalls > MAX_STALLS:
            return False # client went away mid-frame

        self.request_missing()
        return True

    def request_missing(self) -> None:
        """Ask the owner to resend whichever chunk indices we are still waiting on."""
        if self.total_chunks is None or self.owner is None:
            return # heard nothing usable yet, so we cannot say what is missing

        missing = [i for i in range(self.total_chunks) if i not in self.chunks]
        if missing:
            indices = struct.pack(f"!{len(missing)}{MISSING_INDEX_FMT}", *missing)
            self.sock.sendto(MISSING_TAG + indices, self.owner)

    def assemble(self) -> tuple[bytes, bool]:
        """Join the collected chunks in index order, flagging any size mismatch with META."""
        assert self.total_chunks is not None and self.total_size is not None, "assemble() called before META"

        data = b"".join(self.chunks[i] for i in range(self.total_chunks))
        return data, len(data) != self.total_size

    def receive(self) -> tuple[bytes | None, bool]:
        """Block until the owner delivers a whole frame, returning (None, True) if it is abandoned."""
        self.reset()

        while True:
            self.prune_clients()
            self.sync_active()

            try:
                packet, addr = self.sock.recvfrom(RECV_BUF)
            except socket.timeout:
                if not self.handle_stall():
                    self.release_floor()
                    return None, True
                continue

            self.clients[addr] = time.monotonic()
            tag, payload = packet[:TAG_SIZE], packet[TAG_SIZE:]

            if addr != self.owner:
                self.handle_bystander(addr, tag)
                continue # only the owner may feed the frame, or reset its stall count

            self.stalls = 0

            if tag == META_TAG:
                self.handle_meta(payload)
            elif tag == DATA_TAG:
                self.handle_data(payload)
            elif tag == HELO_TAG:
                self.sock.sendto(GO_TAG, addr) # the owner only says HELO if its GO was lost
                continue
            else:
                continue # unknown tag; unpacking it as a header would raise struct.error

            if self.is_complete: # do we have enough chunks? doesn't guarantee matched size
                self.sock.sendto(DONE_TAG, addr)
                return self.assemble()


if __name__ == "__main__":
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(ADDR)
    server.settimeout(STALL_TIMEOUT)
    receiver = FrameReceiver(server)

    while True:
        data, corrupt = receiver.receive()
        if data is None or corrupt: # todo: render corrupt frames instead of dropping them
            continue

        img = Image.open(BytesIO(data))
        # todo: render img, sizing the window from receiver.resolution
        # todo: pick receiver.active from the registry in receiver.clients
