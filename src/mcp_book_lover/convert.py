"""Book format conversion: epub, fb2, txt, pdf."""

import base64
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape


# ---------------------------------------------------------------------------
# Rich content model
# ---------------------------------------------------------------------------

@dataclass
class _Span:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class _Block:
    """A block-level element in a chapter."""
    kind: str  # "para" | "subtitle" | "epigraph" | "image" | "empty"
    spans: list[_Span] = field(default_factory=list)
    image_id: str = ""  # key into _RichBook.images, for kind="image"

    @classmethod
    def para(cls, spans: list[_Span]) -> "_Block":
        return cls(kind="para", spans=spans)

    @classmethod
    def subtitle(cls, text: str) -> "_Block":
        return cls(kind="subtitle", spans=[_Span(text)])

    @classmethod
    def epigraph(cls, text: str) -> "_Block":
        return cls(kind="epigraph", spans=[_Span(text, italic=True)])

    @classmethod
    def image(cls, img_id: str) -> "_Block":
        return cls(kind="image", image_id=img_id)

    @classmethod
    def empty(cls) -> "_Block":
        return cls(kind="empty")


@dataclass
class _Chapter:
    title: str = ""
    blocks: list[_Block] = field(default_factory=list)


@dataclass
class _RichBook:
    title: str = ""
    author: str = ""
    language: str = "ru"
    chapters: list[_Chapter] = field(default_factory=list)
    cover_data: bytes | None = None
    cover_mime: str = "image/jpeg"
    images: dict[str, tuple[bytes, str]] = field(default_factory=dict)  # id → (data, mime)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_book_file(input_path: str, output_format: str) -> str:
    """Convert book file to target format. Returns output file path."""
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    src_fmt = src.suffix.lstrip(".").lower()
    if src_fmt == output_format:
        raise ValueError(f"Source is already in {output_format} format.")

    dest = src.with_suffix(f".{output_format}")

    book = _parse_book(src, src_fmt)

    if output_format == "epub":
        _write_epub(book, dest)
    elif output_format == "fb2":
        _write_fb2(book, dest)
    elif output_format == "pdf":
        _write_pdf(book, dest)
    elif output_format == "txt":
        _write_txt(book, dest)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    return str(dest)


# ---------------------------------------------------------------------------
# Parsers (source → _RichBook)
# ---------------------------------------------------------------------------

def _parse_book(src: Path, fmt: str) -> _RichBook:
    if fmt == "fb2":
        return _parse_fb2(src)
    if fmt == "epub":
        return _parse_epub(src)
    if fmt == "txt":
        return _parse_txt(src)
    if fmt == "pdf":
        return _parse_pdf(src)
    raise ValueError(f"Cannot read format: {fmt}")


def _parse_fb2(src: Path) -> _RichBook:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(src.read_bytes(), "xml")
    book = _RichBook(title=src.stem)

    ti = soup.find("title-info")
    if ti:
        bt = ti.find("book-title")
        if bt:
            book.title = bt.get_text(strip=True)
        lang = ti.find("lang")
        if lang:
            book.language = lang.get_text(strip=True)
        authors = []
        for a in ti.find_all("author"):
            fn = a.find("first-name") or a.find("nickname")
            ln = a.find("last-name")
            name = " ".join(filter(None, [
                fn.get_text(strip=True) if fn else "",
                ln.get_text(strip=True) if ln else "",
            ]))
            if name:
                authors.append(name)
        book.author = ", ".join(authors)

    # Cover image
    cover_id = ""
    if ti:
        cp = ti.find("coverpage")
        if cp:
            img = cp.find("image")
            if img:
                cover_id = (img.get("l:href", "") or img.get("href", "")).lstrip("#")
                binary = soup.find("binary", attrs={"id": cover_id})
                if binary:
                    book.cover_data = base64.b64decode(binary.get_text())
                    book.cover_mime = binary.get("content-type", "image/jpeg")

    # All non-cover binary images
    for binary in soup.find_all("binary"):
        bin_id = binary.get("id", "")
        if bin_id == cover_id:
            continue
        try:
            data = base64.b64decode(binary.get_text())
            mime = binary.get("content-type", "image/jpeg")
            book.images[bin_id] = (data, mime)
        except Exception:
            pass

    # Body → chapters
    body = soup.find("body")
    if body:
        sections = body.find_all("section", recursive=False) or [body]
        for i, sec in enumerate(sections):
            ch = _Chapter()
            t = sec.find("title")
            if t:
                ch.title = t.get_text(strip=True)
                t.decompose()
            else:
                ch.title = book.title if i == 0 else f"Глава {i + 1}"
            ch.blocks = _fb2_section_to_blocks(sec)
            if ch.blocks:
                book.chapters.append(ch)

    return book


