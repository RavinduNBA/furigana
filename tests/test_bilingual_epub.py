import zipfile
from xml.etree import ElementTree as ET

from furiganalyse.bilingual_epub import package_bilingual_epub, render_translation_xhtml
from furiganalyse.bilingual_translation import TranslationChapter, TranslationParagraph
from tests.phase0_epub import build_fixture


def test_render_translation_xhtml():
    ch = TranslationChapter(
        chapter_id="ch-0001",
        title="Prologue",
        paragraphs=[
            TranslationParagraph(
                block_id="ch-0001-b-0001",
                japanese_sentences=["魔法。"],
                english_translation="Magic.",
            ),
            TranslationParagraph(
                block_id="ch-0001-b-0002",
                japanese_sentences=["「それは技術だ」"],
                english_translation="“It is a technology.”",
                footnotes=["Modern scientific magic."],
            ),
        ],
    )

    xhtml = render_translation_xhtml(ch, orig_xhtml_name="chapter-01.xhtml")

    assert "<?xml version=" in xhtml
    assert "<title>Prologue (English Translation)</title>" in xhtml
    assert '<p class="bilingual-paragraph" id="trans-ch-0001-b-0001">Magic.' in xhtml
    assert '<p class="bilingual-dialogue" id="trans-ch-0001-b-0002">“It is a technology.”' in xhtml
    assert '<div class="bilingual-footnote"><em>Note:</em> Modern scientific magic.</div>' in xhtml
    assert 'href="chapter-01.xhtml#ch-0001-b-0001"' in xhtml

    # Ensure valid XML
    root = ET.fromstring(xhtml)
    assert root.tag == "{http://www.w3.org/1999/xhtml}html"


def test_package_bilingual_epub(tmp_path):
    src_epub = tmp_path / "src.epub"
    dst_epub = tmp_path / "bilingual.epub"

    build_fixture(src_epub)

    trans_chapters = [
        TranslationChapter(
            chapter_id="ch-0001",
            title="First Chapter",
            paragraphs=[
                TranslationParagraph(
                    block_id="b-0001",
                    japanese_sentences=["テスト"],
                    english_translation="Test sentence in English.",
                )
            ],
        )
    ]

    package_bilingual_epub(src_epub, dst_epub, trans_chapters)

    assert dst_epub.exists()

    with zipfile.ZipFile(dst_epub, "r") as z:
        names = z.namelist()
        # Verify mimetype is first and uncompressed
        assert names[0] == "mimetype"
        assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED

        # Verify companion chapter exists
        trans_files = [n for n in names if "translation.xhtml" in n]
        assert len(trans_files) == 1

        content = z.read(trans_files[0]).decode("utf-8")
        assert "Test sentence in English." in content

        # Verify OPF manifest & spine were updated
        opf_file = next(n for n in names if n.endswith(".opf"))
        opf_root = ET.fromstring(z.read(opf_file))
        manifest = opf_root.find("{http://www.idpf.org/2007/opf}manifest")
        assert any("translation.xhtml" in (item.get("href") or "") for item in manifest)
