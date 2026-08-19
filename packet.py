from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from struct import pack, unpack

from constants import (
    DATA_PACKET_PD_FMT,
    DATA_PACKET_PD_LEN,
    META_PACKET_PD_FMT,
    META_PACKET_PD_LEN,
    MISSING_PACKET_PD_LEN_BASE,
    PACKET_HEADER_FMT,
    PACKET_HEADER_LEN,
    create_missing_packet_pd_fmt,
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
        return (
            pack(PACKET_HEADER_FMT, packet.type, len(packet.payload)) + packet.payload
        )

    # create packet from bytes received
    @staticmethod
    def from_bytes(packet_bytes: bytes) -> Packet:
        header = packet_bytes[:PACKET_HEADER_LEN]
        type, length = unpack(PACKET_HEADER_FMT, header)
        payload = packet_bytes[
            PACKET_HEADER_LEN : PACKET_HEADER_LEN + length
        ]  # from header to header + length (payload end). Safer approach than [PACKET_HEADER_LEN:]. Ensures irrelevant bytes are not accidentally grabbed.
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
class MetaPacketWrapper(BasePacketWrapper):
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


class DataPacketWrapper(BasePacketWrapper):
    # payload
    chunk_index: int  # 2 bytes

    def __init__(self, packet: Packet):
        super().__init__(packet, PacketType.DATA, DATA_PACKET_PD_LEN)

        (self.chunk_index,) = unpack(DATA_PACKET_PD_FMT, self.packet.payload)


class MissingPacketWrapper(BasePacketWrapper):
    # payload
    indices: set[int]  # x2 bytes

    def __init__(self, packet: Packet):
        payload_len = len(packet.payload)
        indices_count = payload_len // MISSING_PACKET_PD_LEN_BASE

        super().__init__(
            packet,
            PacketType.MISSING,
            payload_len,
        )

        self.indices = set(unpack(
            create_missing_packet_pd_fmt(indices_count), self.packet.payload
        ))


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


class DataPacketFactory(BasePacketFactory):
    @staticmethod
    def create(chunk_index: int) -> Packet:
        return Packet(PacketType.DATA, pack(DATA_PACKET_PD_FMT, chunk_index))


class DonePacketFactory(BasePacketFactory):
    @staticmethod
    def create() -> Packet:
        return Packet(PacketType.DONE, b"")


class MissingPacketFactory(BasePacketFactory):
    @staticmethod
    def create(indices: set[int]) -> Packet:
        return Packet(
            PacketType.MISSING,
            pack(create_missing_packet_pd_fmt(len(indices)), *indices),
        )


class HelloPacketFactory(BasePacketFactory):
    @staticmethod
    def create() -> Packet:
        return Packet(PacketType.HELLO, b"")


class GoPacketFactory(BasePacketFactory):
    @staticmethod
    def create() -> Packet:
        return Packet(PacketType.GO, b"")


class WaitPacketFactory(BasePacketFactory):
    @staticmethod
    def create() -> Packet:
        return Packet(PacketType.WAIT, b"")


# TODO: add max size validation checks (maybe chunks too)