def _fb2_section_to_blocks(section) -> list[_Block]:
    blocks = []
    for el in section.children:
        if not hasattr(el, "name") or el.name is None:
            continue
        if el.name == "p":
            spans = _fb2_inline_spans(el)
            if spans:
                blocks.append(_Block.para(spans))
        elif el.name == "empty-line":
            blocks.append(_Block.empty())
        elif el.name == "subtitle":
            blocks.append(_Block.subtitle(el.get_text(strip=True)))
        elif el.name == "epigraph":
            blocks.append(_Block.epigraph(el.get_text(strip=True)))
        elif el.name == "image":
            href = el.get("l:href", "") or el.get("href", "")
            img_id = href.lstrip("#")
            if img_id:
                blocks.append(_Block.image(img_id))
        elif el.name == "section":
            sub_t = el.find("title")
            if sub_t:
                blocks.append(_Block.subtitle(sub_t.get_text(strip=True)))
                sub_t.decompose()
            blocks.extend(_fb2_section_to_blocks(el))
    return blocks


def _fb2_inline_spans(el) -> list[_Span]:
    spans = []
    for child in el.children:
        if not hasattr(child, "name") or child.name is None:
            text = str(child)
            if text:
                spans.append(_Span(text))
        elif child.name == "emphasis":
            spans.append(_Span(child.get_text(), italic=True))
        elif child.name == "strong":
            spans.append(_Span(child.get_text(), bold=True))
        else:
            text = child.get_text()
            if text:
                spans.append(_Span(text))
    return [s for s in spans if s.text]


def _parse_epub(src: Path) -> _RichBook:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    ebook = epub.read_epub(str(src))
    book = _RichBook(title=src.stem)

    titles = ebook.get_metadata("DC", "title")
    if titles:
        book.title = titles[0][0]
    creators = ebook.get_metadata("DC", "creator")
    if creators:
        book.author = ", ".join(c[0] for c in creators)
    langs = ebook.get_metadata("DC", "language")
    if langs:
        book.language = langs[0][0]

    for item in ebook.get_items():
        if item.get_type() == ebooklib.ITEM_COVER:
            book.cover_data = item.get_content()
            book.cover_mime = item.media_type or "image/jpeg"
            break

    # Build name → (data, mime) map for images
    epub_images: dict[str, tuple[bytes, str]] = {}
    for item in ebook.get_items_of_type(ebooklib.ITEM_IMAGE):
        epub_images[item.get_name()] = (item.get_content(), item.media_type or "image/jpeg")

    for html_item in ebook.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(html_item.get_content(), "html.parser")
        heading = soup.find(["h1", "h2", "h3"])
        ch_title = heading.get_text(strip=True) if heading else ""
        if heading:
            heading.decompose()

        body = soup.find("body") or soup
        blocks = _html_to_blocks(body, epub_images, book.images, html_item.get_name())
        if blocks:
            book.chapters.append(_Chapter(title=ch_title, blocks=blocks))

    return book


