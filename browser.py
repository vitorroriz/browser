import socket
import sys
import ssl

def parse(url):
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

def request(url):
    s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)

    scheme, host, path, port = parse(url)

    #if it is https, let's wrap the socket with ssl library
    if scheme == "https":
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(s, server_hostname=host)

    s.connect((host, port))

    # GET /index.html HTTP/1.0
    # Host: example.org
    #
    #there is actually an empty lines indicating end of the request
    requestUtf8 = "GET {} HTTP/1.1\r\n".format(path).encode("utf8") + "Host: {}\r\nConnection: {}\r\n\r\n".format(host, "close").encode("utf8")
    s.send(requestUtf8)

    #HTTP/1.0 200 OK
    response =  s.makefile("r", encoding="utf8", newline="\r\n")
    statusline = response.readline()
    version, status, explanation = statusline.split(" ", 2)

    #if condition returns False, AssertionError is raised:
    assert status == "200", "{}: {}".format(status, explanation)

    #build header (response) map
    headers = {}
    while True:
        line = response.readline()
        if line == "\r\n": break
        header, value = line.split(":", 1)
        #normalize header, since it is case-insensitive
        #strip value because white space is insignificat in http header values
        #strip remove leading and trailing chars, default is whitespace
        headers[header.lower()] = value.strip()

    assert "transfer-encoding" not in headers
    assert "content-enconding" not in headers

    body = response.read()
    s.close()

    return headers, body

def show(body):
    in_angle = False
    for c in body:
        if c == "<":
            in_angle = True
        elif c == ">":
            in_angle = False
        elif not in_angle:
            print(c, end="")

def load(url):
    headers, body = request(url)
    show(body)

#"...when the interpreter runs a module, the __name__ variable will be set as  __main__ if the module that is being run is the main program."
if __name__ == '__main__':
    load(sys.argv[1])
