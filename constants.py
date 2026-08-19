from struct import calcsize

# Image
JPEG_IMAGE_QUALITY = 70

CHUNK_SIZE = 1024

PACKET_HEADER_FMT = "!BH" # type (1 byte), len (2 bytes)
PACKET_HEADER_LEN = calcsize(PACKET_HEADER_FMT)

META_PACKET_PD_FMT = "!IHHH" # total_size (4 bytes), total_chunks (2), width (2), height (2)
META_PACKET_PD_LEN = calcsize(META_PACKET_PD_FMT)

DATA_PACKET_PD_FMT = "!H" # chunk_index (2 bytes)
DATA_PACKET_PD_LEN = calcsize(DATA_PACKET_PD_FMT)

MISSING_PACKET_PD_FMT_BASE = "H" # chunk_index (2 bytes)
MISSING_PACKET_PD_LEN_BASE = calcsize(MISSING_PACKET_PD_FMT_BASE)
def create_missing_packet_pd_fmt(indices_len: int) -> str:
    return f"!{MISSING_PACKET_PD_FMT_BASE * indices_len}"
