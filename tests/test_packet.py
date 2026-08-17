from struct import pack, unpack

import pytest

from constants import META_PACKET_PD_FMT, META_PACKET_PD_LEN
from packet import (
    BasePacketFactory,
    BasePacketWrapper,
    MetaPacketFactory,
    MetaWrapper,
    Packet,
    PacketType,
)
from typedefs import Resolution


# --- Packet ---

def test_packet_accepts_valid_type():
    packet = Packet(PacketType.DONE, b"")
    assert packet.type == PacketType.DONE
    assert packet.payload == b""


def test_packet_rejects_invalid_type():
    with pytest.raises(ValueError):
        Packet(99, b"")  # type: ignore[arg-type]


def test_packet_to_bytes_encodes_type_length_and_payload():
    payload = b"hello"
    packet = Packet(PacketType.DATA, payload)

    encoded = packet.to_bytes()

    packet_type, length = unpack("!BH", encoded[:3])
    assert packet_type == PacketType.DATA
    assert length == len(payload)
    assert encoded[3:] == payload


def test_packet_to_bytes_length_tracks_payload_not_a_stored_field():
    # length is derived from payload, so it can never desync from it.
    short = Packet(PacketType.DATA, b"a")
    long_ = Packet(PacketType.DATA, b"a" * 10)

    assert unpack("!BH", short.to_bytes()[:3])[1] == 1
    assert unpack("!BH", long_.to_bytes()[:3])[1] == 10


# --- BasePacketWrapper ---

def test_base_wrapper_accepts_matching_packet():
    packet = Packet(PacketType.DONE, b"ab")
    wrapper = BasePacketWrapper(packet, PacketType.DONE, 2)
    assert wrapper.packet is packet


def test_base_wrapper_rejects_wrong_type():
    packet = Packet(PacketType.DONE, b"ab")
    with pytest.raises(ValueError):
        BasePacketWrapper(packet, PacketType.DATA, 2)


def test_base_wrapper_rejects_wrong_payload_length():
    packet = Packet(PacketType.DONE, b"ab")
    with pytest.raises(ValueError):
        BasePacketWrapper(packet, PacketType.DONE, 3)


# --- MetaWrapper ---

def make_meta_packet(total_img_size=12345, total_chunks=13, width=1920, height=1080) -> Packet:
    payload = pack(META_PACKET_PD_FMT, total_img_size, total_chunks, width, height)
    return Packet(PacketType.META, payload)


def test_meta_wrapper_parses_payload_fields():
    packet = make_meta_packet(total_img_size=54321, total_chunks=7, width=1280, height=720)

    wrapper = MetaWrapper(packet)

    assert wrapper.total_img_size == 54321
    assert wrapper.total_chunks == 7
    assert wrapper.resolution == Resolution(width=1280, height=720)


def test_meta_wrapper_rejects_non_meta_packet():
    packet = Packet(PacketType.DATA, b"\x00" * META_PACKET_PD_LEN)
    with pytest.raises(ValueError):
        MetaWrapper(packet)


def test_meta_wrapper_rejects_wrong_length_payload():
    packet = Packet(PacketType.META, b"\x00" * (META_PACKET_PD_LEN - 1))
    with pytest.raises(ValueError):
        MetaWrapper(packet)


# --- BasePacketFactory ---

def test_base_packet_factory_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BasePacketFactory()  # type: ignore[abstract]


# --- MetaPacketFactory ---

def test_meta_packet_factory_creates_meta_packet():
    packet = MetaPacketFactory.create(total_img_size=100, total_chunks=1, width=800, height=600)

    assert packet.type == PacketType.META
    assert packet.payload == pack(META_PACKET_PD_FMT, 100, 1, 800, 600)


def test_meta_packet_factory_round_trips_through_wrapper():
    packet = MetaPacketFactory.create(total_img_size=999, total_chunks=42, width=640, height=480)

    wrapper = MetaWrapper(packet)

    assert wrapper.total_img_size == 999
    assert wrapper.total_chunks == 42
    assert wrapper.resolution == Resolution(width=640, height=480)
