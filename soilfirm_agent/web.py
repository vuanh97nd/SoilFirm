import re, time, requests
from io import BytesIO
def search_web_duckduckgo(query, cancel=None, search_factory=None):
    """Search on the desktop; only the question goes to the search service."""
    from datetime import datetime, timezone
    from html import unescape
    from urllib.parse import urlsplit
    query = str(query or '').strip()
    if not query or len(query) > 2000:
        raise ValueError('Câu hỏi tra cứu phải có từ 1 đến 2000 ký tự.')

    def stopped():
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Đã dừng tra cứu mạng.')
    stopped()
    backend = 'duckduckgo'
    if search_factory is None:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
                backend = 'html'
            except ImportError:
                raise ValueError('Chưa có thư viện tra cứu miễn phí. Cài trong môi trường chạy SoilFirm: python -m pip install -U ddgs. Nếu dùng EXE, cần bản đóng gói đã bổ sung ddgs.') from None
        search_factory = DDGS
    try:
        client = search_factory(timeout=12)
        try:
            found = client.text(query, backend=backend, max_results=5, safesearch='moderate')
            rows = []
            for item in found:
                stopped()
                rows.append(item)
                if len(rows) >= 5:
                    break
        finally:
            close = getattr(client, 'close', None)
            if callable(close):
                close()
    except InterruptedError:
        raise
    except Exception as exc:
        stopped()
        kind = type(exc).__name__.lower()
        message = 'DuckDuckGo đang giới hạn truy cập. Đợi một chút rồi thử lại.' if 'ratelimit' in kind else 'DuckDuckGo quá thời gian chờ. Kiểm tra mạng và thử lại.' if 'timeout' in kind else 'Chưa lấy được kết quả DuckDuckGo. Kiểm tra mạng hoặc cập nhật ddgs rồi thử lại.'
        raise ValueError(message) from None
    stopped()

    def clean(value):
        return re.sub('\\s+', ' ', unescape(re.sub('<[^>]*>', ' ', str(value or '')))).strip()
    sources = []
    parts = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        link = str(item.get('href') or item.get('url') or '').strip()
        try:
            parsed = urlsplit(link)
        except ValueError:
            continue
        if parsed.scheme not in ('https', 'http') or not parsed.netloc or link in seen:
            continue
        snippet = clean(item.get('body') or item.get('description'))[:350]
        if not snippet:
            continue
        title = clean(item.get('title') or parsed.hostname)[:150]
        seen.add(link)
        sources.append({'title': title, 'url': link})
        parts.append('[' + str(len(sources)) + '] ' + title + '\n' + snippet + '\nNguồn: ' + link)
    if not sources:
        raise ValueError('DuckDuckGo chưa tìm thấy trích đoạn có nguồn. Hãy đổi từ khóa tra cứu.')
    return {'success': True, 'answer': 'Trích đoạn tìm kiếm, chưa phải toàn văn tài liệu; không tự khẳng định điều khoản tiêu chuẩn.\n' + '\n\n'.join(parts), 'sources': sources, 'source': 'duckduckgo', 'searched_at': datetime.now(timezone.utc).isoformat()}

