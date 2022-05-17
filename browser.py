import socket
import sys
import ssl
import tkinter
import tkinter.font
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
        self.WIDTH = 800
        self.HEIGHT = 600
        self.HSTEP = 9 
        self.VSTEP = 18
        self.LINE_BREAK_STEP = 1.5 * self.VSTEP
        self.display_list = []
        self.scroll = 0
        self.SCROLL_STEP = 18 

        self.window = tkinter.Tk()
        #font hard-coded for now, later it has to come from css properties
        self.font = tkinter.font.Font(family="Times", size=16)

        self.window.bind("<Down>", self.onScrollDown)
        self.window.bind("<Up>", self.onScrollUp)
        self.window.bind("<MouseWheel>", self.onMouseWheel)

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
        requestHeaders = ""
        if requestHeadersMap:
            for key in requestHeadersMap:
                requestHeaders += key + ": " + requestHeadersMap[key] + "\r\n"
        else:
            requestHeaders = "\r\n"

        requestHeaders += "\r\n"
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
    
    def layout(self, text):
        display_list = []
        cursor_x, cursor_y = self.HSTEP, self.VSTEP
        wordList = text.split(' ')
        lineSpace = self.font.metrics("linespace")
        whiteSpaceSpace = self.font.measure(" ")
        for word in wordList:
            wordWidth = self.font.measure(word)

            hasNewLineCharacter = '\n' in word
            if cursor_x + wordWidth > self.WIDTH - self.HSTEP:
                cursor_x = self.HSTEP
                cursor_y +=  lineSpace

            if word != '':
                display_list.append((cursor_x, cursor_y, word))

            cursor_x += wordWidth + 1 * whiteSpaceSpace 
            
            if(hasNewLineCharacter):
                cursor_x = self.HSTEP
                cursor_y +=  lineSpace * 1.25

        return display_list

    def load(self, url):
        headers, body = self.request(url)
        text = self.lex(body)
        self.display_list = self.layout(text)
        self.draw()
    
    def redraw(self):
        self.canvas.delete("all")
        self.draw()

    def draw(self):
        for x, y, c in self.display_list:
            if y > self.scroll + self.HEIGHT: continue
            if y + self.VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=c, anchor="nw", font=self.font)
    
    def scrollDown(self, nTimes):
        self.scroll += nTimes * self.SCROLL_STEP
        self.redraw()
    
    def scrollUp(self, nTimes):
        self.scroll -= nTimes * self.SCROLL_STEP
        if self.scroll < 0:
            self.scroll = 0
        self.redraw()
    
    def onScrollDown(self, e):
        self.scrollDown(1)

    def onScrollUp(self, e):
        self.scrollUp(1)

    def onMouseWheel(self, e):
        #todo: add support for linux and mac platforms since delta module, delta sign and event might differ.
        if e.delta > 0:
            self.scrollUp(e.delta / 120)
        else:
            self.scrollDown(-e.delta / 120)

#"...when the interpreter runs a module, the __name__ variable will be set as  __main__ if the module that is being run is the main program."
if __name__ == '__main__':
    Browser().load(sys.argv[1])
    tkinter.mainloop()