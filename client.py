import socket
import struct
from PIL import ImageGrab
from io import BytesIO

CHUNK_SIZE = 1024
ADDR = ("127.0.0.1", 9999)
RECV_BUF = 65536
ACK_TIMEOUT = 2.0 # how long to wait for DONE/MISSING before giving up on the frame

META_TAG = b"META"
META_HEADER_FMT = "!IHHH" # total_size (4 bytes), total_chunks (2), width (2), height (2)

DATA_TAG = b"DATA"
DATA_HEADER_FMT = "!H" # chunk_index (2 bytes); the count lives in META, so it is not repeated here

DONE_TAG = b"DONE"

MISSING_TAG = b"MISSING"
MISSING_INDEX_FMT = "H"
MISSING_INDEX_SIZE = struct.calcsize("!" + MISSING_INDEX_FMT) # match the server's "!" packing, not native alignment


class ImageSender:
    """Sends one screenshot per call as chunked UDP packets, honouring retransmit requests."""

    def __init__(self, sock: socket.socket) -> None:
        """Bind the sender to a connected socket that already has a timeout configured."""
        self.sock = sock # socket used to connect
        self.img_bytes: bytes = b"" # image data
        self.total_chunks: int = 0 # count of chunks (packets)
        self.resolution: tuple[int, int] = (0, 0) # (width, height) of the captured screen

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

    def send_meta(self) -> None:
        """Announce the size, chunk count and resolution of the current frame, before any DATA."""
        header = struct.pack(META_HEADER_FMT, len(self.img_bytes), self.total_chunks, *self.resolution)
        self.sock.send(META_TAG + header)

    def send_chunk(self, idx: int) -> None:
        """Send one DATA packet, for both the initial pass and retransmits."""
        header = struct.pack(DATA_HEADER_FMT, idx)
        self.sock.send(DATA_TAG + header + self.img_bytes[idx * CHUNK_SIZE : (idx + 1) * CHUNK_SIZE])

    def await_ack(self) -> None:
        """Resend whatever the server reports missing until it sends DONE or falls silent."""
        while True:
            try:
                resp = self.sock.recv(RECV_BUF)
            except socket.timeout:
                return # server is unreachable or already gave up; drop the frame

            if resp == DONE_TAG:
                return
            if resp.startswith(MISSING_TAG):
                for idx in self.parse_missing(resp):
                    self.send_chunk(idx)

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


if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(ADDR) # connected socket, so plain send/recv is enough
    sock.settimeout(ACK_TIMEOUT)
    ImageSender(sock).send_image()
