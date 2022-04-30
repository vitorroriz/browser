from bz2 import decompress
import socket
import sys
import ssl
import tkinter
import gzip

from numpy import empty

class Url:
    def __init__(self, url):
        self.url = url
        self.scheme, self.host, self.path, self.port = self.parse(url)

    def parse(self, url):
        scheme, url = url.split("://", 1)
        assert scheme in ["http", "https"], "Unknown scheme {}".format(scheme)
        if "/" in url:
            host, path = url.split("/", 1)
        else:
            host = url
            path = ""

        path = "/" + path #adding "/" back to path

        #handle custom ports
        if ":" in host:
            host, port = host.split(":", 1)
            port = int(port)
        else:
            port = 80 if scheme == "http" else 443

        return scheme, host, path, port


class Browser:
    def __init__(self, WIDTH = 800, HEIGHT = 600):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

    def request(self, url):
        s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)

        url = Url(url)

        #if it is https, let's wrap the socket with ssl library
        if url.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=url.host)

        s.connect((url.host, url.port))

        # GET /index.html HTTP/1.0
        # Host: example.org
        #
        #there is actually an empty lines indicating end of the request
        request = "GET {} HTTP/1.1\r\n".format(url.path).encode("utf8")
        # headers = "Host: {}\r\nConnection: close\r\nUser-Agent: Mr. Vivi\r\n\r\n".format(host).encode("utf8")

        headersMap = {"Host": url.host, "Connection": "close", "User-Agent": "Mr. Vivi", "Accept-Encoding": "gzip"}
        print(headersMap)
        headers = ""
        if headersMap:
            for key in headersMap:
                headers += key + ": " + headersMap[key] + "\r\n"
        else:
            headers = "\r\n"

        headers += "\r\n"
        print(headers) 
        headers = headers.encode("utf8")

        request += headers
        s.send(request)

        #HTTP/1.0 200 OK
        response =  s.makefile("rb", newline="\r\n")
        statusline = response.readline().decode("utf8")
        version, status, explanation = statusline.split(" ", 2)

        #if condition returns False, AssertionError is raised:
        assert status == "200", "{}: {}".format(status, explanation)

        #build header (response) map
        headers = {}
        while True:
            line = response.readline().decode("utf8")
            if line == "\r\n": break
            header, value = line.split(":", 1)
            #normalize header, since it is case-insensitive
            #strip value because white space is insignificat in http header values
            #strip remove leading and trailing chars, default is whitespace
            headers[header.lower()] = value.strip()

        # assert "transfer-encoding" not in headers
        # assert "content-enconding" not in headers

        body = response.read()
        body = self.decompress(body, headers).decode("utf8")

        s.close()

        return headers, body

    def decompress(self, body, headers):
        #support only gzip
        if("content-encoding" in headers):
            assert headers["content-encoding"] == "gzip", "content-encoding: {}, not supported".format(headers["content-encoding"])
            body = gzip.decompress(body)

        return body

    def lex(self, body):
        text = ""
        in_angle = False
        for c in body:
            if c == "<":
                in_angle = True
            elif c == ">":
                in_angle = False
            elif not in_angle:
               text += c
        return text

    def load(self, url):
        headers, body = self.request(url)
        text = self.lex(body)
        # self.canvas.create_rectangle(5, 5, 795, 595)
        # self.canvas.create_oval(100, 100, 160, 150)
        HSTEP, VSTEP = 13, 18
        cursor_x, cursor_y = HSTEP, VSTEP
        for c in text:
            self.canvas.create_text(cursor_x, cursor_y, text=c)
            cursor_x += HSTEP


#"...when the interpreter runs a module, the __name__ variable will be set as  __main__ if the module that is being run is the main program."
if __name__ == '__main__':
    Browser().load(sys.argv[1])
    tkinter.mainloop()
