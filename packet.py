from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from struct import pack, unpack

from constants import (
    META_PACKET_PD_FMT,
    META_PACKET_PD_LEN,
    PACKET_HEADER_FMT,
    PACKET_HEADER_LEN,
)
from typedefs import Resolution

# IMPORTANT: max length is 65535

#   1 2 3 4 5 6 7 8   1 2 3 4 5 6 7 8   1 2 3 4 5 6 7 8
# + - - - - - - - - + - - - - - - - - + - - - - - - - - +
# |      type       |                len                |
# + - - - - - - - - + - - - - - - - - + - - - - - - - - |
# |    Payload... len bytes...                          |
# + - - - - - - - - + - - - - - - - - + - - - - - - - - +


# Bytes received from wire -> Packet.from_bytes -> BasePacketWrapper -> Interpret it
# BasePacketFactory.create -> Packet.to_bytes -> Send bytes to wire


# Describes the kind of packet
class PacketType(IntEnum):
    META = 0x0
    DATA = 0x1
    DONE = 0x2
    MISSING = 0x3
    HELLO = 0x4
    GO = 0x5
    WAIT = 0x6


# The packet class that represents it throughout the project
@dataclass
class Packet:
    type: PacketType
    # length: int #! implicitly inferred
    payload: bytes

    # Runs after __init__
    def __post_init__(self):
        if self.type not in PacketType:
            raise ValueError("Invalid packet type")

    # prepare packet bytes to send
    @staticmethod
    def to_bytes(packet: Packet) -> bytes:
        return pack(PACKET_HEADER_FMT, packet.type, len(packet.payload)) + packet.payload

    # create packet from bytes received
    @staticmethod
    def from_bytes(packet_bytes: bytes) -> Packet:
        header = packet_bytes[:PACKET_HEADER_LEN]
        type, length = unpack(PACKET_HEADER_FMT, header)
        payload = packet_bytes[PACKET_HEADER_LEN:PACKET_HEADER_LEN + length] # from header to header + length (payload end). Safer approach than [PACKET_HEADER_LEN:]. Ensures irrelevant bytes are not accidentally grabbed.
        return Packet(type, payload)


# An abstract wrapper class used to interpret packet payloads
class BasePacketWrapper(ABC):
    packet: Packet  # the actual packet to handle

    # target_* params ensure the packet is compatible with the wrapper.
    def __init__(
        self, packet: Packet, target_packet_type: PacketType, target_packet_len: int
    ):
        if packet.type != target_packet_type:
            raise ValueError(
                f"Incompatible packet type with packet wrapper '{self.__class__.__name__}'."
            )
        if len(packet.payload) != target_packet_len:
            raise ValueError(
                f"Incompatible packet header length with packet wrapper '{self.__class__.__name__}'"
            )

        self.packet = packet


# Meta packet wrapper
class MetaWrapper(BasePacketWrapper):
    # payload
    total_img_size: int  # 4 bytes
    total_chunks: int  # 2 bytes
    resolution: Resolution  # 2+2 bytes

    def __init__(self, packet: Packet):
        super().__init__(packet, PacketType.META, META_PACKET_PD_LEN)

        self.total_img_size, self.total_chunks, width, height = unpack(
            META_PACKET_PD_FMT,  # using the payload format
            self.packet.payload,
        )
        self.resolution = Resolution(width=width, height=height)


# A base packet factory class used to construct specific kinds of packets
class BasePacketFactory(ABC):
    # Generic basic minimalistic create function as a minimum requirement
    @staticmethod
    @abstractmethod
    def create(*args, **kwargs) -> Packet:
        pass


# TODO: Create an image class handler, and construct the packet just
# from the Image and passing to the handler
class MetaPacketFactory(BasePacketFactory):
    @staticmethod
    def create(
        total_img_size: int, total_chunks: int, width: int, height: int
    ) -> Packet:
        return Packet(
            PacketType.META,
            pack(META_PACKET_PD_FMT, total_img_size, total_chunks, width, height),
        )
