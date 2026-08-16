import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from furiganalyse.parsing import (
    NAMESPACE,
    RubyAnnotation,
    extract_publisher_ruby,
    process_tree,
)


@pytest.mark.parametrize(
    ("test_case", "xml_str", "mode", "expected_xml_str"),
    [
        (
            "Remove furigana",
            '<body>はじめに、<ruby>第一<rt>ファースト</rt></ruby>歩。<ruby>終<rt>おわり</rt></ruby></body>',
            "remove",
            '<body>はじめに、第一歩。終</body>',
        ),
        (
            "Remove furigana, handling rb elements",
            "<body>黒い服を着た大人<ruby><rb>達</rb><rt>たち</rt></ruby>の間に</body>",
            "remove",
            "<body>黒い服を着た大人達の間に</body>",
        ),
        (
            "Remove furigana, handling rp elements",
            "<body><ruby>漢<rp>(</rp><rt>Kan</rt><rp>)</rp>字<rp>(</rp><rt>ji</rt><rp>)</rp></ruby></body>",
            "remove",
            "<body>漢字</body>",
        ),
        (
            "Remove furigana, parent node with text",
            '<body><ruby>第一<rt>ファースト</rt></ruby></body>',
            "remove",
            '<body>第一</body>',
        ),
        (
            "Remove furigana, no text",
            '<body><ruby><rt>ファースト</rt></ruby></body>',
            "remove",
            '<body></body>',
        ),
        (
            "Remove furigana, no text or childs",
            '<body><ruby></ruby></body>',
            "remove",
            '<body></body>',
        ),
        (
            "Override furigana",
            '<body>はじめに、<ruby>第一<rt>ファースト</rt></ruby>歩。<ruby>終<rt>おわり</rt></ruby></body>',
            "replace",
            '<body>はじめに、<ruby>第一歩<rt>だいいっぽ</rt></ruby>。<ruby>終<rt>おわり</rt></ruby></body>',
        ),
        (
            "Override furigana, handling rb elements",
            "<body>大人<ruby><rb>達</rb><rt>あああ</rt></ruby>の間に</body>",
            "replace",
            "<body><ruby>大人<rt>おとな</rt></ruby><ruby>達<rt>たち</rt></ruby>の<ruby>間<rt>ま</rt></ruby>に</body>"
        ),
        (
            "Text may be positioned before, inside or after elements",
            """
            <body class="p-text">
              <div class="main2">
                <p id="1">
                　1つの成功体験は
                  <a>ハーバード大学。</a>
                  その真ん中を
                  <span>はじめに、第一。</span>
                </p>
                その後で
              </div>
            </body>
            """,
            "add",
            """
            <body class="p-text">
              <div class="main2">
                <p id="1">1つの<ruby>成功体験<rt>せいこうたいけん</rt></ruby>は<a>ハーバード<ruby>大学<rt>だいがく</rt></ruby>。</a>その<ruby>真<rt>ま</rt></ruby>ん<ruby>中<rt>なか</rt></ruby>を<span>はじめに、<ruby>第一<rt>だいいち</rt></ruby>。</span>
                </p>その<ruby>後<rt>ご</rt></ruby>で</div>
            </body>
            """,
        ),
        (
            "Romaji is not modified",
            '<body><p id="2">No kanji around here<br class="main"/></p></body>',
            "add",
            '<body><p id="2">No kanji around here<br class="main"/></p></body>',
        ),
        (
            "Escaped characters",
            '<body>&gt;ファスト&amp;スロー&lt;：&apos;あなた&apos;の意思&quot;は&quot;</body>',
            "add",
            '<body>&gt;ファスト&amp;スロー&lt;：&apos;あなた&apos;の<ruby>意思<rt>いし</rt></ruby>&quot;は&quot;</body>',
        ),
        (
            "Applying the a title tag in the head",
            '<head><title>世界一やさしい「やりたいこと」の見つけ方　人生のモヤモヤから解放される自己理解メソッド</title></head>',
            "add",
            '<head><title><ruby>世界一<rt>せかいいち</rt></ruby>やさしい「やりたいこと」の<ruby>見<rt>み</rt></ruby>つけ<ruby>方<rt>かた</rt></ruby>　<ruby>人生<rt>じんせい</rt></ruby>のモヤモヤから<ruby>解放<rt>かいほう</rt></ruby>される<ruby>自己<rt>じこ</rt></ruby><ruby>理解<rt>りかい</rt></ruby>メソッド</title></head>',
        ),
        (
            "Don't override existing furigana",
            '<body>はじめに、<ruby>第一<rt>ファースト</rt></ruby>歩。</body>',
            "add",
            '<body>はじめに、<ruby>第一<rt>ファースト</rt></ruby><ruby>歩<rt>ふ</rt></ruby>。</body>',
        ),
        (
            "Tag inside of ruby subtags",
            '<body><ruby>一<rb><span>辿</span></rb><rt><span>たど</span></rt>二</ruby>三</body>',
            "add",
            '<body><ruby>一<rb><span>辿</span></rb><rt><span>たど</span></rt>二</ruby><ruby>三<rt>さん</rt></ruby></body>',
        ),
    ]
)
def test_process_tree(test_case, xml_str, mode, expected_xml_str):
    template = """
    <?xml version='1.0' encoding='utf-8'?>
    <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ja" class="hltr">
    {}
    </html>
    """.strip()

    tree = ET.fromstring(template.format(xml_str))

    process_tree(tree, mode)

    expected_tree = ET.fromstring(template.format(expected_xml_str))

    assert ET.tostring(tree, encoding='unicode') == ET.tostring(expected_tree, encoding='unicode')


