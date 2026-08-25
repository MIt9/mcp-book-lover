import zipfile

from mcp_book_lover.convert import _parse_docx

DOC_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="Title"/></w:pPr>
      <w:r><w:t>Назва книги</w:t></w:r>
    </w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>Глава 1</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Звичайний текст </w:t></w:r>
      <w:r><w:rPr><w:b/></w:rPr><w:t>жирний</w:t></w:r>
      <w:r><w:rPr><w:i/></w:rPr><w:t> курсив</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Другий абзац</w:t></w:r>
    </w:p>
  </w:body>
</w:document>"""

CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Метадані назва</dc:title>
  <dc:creator>Тест Автор</dc:creator>
</cp:coreProperties>"""


def _make_docx(tmp_path, include_core=True):
    p = tmp_path / "t.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("word/document.xml", DOC_XML)
        if include_core:
            zf.writestr("docProps/core.xml", CORE_XML)
    return p


def test_parse_docx_metadata(tmp_path):
    book = _parse_docx(_make_docx(tmp_path))
    assert book.title == "Метадані назва"
    assert book.author == "Тест Автор"


def test_parse_docx_blocks_and_formatting(tmp_path):
    book = _parse_docx(_make_docx(tmp_path, include_core=False))
    assert len(book.chapters) == 1
    kinds = [b.kind for b in book.chapters[0].blocks]
    assert kinds == ["subtitle", "subtitle", "para", "para"]

    body = book.chapters[0].blocks[2].spans
    texts = [s.text for s in body]
    assert "".join(texts) == "Звичайний текст жирний курсив"
    bold_flags = [s.bold for s in body]
    italic_flags = [s.italic for s in body]
    assert bold_flags == [False, True, False]
    assert italic_flags == [False, False, True]


def test_parse_docx_title_falls_back_to_first_heading(tmp_path):
    book = _parse_docx(_make_docx(tmp_path, include_core=False))
    assert book.title == "Назва книги"