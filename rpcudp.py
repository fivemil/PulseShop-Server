"""
Copyright (c) 2014 Brian Muller
Copyright (c) 2015 OpenBazaar
"""

import random

import nacl.signing, nacl.encoding, nacl.hash

from binascii import hexlify

from hashlib import sha1
from base64 import b64encode

from twisted.internet import reactor
from twisted.internet import defer

from dht.log import Logger
from dht.kprotocol import Message, Command
from dht import node

class RPCProtocol():
    def __init__(self, proto, router, waitTimeout=5, noisy=True):
        """
        Args:
            proto: A protobuf `Node` object containing info about this node.
            router: A `RoutingTable` object from dht.routing. Implies a `network.Server` object
                    must be started first.
            waitTimeout: Consider it a connetion failure if no response
                    within this time window.
            noisy: Whether or not to log the output for this class.

        """
        self.proto = proto
        self.router = router
        self._waitTimeout = waitTimeout
        self._outstanding = {}
        self.noisy = noisy
        self.log = Logger(system=self)

    def receive_message(self, datagram, connection):
        m = Message()
        try:
            m.ParseFromString(datagram)
            sender = node.Node(m.sender.guid, connection.dest_addr[0], connection.dest_addr[1],
                               m.sender.signedPublicKey, m.sender.vendor)
        except:
            # If message isn't formatted property then ignore
            self.log.msg("Received unknown message from %s, ignoring" % str(connection.dest_addr))
            return False

        # Check that the GUID is valid. If not, ignore
        if self.router.isNewNode(sender):
            try:
                pubkey = m.sender.signedPublicKey[len(m.sender.signedPublicKey) - 32:]
                verify_key = nacl.signing.VerifyKey(pubkey)
                verify_key.verify(m.sender.signedPublicKey)
                h = nacl.hash.sha512(m.sender.signedPublicKey)
                pow = h[64:128]
                if int(pow[:6], 16) >= 50 or hexlify(m.sender.guid) != h[:40]:
                    raise Exception('Invalid GUID')

            except:
                self.log.msg("Received message from sender with invalid GUID, ignoring")
                return False

        msgID = m.messageID
        data = tuple(m.arguments)
        if msgID in self._outstanding:
            self._acceptResponse(msgID, data, sender)
        else:
            self._acceptRequest(msgID, str(Command.Name(m.command)).lower(), data, sender, connection)

    def _acceptResponse(self, msgID, data, sender):
        msgargs = (b64encode(msgID), sender)
        if self.noisy:
            self.log.msg("Received response for message id %s from %s" % msgargs)
        d, timeout = self._outstanding[msgID]
        timeout.cancel()
        d.callback((True, data))
        del self._outstanding[msgID]

    def _acceptRequest(self, msgID, funcname, args, sender, connection):
        if self.noisy:
            self.log.msg("received request from %s, command %s" % (sender, funcname.upper()))
        f = getattr(self, "rpc_%s" % funcname, None)
        if f is None or not callable(f):
            msgargs = (self.__class__.__name__, funcname)
            self.log.error("%s has no callable method rpc_%s; ignoring request" % msgargs)
            return False
        d = defer.maybeDeferred(f, sender, *args)
        d.addCallback(self._sendResponse, funcname, msgID, sender, connection)

    def _sendResponse(self, response, funcname, msgID, sender, connection):
        if self.noisy:
            self.log.msg("sending response for msg id %s to %s" % (b64encode(msgID), sender))
        m = Message()
        m.messageID = msgID
        m.sender.MergeFrom(self.proto)
        m.command = Command.Value(funcname.upper())
        for arg in response:
            m.arguments.append(arg)
        data = m.SerializeToString()
        connection.send_message(data)

    def _timeout(self, msgID):
        args = (b64encode(msgID), self._waitTimeout)
        self.log.error("Did not received reply for msg id %s within %i seconds" % args)
        self._outstanding[msgID][0].callback((False, None))
        del self._outstanding[msgID]

    def __getattr__(self, name):
        if name.startswith("_") or name.startswith("rpc_"):
            return object.__getattr__(self, name)

        try:
            return object.__getattr__(self, name)
        except AttributeError:
            pass

        def func(address, *args):
            msgID = sha1(str(random.getrandbits(255))).digest()
            m = Message()
            m.messageID = msgID
            m.sender.MergeFrom(self.proto)
            m.command = Command.Value(name.upper())
            for arg in args:
                m.arguments.append(arg)
            data = m.SerializeToString()
            if self.noisy:
                self.log.msg("calling remote function %s on %s (msgid %s)" % (name, address, b64encode(msgID)))
            self.multiplexer.send_message(data, address)
            d = defer.Deferred()
            timeout = reactor.callLater(self._waitTimeout, self._timeout, msgID)
            self._outstanding[msgID] = (d, timeout)
            return d

        return func