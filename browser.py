import socket

def parse(url):
    protocol = "http://"
    assert url.startswith(protocol)
    url = url[len(protocol):]
    host, path = url.split("/", 1) #1 here is the number of occurrences to use for split
    path = "/" + path #adding "/" back to path
    return host, path




def main():
    url = "http://example.org/index.html"
    host, path = parse(url)
    print ("host: ", host)
    print ("path: ", path)

    s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)

    s.connect((host, 80))

    request = "GET {} HTTP/1.0\r\n".format(path).encode("utf8") + "Host: {}\r\n\r\n".format(host).encode("utf8")
    sentBytes = s.send(request)
    print(sentBytes) 

    response =  s.makefile("r", encoding="utf8", newline="\r\n")
    statusline = response.readline()
    version, status, explanation = statusline.split(" ", 2)

    #if condition returns False, AssertionError is raised:
    assert status == "200", "{}: {}".format(status, explanation)

    #build header map
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

    print(body)

if __name__ == '__main__':
    main()
