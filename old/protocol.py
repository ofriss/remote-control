"""Wire format shared by the server and the client; both must agree on every name here."""
import struct

CHUNK_SIZE = 1024
ADDR = ("127.0.0.1", 9999)
RECV_BUF = 65536
TAG_SIZE = 4 # client -> server tags are read as packet[:TAG_SIZE], so they must be exactly this long

META_TAG = b"META"
META_HEADER_FMT = "!IHHH" # total_size (4 bytes), total_chunks (2), width (2), height (2)

DATA_TAG = b"DATA"
DATA_HEADER_FMT = "!H" # chunk_index (2 bytes); the count lives in META, so it is not repeated here
DATA_HEADER_SIZE = struct.calcsize(DATA_HEADER_FMT)

HELO_TAG = b"HELO" # "HELLO" would be read as tag b"HELL" and dropped; keep it at TAG_SIZE

DONE_TAG = b"DONE"

MISSING_TAG = b"MISSING"
MISSING_INDEX_FMT = "H"
MISSING_INDEX_SIZE = struct.calcsize("!" + MISSING_INDEX_FMT) # match the "!" packing, not native alignment

# server -> client only, so these are matched whole and need not be TAG_SIZE long
GO_TAG = b"GO"
WAIT_TAG = b"WAIT"

STALL_TIMEOUT = 0.5 # how long a silence must last before we assume packets were dropped
MAX_STALLS = 10     # give up on the frame after this many consecutive silences (~5s)
ACK_TIMEOUT = 2.0   # how long to wait for DONE/MISSING before giving up on the frame
CLIENT_TTL = 5.0    # forget a client we have not heard from for this long
