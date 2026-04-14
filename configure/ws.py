import socket
import threading
import select
import sys
import time
import getopt

# Listen
LISTENING_ADDR = '127.0.0.1'
if len(sys.argv) > 1:
    LISTENING_PORT = sys.argv[1]
else:
    LISTENING_PORT = 10015

# Pass
PASS = ''

# CONST
BUFLEN = 4096 * 4
TIMEOUT = 60
DEFAULT_HOST = '127.0.0.1:109'
RESPONSE = (b'HTTP/1.1 101 <font color="red"><b>YAN CONFIGS</b></font>\r\n'
            b'Upgrade: websocket\r\n'
            b'Connection: Upgrade\r\n'
            b'Sec-WebSocket-Accept: foo\r\n\r\n')


class Server(threading.Thread):
    def __init__(self, host, port):
        threading.Thread.__init__(self)
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()

    def run(self):
        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        intport = int(self.port)
        self.soc.bind((self.host, intport))
        self.soc.listen(0)
        self.running = True

        try:
            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(1)
                except socket.timeout:
                    continue

                conn = ConnectionHandler(c, self, addr)
                conn.start()
                self.addConn(conn)
        finally:
            self.running = False
            self.soc.close()

    def printLog(self, log):
        with self.logLock:
            print(log)

    def addConn(self, conn):
        with self.threadsLock:
            if self.running:
                self.threads.append(conn)

    def removeConn(self, conn):
        with self.threadsLock:
            self.threads.remove(conn)

    def close(self):
        self.running = False
        with self.threadsLock:
            threads = list(self.threads)
            for c in threads:
                c.close()


class ConnectionHandler(threading.Thread):
    def __init__(self, socClient, server, addr):
        threading.Thread.__init__(self)
        self.clientClosed = False
        self.targetClosed = True
        self.client = socClient
        self.client_buffer = b''
        self.server = server
        self.log = 'Connection: ' + str(addr)

    def close(self):
        try:
            if not self.clientClosed:
                self.client.shutdown(socket.SHUT_RDWR)
                self.client.close()
        except:
            pass
        finally:
            self.clientClosed = True

        try:
            if not self.targetClosed:
                self.target.shutdown(socket.SHUT_RDWR)
                self.target.close()
        except:
            pass
        finally:
            self.targetClosed = True

    def run(self):
        try:
            self.client_buffer = self.client.recv(BUFLEN)

            hostPort = self.findHeader(self.client_buffer.decode(), 'X-Real-Host')

            if hostPort == '':
                hostPort = DEFAULT_HOST

            split = self.findHeader(self.client_buffer.decode(), 'X-Split')

            if split != '':
                self.client.recv(BUFLEN)

            if hostPort != '':
                passwd = self.findHeader(self.client_buffer.decode(), 'X-Pass')

                if len(PASS) != 0 and passwd == PASS:
                    self.method_CONNECT(hostPort)
                elif len(PASS) != 0 and passwd != PASS:
                    self.client.send(b'HTTP/1.1 400 WrongPass!\r\n\r\n')
                elif hostPort.startswith('127.0.0.1') or hostPort.startswith('localhost'):
                    self.method_CONNECT(hostPort)
                else:
                    self.client.send(b'HTTP/1.1 403 Forbidden!\r\n\r\n')
            else:
                print('- No host header found!')

        except Exception as e:
            pass
        finally:
            self.close()

    def findHeader(self, head, header):
        aux = head.find(header + ': ')

        if aux == -1:
            return ''

        aux = head.find(':', aux)
        head = head[aux + 2:]
        aux = head.find('\r\n')

        if aux == -1:
            return ''

        return head[:aux]

    def method_CONNECT(self, path):
        self.log += ' - CONNECT ' + path

        p = path.split(':')
        if len(p) != 2:
            p = ['127.0.0.1', '109']

        try:
            self.target = socket.create_connection((p[0], int(p[1])))
            self.targetClosed = False
            self.client.send(RESPONSE)
            self.client_buffer = b''
            self.server.printLog(self.log)
            self.transfer(self.client, self.target)
        except Exception as e:
            self.server.printLog(self.log + ' - Error: ' + str(e))
            self.close()

    def transfer(self, src, dest):
        try:
            while True:
                r, _, _ = select.select([src, dest], [], [], TIMEOUT)

                if not r:
                    break

                for s in r:
                    data = s.recv(BUFLEN)
                    if not data:
                        return
                    if s is src:
                        dest.send(data)
                    elif s is dest:
                        src.send(data)
        except:
            pass


def main():
    print("\n:------- SSH WebSocket Proxy (ws.py) --------:")
    print("  Listening: %s:%s" % (LISTENING_ADDR, LISTENING_PORT))
    print("  SSH Target: %s" % DEFAULT_HOST)
    print(":--------------------------------------------:\n")

    server = Server(LISTENING_ADDR, LISTENING_PORT)
    server.start()

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping server...")
        server.close()


if __name__ == '__main__':
    main()