def _html_to_blocks(
    el,
    epub_images: dict,
    dest_images: dict,
    item_name: str,
) -> list[_Block]:
    blocks = []
    for child in el.children:
        if not hasattr(child, "name") or child.name is None:
            text = str(child).strip()
            if text:
                blocks.append(_Block.para([_Span(text)]))
            continue
        if child.name == "p":
            spans = _html_inline_spans(child, epub_images, dest_images, item_name)
            if spans:
                blocks.append(_Block.para(spans))
        elif child.name in ("h1", "h2", "h3", "h4", "h5"):
            text = child.get_text(strip=True)
            if text:
                blocks.append(_Block.subtitle(text))
        elif child.name == "blockquote":
            text = child.get_text(strip=True)
            if text:
                blocks.append(_Block.epigraph(text))
        elif child.name == "img":
            img_id = _resolve_and_store_epub_image(
                child.get("src", ""), epub_images, dest_images, item_name
            )
            if img_id:
                blocks.append(_Block.image(img_id))
        elif child.name == "br":
            blocks.append(_Block.empty())
        elif child.name in ("div", "section", "article", "main", "figure"):
            blocks.extend(_html_to_blocks(child, epub_images, dest_images, item_name))
        elif child.name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                spans = _html_inline_spans(li, epub_images, dest_images, item_name)
                if spans:
                    spans.insert(0, _Span("• "))
                    blocks.append(_Block.para(spans))
    return blocks


def _html_inline_spans(el, epub_images, dest_images, item_name) -> list[_Span]:
    spans = []
    for child in el.children:
        if not hasattr(child, "name") or child.name is None:
            text = str(child)
            if text:
                spans.append(_Span(text))
        elif child.name in ("em", "i"):
            text = child.get_text()
            if text:
                spans.append(_Span(text, italic=True))
        elif child.name in ("strong", "b"):
            text = child.get_text()
            if text:
                spans.append(_Span(text, bold=True))
        elif child.name == "br":
            spans.append(_Span("\n"))
        elif child.name == "img":
            # Inline images are uncommon but handle them
            _resolve_and_store_epub_image(
                child.get("src", ""), epub_images, dest_images, item_name
            )
        elif child.name in ("span", "a", "sup", "sub", "cite", "code"):
            spans.extend(_html_inline_spans(child, epub_images, dest_images, item_name))
        else:
            text = child.get_text()
            if text:
                spans.append(_Span(text))
    return [s for s in spans if s.text]


def _resolve_and_store_epub_image(src: str, epub_images: dict, dest_images: dict, item_name: str) -> str:
    """Resolve relative src, copy into dest_images dict, return key (or '')."""
    if not src:
        return ""
    base = posixpath.dirname(item_name)
    resolved = posixpath.normpath(posixpath.join(base, src)) if base else src
    resolved = resolved.lstrip("/")
    key = resolved if resolved in epub_images else src.lstrip("/")
    if key not in epub_images:
        return ""
    if key not in dest_images:
        dest_images[key] = epub_images[key]
    return key


def _parse_txt(src: Path) -> _RichBook:
    text = src.read_text(encoding="utf-8", errors="replace")
    paras = [l.strip() for l in text.split("\n") if l.strip()]
    title = paras[0] if paras else src.stem
    blocks = [_Block.para([_Span(p)]) for p in paras]
    return _RichBook(title=title, chapters=[_Chapter(title="", blocks=blocks)])


def _parse_pdf(src: Path) -> _RichBook:
    from pypdf import PdfReader

    reader = PdfReader(str(src))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    paras = [l.strip() for l in text.split("\n") if l.strip()]
    title = paras[0] if paras else src.stem
    blocks = [_Block.para([_Span(p)]) for p in paras]
    return _RichBook(title=title, chapters=[_Chapter(title="", blocks=blocks)])


# ---------------------------------------------------------------------------
# Writers (_RichBook → target format)
# ---------------------------------------------------------------------------

def _write_epub(book: _RichBook, dest: Path):
    from ebooklib import epub

    ebook = epub.EpubBook()
    ebook.set_title(book.title)
    ebook.set_language(book.language)
    if book.author:
        ebook.add_author(book.author)
    if book.cover_data:
        ext = "png" if "png" in book.cover_mime else "jpg"
        ebook.set_cover(f"cover.{ext}", book.cover_data)

    # Register all images
    key_to_path: dict[str, str] = {}
    for img_key, (img_data, img_mime) in book.images.items():
        safe = _safe_id(img_key)
        img_item = epub.EpubImage()
        img_item.file_name = f"images/{safe}"
        img_item.media_type = img_mime
        img_item.content = img_data
        ebook.add_item(img_item)
        key_to_path[img_key] = f"images/{safe}"

    spine = ["nav"]
    epub_chapters = []
    for i, ch in enumerate(book.chapters):
        title = ch.title or f"Chapter {i + 1}"
        body_html = _blocks_to_html(ch.blocks, key_to_path)
        item = epub.EpubHtml(title=title, file_name=f"ch_{i:03d}.xhtml", lang=book.language)
        item.set_content(
            f'<html><head><title>{_xml_escape(title)}</title></head>'
            f'<body><h2>{_xml_escape(title)}</h2>{body_html}</body></html>'
        )
        ebook.add_item(item)
        epub_chapters.append(item)
        spine.append(item)

    ebook.toc = epub_chapters
    ebook.add_item(epub.EpubNcx())
    ebook.add_item(epub.EpubNav())
    ebook.spine = spine
    epub.write_epub(str(dest), ebook)


