"""Book format conversion: epub, fb2, txt, pdf."""

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

    # Read content from source
    text = _extract_text(src, src_format)

    # Write to target format
    _write_format(dest, output_format, text, title=src.stem)

    return str(dest)


def _extract_text(path: Path, fmt: str) -> str:
    """Extract plain text from a book file."""
    if fmt == "txt":
        return path.read_text(encoding="utf-8")

    if fmt == "epub":
        return _extract_epub(path)

    if fmt == "pdf":
        return _extract_pdf(path)

    if fmt == "fb2":
        return _extract_fb2(path)

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


def _extract_fb2(path: Path) -> str:
    from bs4 import BeautifulSoup

    content = path.read_bytes()
    soup = BeautifulSoup(content, "xml")
    body = soup.find("body")
    if not body:
        return soup.get_text(separator="\n")
    return body.get_text(separator="\n")


def _write_format(path: Path, fmt: str, text: str, title: str = ""):
    """Write text content to target format."""
    if fmt == "txt":
        path.write_text(text, encoding="utf-8")
        return

    if fmt == "epub":
        _write_epub(path, text, title)
        return

    if fmt == "pdf":
        _write_pdf(path, text, title)
        return

    if fmt == "fb2":
        _write_fb2(path, text, title)
        return

    raise ValueError(f"Cannot write format: {fmt}")


def _write_epub(path: Path, text: str, title: str):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("uk")

    chapter = epub.EpubHtml(title=title, file_name="content.xhtml")
    paragraphs = "\n".join(f"<p>{line}</p>" for line in text.split("\n") if line.strip())
    chapter.set_content(f"<html><body><h1>{title}</h1>{paragraphs}</body></html>")

    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    epub.write_epub(str(path), book)


def _write_pdf(path: Path, text: str, title: str):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, ArrayObject, DictionaryObject

    # Simple text-to-PDF using reportlab-free approach
    # For proper PDF creation we'll use a minimal approach
    writer = PdfWriter()
    # pypdf can't create PDFs from scratch easily, use a text file fallback
    # Instead, create a simple PDF with basic content stream
    txt_path = path.with_suffix(".txt")
    txt_path.write_text(f"{title}\n\n{text}", encoding="utf-8")
    # Notify user about limitation
    path_txt = str(txt_path)
    raise ValueError(
        f"PDF writing requires reportlab. Text saved to {path_txt}. "
        f"Install reportlab (`pip install reportlab`) for PDF output."
    )


def _write_fb2(path: Path, text: str, title: str):
    paragraphs = "\n".join(f"<p>{line}</p>" for line in text.split("\n") if line.strip())
    fb2 = f"""<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <description>
    <title-info>
      <book-title>{title}</book-title>
    </title-info>
  </description>
  <body>
    <section>
      <title><p>{title}</p></title>
      {paragraphs}
    </section>
  </body>
</FictionBook>"""
    path.write_text(fb2, encoding="utf-8")
