from struct import calcsize

# Image
JPEG_IMAGE_QUALITY = 70

CHUNK_SIZE = 1024

META_PACKET_PD_FMT = "!IHHH" # total_size (4 bytes), total_chunks (2), width (2), height (2)
META_PACKET_PD_LEN = calcsize(META_PACKET_PD_FMT)
