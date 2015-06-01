from __future__ import absolute_import
__author__ = 'katharine'

from enum import IntEnum

from events import EventSourceMixin
from errors import PebbleError
from protocol import transfers
from util import stm32_crc

__all__ = ["PutBytes", "PutBytesError", "PutBytesType"]


class PutBytesError(PebbleError):
    pass


class PutBytesType(IntEnum):
    Firmware = 1
    Recovery = 2
    SystemResources = 3
    Resources = 4
    Binary = 5
    File = 6
    Worker = 7


class PutBytes(EventSourceMixin):
    def __init__(self, pebble, event_handler, object_type, object, bank=None, filename="", app_install_id=None):
        self._pebble = pebble
        self._object_type = object_type
        self._object = object
        self._bank = bank
        self._filename = filename
        self._app_install_id = app_install_id
        if app_install_id is not None:
            self._object_type |= (1 << 7)
        EventSourceMixin.__init__(self, event_handler)

    def send(self):
        # Prepare the watch to receive something.
        cookie = self._prepare()

        # Send it.
        self._send_object(cookie)

        # Commit it.
        self._commit(cookie)

        # Install it.
        self._install(cookie)

    def _assert_success(self, result):
        if result.result == transfers.PutBytesResponse.Result.NACK:
            raise PutBytesError("Watch NACKed PutBytes request.")

    def _prepare(self):
        if self._app_install_id is not None:
            packet = transfers.PutBytesApp(data=transfers.PutBytesAppInit(
                object_size=len(self._object), object_type=self._object_type, app_id=self._app_install_id))
        else:
            packet = transfers.PutBytes(data=transfers.PutBytesInit(
                object_size=len(self._object), object_type=self._object_type, bank=self._bank, filename=self._filename))
        self._pebble.send_packet(packet)

        result = self._pebble.read_from_endpoint(transfers.PutBytesResponse)
        self._assert_success(result)
        return result.cookie

    def _send_object(self, cookie):
        sent = 0
        length = 2000
        while sent < len(self._object):
            chunk = self._object[sent:sent+length]
            self._pebble.send_packet(transfers.PutBytes(data=(transfers.PutBytesPut(cookie=cookie, payload=chunk))))
            self._assert_success(self._pebble.read_from_endpoint(transfers.PutBytesResponse))
            sent += len(chunk)
            self._broadcast_event("progress", sent, len(self._object))

    def _commit(self, cookie):
        crc = stm32_crc.crc32(self._object)
        self._pebble.send_packet(transfers.PutBytes(data=transfers.PutBytesCommit(cookie=cookie, object_crc=crc)))
        self._assert_success(self._pebble.read_from_endpoint(transfers.PutBytesResponse))

    def _install(self, cookie):
        self._pebble.send_packet(transfers.PutBytes(data=transfers.PutBytesInstall(cookie=cookie)))
        self._assert_success(self._pebble.read_from_endpoint(transfers.PutBytesResponse))
