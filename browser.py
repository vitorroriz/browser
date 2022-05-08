import socket
import sys
import ssl
import tkinter
import gzip

def getHeaderValue(values, id):
    pos = values.find(id)
    values = values[pos + len(id):]
    pos = values.find(' ') 
    if pos == -1: return values
    return values[:pos]

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
        s.setblocking(True)

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

        requestHeadersMap = {"Host": url.host, "Connection": "close", "User-Agent": "Mr. Vivi", "Accept-Encoding": "gzip"}
        # print(headersMap)
        requestHeaders = ""
        if requestHeadersMap:
            for key in requestHeadersMap:
                requestHeaders += key + ": " + requestHeadersMap[key] + "\r\n"
        else:
            requestHeaders = "\r\n"

        requestHeaders += "\r\n"
        # print(headers) 
        requestHeaders = requestHeaders.encode("utf8")

        request += requestHeaders
        s.send(request)

        #HTTP/1.0 200 OK
        response =  s.makefile("rb", newline="\r\n")
        statusline = response.readline().decode("utf8")
        version, status, explanation = statusline.split(" ", 2)

        #if condition returns False, AssertionError is raised:
        assert status == "200", "{}: {}".format(status, explanation)

        #build header (response) map
        responseHeaderMap = {}
        while True:
            line = response.readline().decode("utf8")
            if line == "\r\n": break
            key, value = line.split(":", 1)
            #normalize header, since it is case-insensitive
            #strip value because white space is insignificat in http header values
            #strip remove leading and trailing chars, default is whitespace
            responseHeaderMap[key.lower()] = value.strip()

        body = bytearray() 
        if "transfer-encoding" in responseHeaderMap:
            body = self.decodeTransfer(response, responseHeaderMap)
        else:
            body = response.read()

        if "content-encoding" in responseHeaderMap:
            body = self.decodeContent(body, responseHeaderMap)

        charset = 'utf-8'
        if 'content-type' in responseHeaderMap:
            charset = getHeaderValue(responseHeaderMap['content-type'], 'charset=')

        body = body.decode(charset)

        s.close()

        return responseHeaderMap, body

    # Transfer-Encoding is a hop-by-hop header, that is applied to a message between two nodes, not to a resource itself. Each segment of a multi-node connection can use different Transfer-Encoding values. If you want to compress data over the whole connection, use the end-to-end Content-Encoding header instead.
    def decodeTransfer(self, response, headers):
        assert headers["transfer-encoding"] == "chunked", "transfer-encoding: {}, not supported".format(headers["transfer-encoding"])

        data = bytearray() 
        while(True):
            line = response.readline()
            sz = int(line, 16) 
            if sz == 0:
                break
            chunk = response.read(sz)
            data += chunk
            crlf = response.readline()
        return data 

    def decodeContent(self, data, headers):
        assert headers["content-encoding"] == "gzip", "content-encoding: {}, not supported".format(headers["content-encoding"])
        data = gzip.decompress(data)
        return data 

    def lex(self, data):
        text = ""
        in_angle = False
        in_body = False
        tagContent = ""
        tag = ""
        copyToTag = False
        for c in data:
            if c == "<":
                in_angle = True
                tagContent = ""
                tag = ""
                copyToTag = True
            elif c == ">":
                # print("@@tag=" + tag) 
                in_angle = False
                if tag == "/body":
                    break
                if tag == "body":
                    in_body = True
            elif in_angle:
                if copyToTag and c != " ":
                    tag += c
                elif copyToTag and c == " ": 
                    copyToTag = False

                tagContent += c
            elif not in_angle:
                if in_body:
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
