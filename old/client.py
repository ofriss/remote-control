import socket
import struct
from PIL import ImageGrab
from io import BytesIO

from old.protocol import (
    CHUNK_SIZE, ADDR, RECV_BUF, ACK_TIMEOUT,
    META_TAG, META_HEADER_FMT,
    DATA_TAG, DATA_HEADER_FMT,
    HELO_TAG, DONE_TAG, GO_TAG, WAIT_TAG,
    MISSING_TAG, MISSING_INDEX_FMT, MISSING_INDEX_SIZE,
)


class ImageSender:
    """Sends one screenshot per call as chunked UDP packets, but only while it holds the floor."""

    def __init__(self, sock: socket.socket) -> None:
        """Bind the sender to a connected socket that already has a timeout configured."""
        self.sock = sock # socket used to connect
        self.img_bytes: bytes = b"" # image data
        self.total_chunks: int = 0 # count of chunks (packets)
        self.resolution: tuple[int, int] = (0, 0) # (width, height) of the captured screen
        self.active: bool = False # whether the server has handed us the floor

    @staticmethod
    def capture() -> tuple[bytes, tuple[int, int]]:
        """Grab the current screen, returning it as JPEG bytes alongside its (width, height)."""
        img = ImageGrab.grab()
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        return buffer.getvalue(), img.size

    @staticmethod
    def parse_missing(resp: bytes) -> tuple[int, ...]:
        """Unpack the chunk indices the server is still waiting on from a whole MISSING packet."""
        index_data = resp[len(MISSING_TAG):]
        count = len(index_data) // MISSING_INDEX_SIZE
        return struct.unpack(f"!{count}{MISSING_INDEX_FMT}", index_data)

    def register(self) -> None:
        """Announce ourselves until the server grants the floor, capturing nothing while we wait."""
        while not self.active:
            try:
                self.sock.send(HELO_TAG)
                resp = self.sock.recv(RECV_BUF)
            except (socket.timeout, ConnectionRefusedError):
                continue # server is down, gone, or busy with someone else; announce again

            if resp == GO_TAG: # only GO grants the floor, so a duplicate WAIT is inert here
                self.active = True

    def send_meta(self) -> None:
        """Announce the size, chunk count and resolution of the current frame, before any DATA."""
        header = struct.pack(META_HEADER_FMT, len(self.img_bytes), self.total_chunks, *self.resolution)
        self.sock.send(META_TAG + header)

    def send_chunk(self, idx: int) -> None:
        """Send one DATA packet, for both the initial pass and retransmits."""
        header = struct.pack(DATA_HEADER_FMT, idx)
        self.sock.send(DATA_TAG + header + self.img_bytes[idx * CHUNK_SIZE : (idx + 1) * CHUNK_SIZE])

    def await_ack(self) -> None:
        """Resend whatever the server reports missing until it sends DONE, revokes us, or falls silent."""
        while True:
            try:
                resp = self.sock.recv(RECV_BUF)
            except socket.timeout:
                return # server is unreachable or already gave up; drop the frame

            if resp == DONE_TAG:
                return
            if resp == WAIT_TAG:
                self.active = False
                return # floor revoked mid-frame; abandon it rather than keep sending
            if resp.startswith(MISSING_TAG):
                for idx in self.parse_missing(resp):
                    self.send_chunk(idx)
            # a GO can cross a HELO in flight and arrive here; ignoring it leaves the frame untouched

    def send_image(self) -> None:
        """Capture the screen and deliver it as one frame, serving retransmits until acked."""
        self.img_bytes, self.resolution = self.capture()
        self.total_chunks = (len(self.img_bytes) + CHUNK_SIZE - 1) // CHUNK_SIZE
        # e.g. 2500B // 1024B = 2 INCORRECT
        # (2500B + 1024B - 1B) // 1024B = 3 CORRECT
        # another example: (2048B + 1024B - 1B) // 1024B = 2

        self.send_meta()
        for idx in range(self.total_chunks):
            self.send_chunk(idx)

        self.await_ack()

    def run(self) -> None:
        """Stream frames back to back while we hold the floor, and wait quietly whenever we do not."""
        while True:
            self.register()
            while self.active:
                try:
                    self.send_image()
                except ConnectionRefusedError:
                    self.active = False # server vanished mid-stream; park and announce ourselves again


if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(ADDR) # connected socket, so plain send/recv is enough
    sock.settimeout(ACK_TIMEOUT)
    ImageSender(sock).run()