def read_web_source(url, cancel=None, session=None):
    """Read bounded public HTML/PDF content without sending account credentials."""
    import ipaddress, socket
    from urllib.parse import urlsplit, urljoin
    from html.parser import HTMLParser

    def stopped():
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Đã dừng đọc nguồn.')

    def public(link):
        parsed = urlsplit(link)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Nguồn không phải URL web công khai.')
        if parsed.port not in (None, 80, 443):
            raise ValueError('Cổng nguồn không được hỗ trợ.')
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if not addresses or any((not ipaddress.ip_address(a[4][0]).is_global for a in addresses)):
            raise ValueError('Không đọc địa chỉ mạng nội bộ từ kết quả tìm kiếm.')
    owned = session is None
    if owned:
        session = requests.Session()
        session.trust_env = False
    response = None
    started = time.monotonic()
    try:
        for _ in range(5):
            stopped()
            public(url)
            response = session.get(url, timeout=(4, 10), stream=True, allow_redirects=False, headers={'User-Agent': 'SoilFirm/2026.11 SourceReader', 'Accept': 'text/html,application/pdf,text/plain'})
            if response.status_code in (301, 302, 303, 307, 308):
                target = response.headers.get('Location')
                response.close()
                if not target:
                    raise ValueError('Nguồn chuyển hướng không hợp lệ.')
                url = urljoin(url, target)
                continue
            break
        else:
            raise ValueError('Nguồn chuyển hướng quá nhiều lần.')
        if response.status_code != 200:
            raise ValueError('Nguồn trả HTTP ' + str(response.status_code))
        chunks = []
        size = 0
        for chunk in response.iter_content(65536):
            stopped()
            if time.monotonic() - started > 20:
                raise ValueError('Nguồn quá thời gian đọc.')
            size += len(chunk)
            if size > 8 * 1024 * 1024:
                raise ValueError('Nguồn vượt giới hạn đọc 8 MB.')
            chunks.append(chunk)
        content = b''.join(chunks)
        kind = response.headers.get('Content-Type', '').lower()
        blocks = []
        pdf_links = []
        if content.startswith(b'%PDF-') or 'application/pdf' in kind:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted and (not reader.decrypt('')):
                raise ValueError('PDF có mật khẩu.')
            for page_number, page in enumerate(reader.pages):
                stopped()
                if page_number >= 100 or time.monotonic() - started > 25:
                    break
                text = page.extract_text() or ''
                if text.strip():
                    blocks.append(('Trang ' + str(page_number + 1), text[:20000]))
            if not blocks:
                raise ValueError('PDF dạng ảnh chưa có văn bản; cần OCR hoặc gửi trang ảnh.')
            return {'url': url, 'kind': 'pdf', 'blocks': blocks, 'pdf_links': []}
        if not any((t in kind for t in ('text/', 'html', 'xml'))):
            raise ValueError('Nguồn không phải trang văn bản hoặc PDF.')
        encoding = response.encoding if response.encoding and response.encoding.lower() != 'iso-8859-1' else 'utf-8'
        text = content.decode(encoding, errors='replace')
        if 'html' in kind:

            class Reader(HTMLParser):

                def __init__(self):
                    super().__init__()
                    self.skip = 0
                    self.parts = []
                    self.links = []

                def handle_starttag(self, tag, attrs):
                    if tag in ('script', 'style', 'noscript', 'nav', 'footer', 'header'):
                        self.skip += 1
                    if not self.skip and tag in ('p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4'):
                        self.parts.append('\n')
                    if tag == 'a':
                        href = dict(attrs).get('href', '')
                        if '.pdf' in href.lower():
                            self.links.append(urljoin(url, href))

                def handle_endtag(self, tag):
                    if tag in ('script', 'style', 'noscript', 'nav', 'footer', 'header') and self.skip:
                        self.skip -= 1
                    if not self.skip and tag in ('p', 'div', 'li', 'tr'):
                        self.parts.append('\n')

                def handle_data(self, data):
                    if not self.skip:
                        self.parts.append(data)
            parser = Reader()
            parser.feed(text)
            text = ''.join(parser.parts)
            pdf_links = list(dict.fromkeys(parser.links))[:2]
        text = re.sub('[ \\t]+', ' ', text)
        text = re.sub('\\n\\s*\\n+', '\n', text).strip()[:160000]
        if len(text) < 100:
            raise ValueError('Trang chưa cung cấp đủ văn bản đọc được.')
        blocks = [('Nội dung trang', text)]
        return {'url': url, 'kind': 'html', 'blocks': blocks, 'pdf_links': pdf_links}
    finally:
        if response is not None:
            response.close()
        if owned:
            session.close()

def enrich_search_sources(search, query, cancel=None, progress=None, reader=None, follow_pdf=True):
    """Select relevant passages; report exactly which sources were read."""
    import unicodedata
    reader = reader or read_web_source
    sources = search.get('sources', [])
    passages = []
    notes = []
    started = time.monotonic()

    def plain(value):
        text = unicodedata.normalize('NFD', str(value).lower()).replace('đ', 'd')
        return ''.join((c for c in text if not unicodedata.combining(c)))
    words = set(re.findall('[a-z0-9]{3,}', plain(query)))
    if any((t in plain(query) for t in ('nhan biet', 'nhan dang', 'dat yeu'))):
        words.update(('yeu', 'nhan dang', 'dinh nghia', 'phan loai', 'chi tieu', 'do set', 'suc khang', 'soil'))
    attempts = list(enumerate(sources[:5], 1))
    extra = []
    for index, source in attempts:
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Đã dừng đọc nguồn.')
        if time.monotonic() - started > 50:
            break
        if progress:
            progress('Đang đọc nguồn ' + str(index) + ': ' + source.get('title', '')[:80])
        try:
            doc = reader(source['url'], cancel)
            source['read_status'] = 'read'
            source['read_url'] = doc['url']
            source['read_kind'] = doc['kind']
            blocks = []
            for label, text in doc['blocks']:
                for start in range(0, len(text), 1200):
                    chunk = text[max(0, start - 150):start + 1200]
                    score = sum((plain(chunk).count(word) for word in words))
                    blocks.append((score, label, start, chunk))
            chosen = sorted(blocks, key=lambda b: (-b[0], b[2]))[:3]
            for _, label, _, chunk in chosen:
                passages.append('[' + str(index) + '] ' + source.get('title', '') + ' · ' + label + '\nURL: ' + doc['url'] + '\n' + chunk)
            if doc.get('pdf_links') and (not extra):
                extra = [doc['pdf_links'][0]]
        except InterruptedError:
            raise
        except Exception as exc:
            source['read_status'] = 'failed'
            notes.append('[' + str(index) + '] Chưa đọc được nguồn: ' + str(exc)[:200])
    if follow_pdf and extra and (time.monotonic() - started < 45):
        link = extra[0]
        if link not in [source['url'] for source in sources]:
            child = {'title': 'PDF liên kết từ nguồn đã đọc', 'url': link}
            sources.append(child)
            sub = enrich_search_sources({'sources': [child]}, query, cancel, progress, reader, False)
            passages.append(sub['answer'].replace('[1]', '[' + str(len(sources)) + ']'))
    search['answer'] = ('NỘI DUNG ĐÃ ĐỌC TỪ NGUỒN (các đoạn chọn theo câu hỏi, không phải toàn văn):\n' + '\n\n'.join(passages) + '\n' + '\n'.join(notes))[:18000] if passages else str(search.get('answer','')) + '\n' + '\n'.join(notes)
    search['read_notes'] = notes
    return search
