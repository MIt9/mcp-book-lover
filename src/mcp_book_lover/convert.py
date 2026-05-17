"""Book format conversion: epub, fb2, txt, pdf."""

import base64
from pathlib import Path


def convert_book_file(input_path: str, output_format: str) -> str:
    """Convert book file to target format. Returns output file path."""
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    src_format = src.suffix.lstrip(".").lower()
    if src_format == output_format:
        raise ValueError(f"Source is already in {output_format} format.")

    dest = src.with_suffix(f".{output_format}")

    if src_format == "fb2" and output_format == "epub":
        _fb2_to_epub(src, dest)
        return str(dest)

    # Fallback: extract text and write
    text = _extract_text(src, src_format)
    _write_format(dest, output_format, text, title=src.stem)
    return str(dest)


def _fb2_to_epub(src: Path, dest: Path):
    """Convert FB2 to EPUB preserving cover, metadata, and chapters."""
    from bs4 import BeautifulSoup
    from ebooklib import epub

    content = src.read_bytes()
    soup = BeautifulSoup(content, "xml")

    book = epub.EpubBook()

    # --- Metadata ---
    title_info = soup.find("title-info")
    title = ""
    if title_info:
        bt = title_info.find("book-title")
        title = bt.get_text(strip=True) if bt else src.stem
        book.set_title(title)

        lang = title_info.find("lang")
        book.set_language(lang.get_text(strip=True) if lang else "ru")

        # Authors
        for author_tag in title_info.find_all("author"):
            fn = author_tag.find("first-name")
            ln = author_tag.find("last-name")
            name = " ".join(filter(None, [
                fn.get_text(strip=True) if fn else "",
                ln.get_text(strip=True) if ln else ""
            ]))
            if name:
                book.add_author(name)

        # Annotation as description
        annotation = title_info.find("annotation")
        if annotation:
            book.add_metadata("DC", "description", annotation.get_text(strip=True))

    if not title:
        title = src.stem
        book.set_title(title)

    # --- Cover image ---
    cover_added = False
    coverpage = soup.find("coverpage")
    if coverpage:
        img_tag = coverpage.find("image")
        if img_tag:
            href = img_tag.get("l:href", "") or img_tag.get("href", "")
            href_id = href.lstrip("#")
            binary = soup.find("binary", attrs={"id": href_id})
            if binary:
                img_data = base64.b64decode(binary.get_text())
                ct = binary.get("content-type", "image/jpeg")
                ext = "jpg" if "jpeg" in ct or "jpg" in ct else "png"
                cover_name = f"cover.{ext}"
                book.set_cover(cover_name, img_data)
                cover_added = True

    # --- Chapters ---
    body = soup.find("body")
    chapters = []
    spine = ["nav"]

    if body:
        sections = body.find_all("section", recursive=False)
        if not sections:
            sections = [body]

        for i, section in enumerate(sections):
            # Get chapter title
            section_title = title if i == 0 and not section.find("title") else ""
            title_tag = section.find("title")
            if title_tag:
                section_title = title_tag.get_text(strip=True)
                title_tag.decompose()

            if not section_title:
                section_title = f"Глава {i + 1}"

            # Convert section content to HTML
            html_content = _section_to_html(section, soup)

            ch = epub.EpubHtml(
                title=section_title,
                file_name=f"chapter_{i:03d}.xhtml",
                lang="ru"
            )
            ch.set_content(
                f'<html><head><title>{section_title}</title></head>'
                f'<body><h2>{section_title}</h2>{html_content}</body></html>'
            )
            book.add_item(ch)
            chapters.append(ch)
            spine.append(ch)

    # --- Inline images (non-cover) ---
    for binary in soup.find_all("binary"):
        bin_id = binary.get("id", "")
        if cover_added and coverpage:
            cover_href = coverpage.find("image")
            if cover_href:
                cover_id = (cover_href.get("l:href", "") or cover_href.get("href", "")).lstrip("#")
                if bin_id == cover_id:
                    continue
        ct = binary.get("content-type", "image/jpeg")
        img_data = base64.b64decode(binary.get_text())
        img_item = epub.EpubImage()
        img_item.file_name = f"images/{bin_id}"
        img_item.media_type = ct
        img_item.content = img_data
        book.add_item(img_item)

    # --- TOC and navigation ---
    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub.write_epub(str(dest), book)


def _section_to_html(section, soup) -> str:
    """Convert FB2 section content to HTML paragraphs with images."""
    parts = []
    for el in section.children:
        if not hasattr(el, "name") or el.name is None:
            continue
        if el.name == "p":
            text = el.get_text()
            if text.strip():
                parts.append(f"<p>{text}</p>")
        elif el.name == "empty-line":
            parts.append("<br/>")
        elif el.name == "image":
            href = el.get("l:href", "") or el.get("href", "")
            href_id = href.lstrip("#")
            parts.append(f'<p><img src="images/{href_id}" alt=""/></p>')
        elif el.name == "subtitle":
            parts.append(f"<h3>{el.get_text()}</h3>")
        elif el.name == "epigraph":
            parts.append(f'<blockquote><em>{el.get_text()}</em></blockquote>')
        elif el.name == "section":
            # Nested section
            sub_title = el.find("title")
            if sub_title:
                parts.append(f"<h3>{sub_title.get_text(strip=True)}</h3>")
                sub_title.decompose()
            parts.append(_section_to_html(el, soup))
    return "\n".join(parts)


# --- Legacy functions for other formats ---

def _extract_text(path: Path, fmt: str) -> str:
    if fmt == "txt":
        return path.read_text(encoding="utf-8")
    if fmt == "epub":
        return _extract_epub(path)
    if fmt == "pdf":
        return _extract_pdf(path)
    if fmt == "fb2":
        return _extract_fb2_text(path)
    raise ValueError(f"Cannot read format: {fmt}")


def _extract_epub(path: Path) -> str:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(str(path))
    texts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        texts.append(soup.get_text(separator="\n"))
    return "\n\n".join(texts)


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_fb2_text(path: Path) -> str:
    from bs4 import BeautifulSoup
    content = path.read_bytes()
    soup = BeautifulSoup(content, "xml")
    body = soup.find("body")
    if not body:
        return soup.get_text(separator="\n")
    return body.get_text(separator="\n")


def _write_format(path: Path, fmt: str, text: str, title: str = ""):
    if fmt == "txt":
        path.write_text(text, encoding="utf-8")
    elif fmt == "epub":
        _write_epub_simple(path, text, title)
    elif fmt == "fb2":
        _write_fb2(path, text, title)
    else:
        raise ValueError(f"Cannot write format: {fmt}")


def _write_epub_simple(path: Path, text: str, title: str):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("ru")

    chapter = epub.EpubHtml(title=title, file_name="content.xhtml")
    paragraphs = "\n".join(f"<p>{line}</p>" for line in text.split("\n") if line.strip())
    chapter.set_content(f"<html><body><h1>{title}</h1>{paragraphs}</body></html>")

    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)


def _write_fb2(path: Path, text: str, title: str):
    paragraphs = "\n".join(f"<p>{line}</p>" for line in text.split("\n") if line.strip())
    fb2 = f"""<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <description><title-info><book-title>{title}</book-title></title-info></description>
  <body><section><title><p>{title}</p></title>{paragraphs}</section></body>
</FictionBook>"""
    path.write_text(fb2, encoding="utf-8")
