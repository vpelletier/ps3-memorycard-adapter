#!/usr/bin/env python3
from functools import partial
import os
import select
import socket
import usb1
from nbd import NBDServer
from cache import FileDictCache
from authenticator import SockAuthenticator
from memory_card_reader import PlayStationMemoryCardReader

def main(options):
    nbd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    nbd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    nbd_sock.bind((options.nbd_address, options.nbd_port))
    authentication_cache = FileDictCache(options.auth_cache,
      read_only=options.auth_cache_read_only)
    authenticator = SockAuthenticator(options.auth_address, options.auth_port,
      authentication_cache)
    socket_dict = {}
    # TODO: refactor to support non-blocking IO
    try:
        with usb1.USBContext() as usb_context:
            usb_device = usb_context.openByVendorIDAndProductID(0x054c, 0x02ea)
            with usb_device.claimInterface(0):
                reader = PlayStationMemoryCardReader(usb_device, authenticator)
                print('Waiting for client...')
                epoll = select.epoll()
                def accept():
                    (nbd_client_sock, addr) = nbd_sock.accept()
                    fileno = nbd_client_sock.fileno()
                    print('Client connected %s:%i' % addr)
                    nbd_server = NBDServer(sock=nbd_client_sock, device=reader)
                    if nbd_server.greet():
                        socket_dict[fileno] = nbd_server
                        handler_dict[nbd_server] = nbd_server.handle
                        epoll.register(
                            fileno,
                            select.EPOLLIN | select.EPOLLHUP,
                        )

                nbd_sock_fileno = nbd_sock.fileno()
                socket_dict[nbd_sock_fileno] = nbd_sock
                handler_dict = {
                    nbd_sock: accept,
                }
                epoll.register(nbd_sock_fileno, select.EPOLLIN)
                try:
                    nbd_sock.listen(1)
                    while True:
                        for fd, event in epoll.poll():
                            print(fd, event)
                            sock = socket_dict[fd]
                            if event == select.EPOLLIN:
                                handler_dict[sock]()
                            else:
                                epoll.unregister(sock.fileno())
                                del socket_dict[sock.fileno()]
                                del handler_dict[sock]
                                sock.close()
                finally:
                    nbd_sock.shutdown(socket.SHUT_RDWR)
                    del socket_dict[nbd_sock_fileno]
    except KeyboardInterrupt:
        pass
    finally:
        nbd_sock.close()
        for sock in socket_dict.values():
            # ...actually NBDServer objects
            sock.close()

if __name__ == '__main__':
    # TODO: argparse, move in main()
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-p', '--nbd-port', default=10809, type='int',
      help='Port the embeded NBD server will listen on.')
    parser.add_option('-a', '--nbd-address', default='',
      help='Address the embeded NBD server will listen on.')
    parser.add_option('-c', '--auth-cache', default='auth_cache.bin',
      help='File containing authentication data from previous sessions.')
    parser.add_option('-r', '--auth-cache-read-only', default=False,
      action='store_true',
      help='Don\'t store authentication information generated during this run.')
    parser.add_option('-P', '--auth-port', default=20531, type='int',
      help='Port used to contact authentication daemon.')
    parser.add_option('-A', '--auth-address', default='127.0.0.1',
      help='Address used to contact authentication daemon.')
    (options, args) = parser.parse_args()
    main(options)