@pytest.mark.parametrize(
    ("xml_str", "expected"),
    [
        (
            "<body><ruby>表舞台<rt>おもてぶたい</rt></ruby></body>",
            [RubyAnnotation("表舞台", "おもてぶたい")],
        ),
        (
            "<body><ruby><rb>雪乃</rb><rp>（</rp><rt>ゆきの</rt><rp>）</rp></ruby></body>",
            [RubyAnnotation("雪乃", "ゆきの")],
        ),
        (
            "<body><a><em><ruby>第一<rt>ファースト</rt></ruby></em></a></body>",
            [RubyAnnotation("第一", "ファースト")],
        ),
    ],
)
def test_extract_publisher_ruby(xml_str, expected):
    namespaced = xml_str.replace("<body>", f'<body xmlns="{NAMESPACE[1:-1]}">')
    tree = ET.ElementTree(ET.fromstring(namespaced))
    assert extract_publisher_ruby(tree) == expected


@pytest.mark.parametrize(
    "publisher_markup",
    [
        "<ruby id='publisher'>表舞台<rt>おもてぶたい</rt></ruby>",
        "<ruby id='publisher'><rb>雪乃</rb><rp>（</rp><rt>ゆきの</rt><rp>）</rp></ruby>",
        "<a><em><ruby id='publisher'>第一<rt>ファースト</rt></ruby></em></a>",
        "<ruby id='publisher'><em>表</em>舞台<rt>おもてぶたい</rt></ruby>",
        "<ruby id='publisher'><a href='#note'>表</a>舞台<rt>おもてぶたい</rt></ruby>",
    ],
)
def test_add_keeps_publisher_ruby_subtree_unchanged(publisher_markup):
    tree = ET.ElementTree(
        ET.fromstring(
            f'<body xmlns="{NAMESPACE[1:-1]}">{publisher_markup}の物語</body>'
        )
    )
    publisher = tree.find(f".//{NAMESPACE}ruby[@id='publisher']")
    expected = deepcopy(publisher)
    expected.tail = None

    process_tree(tree, "add")

    publisher = tree.find(f".//{NAMESPACE}ruby[@id='publisher']")
    actual = deepcopy(publisher)
    actual.tail = None
    assert ET.tostring(actual) == ET.tostring(expected)
    assert publisher.find(f".//{NAMESPACE}ruby") is None


def test_add_processes_text_after_protected_publisher_ruby():
    tree = ET.ElementTree(
        ET.fromstring(
            f'<body xmlns="{NAMESPACE[1:-1]}">'
            "<ruby id='publisher'>第一<rt>ファースト</rt></ruby>の漢字"
            "</body>"
        )
    )

    process_tree(tree, "add")

    generated = [
        ruby
        for ruby in tree.findall(f".//{NAMESPACE}ruby")
        if ruby.attrib.get("id") != "publisher"
    ]
    assert generated
    assert all(ruby.text != "第一" for ruby in generated)


def test_tag_suffix_is_not_mistaken_for_ruby_markup():
    tree = ET.ElementTree(
        ET.fromstring(
            f'<body xmlns="{NAMESPACE[1:-1]}"><support>漢字</support></body>'
        )
    )

    process_tree(tree, "add")

    support = tree.find(f".//{NAMESPACE}support")
    assert support.find(f"{NAMESPACE}ruby") is not None


def test_add_preserves_malformed_ruby(caplog):
    tree = ET.ElementTree(
        ET.fromstring(
            f'<body xmlns="{NAMESPACE[1:-1]}"><ruby>未知</ruby>の語</body>'
        )
    )

    with caplog.at_level("WARNING"):
        process_tree(tree, "add")

    ruby = tree.find(f".//{NAMESPACE}ruby")
    assert "Preserving unsupported publisher ruby" in caplog.text
    assert ruby is not None
    assert ruby.text == "未知"
    assert ruby.find(f"{NAMESPACE}rt") is None