def _blocks_to_html(blocks: list[_Block], img_paths: dict) -> str:
    parts = []
    for block in blocks:
        if block.kind == "para":
            inner = "".join(_span_to_html(s) for s in block.spans)
            parts.append(f"<p>{inner}</p>")
        elif block.kind == "subtitle":
            text = _xml_escape(block.spans[0].text if block.spans else "")
            parts.append(f"<h3>{text}</h3>")
        elif block.kind == "epigraph":
            text = _xml_escape(block.spans[0].text if block.spans else "")
            parts.append(f"<blockquote><em>{text}</em></blockquote>")
        elif block.kind == "image":
            path = img_paths.get(block.image_id, "")
            if path:
                parts.append(f'<p><img src="{path}" alt=""/></p>')
        elif block.kind == "empty":
            parts.append("<br/>")
    return "\n".join(parts)


def _span_to_html(span: _Span) -> str:
    text = _xml_escape(span.text)
    if span.bold:
        text = f"<strong>{text}</strong>"
    if span.italic:
        text = f"<em>{text}</em>"
    return text


def _write_fb2(book: _RichBook, dest: Path):
    def e(s: str) -> str:
        return _xml_escape(s or "")

    parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    parts.append('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">')
    parts.append("  <description><title-info>")
    if book.author:
        name_parts = book.author.split(" ", 1)
        fn, ln = name_parts[0], (name_parts[1] if len(name_parts) > 1 else "")
        parts.append(f"    <author><first-name>{e(fn)}</first-name><last-name>{e(ln)}</last-name></author>")
    parts.append(f"    <book-title>{e(book.title)}</book-title>")
    parts.append(f"    <lang>{e(book.language)}</lang>")
    if book.cover_data:
        parts.append('    <coverpage><image l:href="#_cover"/></coverpage>')
    parts.append("  </title-info></description>")
    parts.append("  <body>")
    for ch in book.chapters:
        parts.append("    <section>")
        if ch.title:
            parts.append(f"      <title><p>{e(ch.title)}</p></title>")
        for block in ch.blocks:
            line = _block_to_fb2(block)
            if line:
                parts.append(f"      {line}")
        parts.append("    </section>")
    parts.append("  </body>")
    if book.cover_data:
        b64 = base64.b64encode(book.cover_data).decode()
        parts.append(f'  <binary id="_cover" content-type="{e(book.cover_mime)}">{b64}</binary>')
    for img_key, (img_data, img_mime) in book.images.items():
        safe = _safe_id(img_key)
        b64 = base64.b64encode(img_data).decode()
        parts.append(f'  <binary id="{safe}" content-type="{e(img_mime)}">{b64}</binary>')
    parts.append("</FictionBook>")
    dest.write_text("\n".join(parts), encoding="utf-8")


def _block_to_fb2(block: _Block) -> str:
    if block.kind == "para":
        inner = "".join(_span_to_fb2(s) for s in block.spans)
        return f"<p>{inner}</p>"
    if block.kind == "subtitle":
        text = _xml_escape(block.spans[0].text if block.spans else "")
        return f"<subtitle>{text}</subtitle>"
    if block.kind == "epigraph":
        text = _xml_escape(block.spans[0].text if block.spans else "")
        return f"<epigraph><p><emphasis>{text}</emphasis></p></epigraph>"
    if block.kind == "image":
        safe = _safe_id(block.image_id)
        return f'<image l:href="#{safe}"/>'
    if block.kind == "empty":
        return "<empty-line/>"
    return ""


