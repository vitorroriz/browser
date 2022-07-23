import socket
import sys
import ssl
import tkinter
import tkinter.font
import zlib
from dataclasses import dataclass

#caching fonts to make use of caching system for metrics that happens on font object level
FONTS = {}

def getFont(size, weight, slant):
    key = (size, weight, slant)
    if key in FONTS:
        return FONTS[key]

    font = tkinter.font.Font(size=size, weight=weight, slant=slant)
    FONTS[key] = font
    return FONTS[key]

def getHeaderValue(values, id):
    pos = values.find(id)
    if pos == -1: return ""
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
        assert scheme in ["http", "https", "file"], "Unknown scheme {}".format(scheme)
        if scheme == "file":
            path = url
            return scheme, "", path, -1 

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

def printTree(node, indent=0):
    print("  " * indent, node)
    for child in node.children:
        printTree(child, indent + 1)

class HTMLParser:
    def __init__(self, body):
        self.body = body
        self.unfinishedTags = []
        self.SELF_CLOSING_TAGS = [
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
        ]
        self.HEAD_TAGS = [ "base", "basefont", "bgsound", "noscript", "link", "meta", "title", "style", "script"]

    #Get tag and attributes from a raw tag text 
    def getTagAndAttributes(self, text):
        #we won't handle whitespace in values, so we can split on whitespace
        parts = text.split()
        tag = parts[0].lower()
        attributes = {}

        for attPair in parts[1:]:
            #Parsing pair separated by "="
            if "=" in attPair:
                key, value = attPair.split("=", 1)
                #stripping quotes out from values
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
                attributes[key.lower()] = value
            #Value is ommited, e.g.: <input disabled>
            else:
                attributes[attPair.lower()] = ""

        return tag, attributes

    def parse(self):
        text = ""
        inTag = False

        for c in self.body:
            if c == "<":
                inTag = True
                if text: self.addText(text)
                text = ""
            elif c == ">":
                inTag = False
                self.addTag(text)
                text = ""
            else:
                text += c

        if not inTag and text:
            self.addText(text)

        return self.finish()

    def addText(self, text):
        if text.isspace(): return

        self.addImplicitTags(None)
        #text is added as child of last unfinished node
        parent = self.unfinishedTags[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def addTag(self, tag):
        #we won't be handling tags with '!' prefix like !doctype or comments
        if tag.startswith("!"): return

        tag, attributes = self.getTagAndAttributes(tag)
        self.addImplicitTags(tag)
        
        if tag.startswith("/"):
            #closing tag needs to remove and finish last unfinished node
            if len(self.unfinishedTags) == 1: return #last tag won't be poped, so we won't loose it, finish will pop it

            node = self.unfinishedTags.pop()
            parent = self.unfinishedTags[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinishedTags[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            #open tag will add to unfinished tags list
            parent = self.unfinishedTags[-1] if self.unfinishedTags else None
            node = Element(tag, attributes, parent)
            self.unfinishedTags.append(node)

    def finish(self):
        if len(self.unfinishedTags) == 0:
            #note: what is this?
            self.addTag("html")
        while len(self.unfinishedTags) > 1:
            #are we fixed a ill-formed document here?
            node = self.unfinishedTags.pop()
            parent = self.unfinishedTags[-1]
            parent.children.append(node)

        return self.unfinishedTags.pop() #pops the root node

    def addImplicitTags(self, tag):
        # "implicit_tags has a loop because more than one tag could have been omitted in a row; every iteration around the loop will add just one."
        while True:
            openTags = [node.tag for node in self.unfinishedTags]

            if openTags == [] and tag != "html":
                self.addTag("html")
            elif openTags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.addTag("head")
                else:
                    self.addTag("body")
            elif openTags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.addTag("/head")
            # /body and /html can also be implicit but self.finished() will close them
            else:
                break

class Text:
    def __init__(self, text, parent=None):
        self.text = text
        self.children = []
        self.parent = parent
    
    def __repr__(self) -> str:
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent=None):
        self.tag = tag 
        self.children = []
        self.parent = parent
        self.attributes = attributes

    def __repr__(self) -> str:
        return "<" + self.tag + ">"

class Layout:
    def __init__(self, tree, HSTEP, VSTEP, WIDTH):
        self.display_list = []
        self.line = []
        self.cursor_x, self.cursor_y = HSTEP, VSTEP
        self.weight = "normal"
        self.style = "roman"
        self.in_body = False
        self.HSTEP = HSTEP
        self.VSTEP = VSTEP
        self.WIDTH = WIDTH
        self.inBody = False

        self.processNode(tree)
        #in case tokens didn't reach flush condition, let's force a flush here
        self.flush()

    def processNode(self, tree):
        if isinstance(tree, Text):
            self.processText(tree)
        else: #tag
            self.openTag(tree.tag)
            for child in tree.children:
                self.processNode(child)
            self.closeTag(tree.tag)
    
    def openTag(self, tag):
        if tag == "body":
            self.inBody = True
        elif tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "br":
            self.flush()
        elif tag == "p":
            self.flush()
            self.cursor_y += self.VSTEP

    def closeTag(self, tag):
        if tag == "body":
            self.inBody = False 
        elif tag == "i":
            self.style = "roman"
        elif tag == "b":
            self.weight = "normal" 

    def processText(self, token):
        if not self.inBody: return #let's just layout text within <body>
        # font = tkinter.font.Font(size=16, weight=self.weight, slant=self.style)
        font = getFont(size=16, weight=self.weight, slant=self.style)
        whiteSpaceSpace = font.measure(" ")
        wordList = token.text.split(' ')

        for word in wordList:
            if word == '': continue
            wordWidth = font.measure(word)
            hasNewLineCharacter = '\n' in word
            if self.cursor_x + wordWidth > self.WIDTH - self.HSTEP:
                self.flush()

            self.line.append((self.cursor_x, word, font))
            self.cursor_x += wordWidth + whiteSpaceSpace 

            if(hasNewLineCharacter):
                self.flush()
    
    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font in self.line]
        maxAscent = max(metric["ascent"] for metric in metrics)
        #todo: move magic constants somhere nice
        # 1.25 factor for upper leading
        baseline = self.cursor_y + 1.25 * maxAscent

        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))

        self.cursor_x = self.HSTEP
        self.line = []
        maxDescent = max(metric["descent"] for metric in metrics)
        # 1.25 factor for bottom leading
        self.cursor_y = baseline + 1.25 * maxDescent

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

    def request(self, url: Url):
        s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        s.setblocking(True)

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
            charsetFromHeader = getHeaderValue(responseHeaderMap['content-type'], 'charset=')
            charset = charsetFromHeader if charsetFromHeader else charset

        body = body.decode(charset)

        s.close()

        return body

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
        data = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(data)
        return data 

    def getFileContent(self, url: Url):
        file = open(url.path, "r")
        content = file.read()
        file.close()
        return content

    def getUrlContent(self, url: Url):
        scheme = url.scheme
        if(scheme == "http" or scheme == "https"):
            return self.request(url)
        elif(scheme == "file"):
            return self.getFileContent(url)
        else:
            raise NameError("Scheme {} is not supported".format(url.scheme))
            
    def load(self, url):
        url = Url(url)
        text = self.getUrlContent(url)
        # tokens = self.lex(text)
        self.nodes = HTMLParser(text).parse()
        printTree(self.nodes)
        self.display_list = Layout(self.nodes, self.HSTEP, self.VSTEP, self.WIDTH).display_list
        self.draw()
    
    def redraw(self):
        self.canvas.delete("all")
        self.draw()

    def draw(self):
        for x, y, text, font in self.display_list:
            if y > self.scroll + self.HEIGHT: continue
            if y + self.VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=text, anchor="nw", font=font)
    
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
    browser = Browser()
    url = Url(sys.argv[1])
    browser.load(url.url)
    tkinter.mainloop()