def _span_to_fb2(span: _Span) -> str:
    text = _xml_escape(span.text)
    if span.italic:
        text = f"<emphasis>{text}</emphasis>"
    if span.bold:
        text = f"<strong>{text}</strong>"
    return text


def _write_pdf(book: _RichBook, dest: Path):
    try:
        from fpdf import FPDF
    except ImportError:
        raise ImportError("fpdf2 is required for PDF output: pip install fpdf2")

    import io

    pdf = FPDF(orientation="P", format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)

    fonts = _find_unicode_fonts()
    if fonts:
        pdf.add_font("Book", fname=fonts["regular"])
        pdf.add_font("Book", style="B", fname=fonts["bold"])
        pdf.add_font("Book", style="I", fname=fonts["italic"])
        FONT = "Book"
    else:
        FONT = "Helvetica"

    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Title page
    pdf.add_page()
    pdf.ln(50)
    pdf.set_font(FONT, style="B", size=24)
    pdf.multi_cell(0, 14, book.title, align="C")
    if book.author:
        pdf.ln(10)
        pdf.set_font(FONT, style="B", size=16)
        pdf.multi_cell(0, 10, book.author, align="C")

    for ch in book.chapters:
        pdf.add_page()
        if ch.title:
            pdf.set_font(FONT, style="B", size=16)
            pdf.multi_cell(0, 10, ch.title)
            pdf.ln(6)

        for block in ch.blocks:
            if block.kind == "para":
                # Write spans inline with per-span formatting
                for span in block.spans:
                    style = "B" if span.bold else ("I" if span.italic else "")
                    pdf.set_font(FONT, style=style, size=12)
                    pdf.write(7, span.text)
                pdf.ln(9)

            elif block.kind == "subtitle":
                text = block.spans[0].text if block.spans else ""
                pdf.ln(4)
                pdf.set_font(FONT, style="B", size=14)
                pdf.multi_cell(0, 9, text)
                pdf.ln(2)

            elif block.kind == "epigraph":
                text = block.spans[0].text if block.spans else ""
                pdf.set_font(FONT, style="I", size=12)
                pdf.set_x(pdf.l_margin + 20)
                pdf.multi_cell(page_w - 20, 7, text)
                pdf.ln(2)

            elif block.kind == "image":
                if block.image_id in book.images:
                    img_data, img_mime = book.images[block.image_id]
                    try:
                        ext = "PNG" if "png" in img_mime else "JPEG"
                        pdf.image(io.BytesIO(img_data), x=None, y=None, w=min(page_w, 150), type=ext)
                        pdf.ln(4)
                    except Exception:
                        pass

            elif block.kind == "empty":
                pdf.ln(5)

    pdf.output(str(dest))


def _find_unicode_fonts() -> dict:
    """Find regular, bold, italic Unicode TTF files. Returns {} if none found."""
    families = [
        # Linux — DejaVu (full Cyrillic + bold + italic)
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ),
        (
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf",
        ),
        # macOS — Arial in Supplemental (Cyrillic support)
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        ),
        # macOS — Arial Unicode (no separate bold/italic, falls back to regular)
        (
            "/Library/Fonts/Arial Unicode.ttf",
            None,
            None,
        ),
        # Windows
        (
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/ariali.ttf",
        ),
    ]
    for regular, bold, italic in families:
        if not regular or not Path(regular).exists():
            continue
        return {
            "regular": regular,
            "bold": bold if bold and Path(bold).exists() else regular,
            "italic": italic if italic and Path(italic).exists() else regular,
        }
    return {}


def _write_txt(book: _RichBook, dest: Path):
    chunks = []
    if book.title:
        chunks.append(book.title)
    if book.author:
        chunks.append(book.author)
    for ch in book.chapters:
        if ch.title:
            chunks.append(f"\n{ch.title}")
        for block in ch.blocks:
            if block.kind in ("para", "subtitle", "epigraph"):
                text = "".join(s.text for s in block.spans)
                if text.strip():
                    chunks.append(text)
    dest.write_text("\n\n".join(chunks), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_id(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
