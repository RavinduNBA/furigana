"""Build and validate the small, copyright-free Phase 0 EPUB fixture."""

import posixpath
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}

FIXTURE_FILES = {
    "mimetype": b"application/epub+zip",
    "META-INF/container.xml": """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles><rootfile full-path="EPUB/package.opf"
 media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
    "EPUB/package.opf": """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
 unique-identifier="book-id" xml:lang="ja">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:identifier id="book-id">urn:uuid:furiganalyse-phase-0</dc:identifier>
  <dc:title>Furiganalyse Phase 0 Fixture</dc:title>
  <dc:language>ja</dc:language>
  <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
 </metadata>
 <manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="ch1" href="text/chapter-01.xhtml" media-type="application/xhtml+xml"/>
  <item id="ch2" href="text/chapter-02.xhtml" media-type="application/xhtml+xml"/>
  <item id="css" href="styles/book.css" media-type="text/css"/>
  <item id="image" href="images/lantern.svg" media-type="image/svg+xml"/>
 </manifest>
 <spine><itemref idref="ch1"/><itemref idref="ch2"/></spine>
</package>""",
    "EPUB/nav.xhtml": """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"
 xmlns:epub="http://www.idpf.org/2007/ops" lang="ja">
 <head><title>\u76ee\u6b21</title></head><body>
 <nav epub:type="toc" id="toc"><h1>\u76ee\u6b21</h1><ol>
  <li><a href="text/chapter-01.xhtml">\u7b2c\u4e00\u7ae0</a></li>
  <li><a href="text/chapter-02.xhtml">\u7b2c\u4e8c\u7ae0</a></li>
 </ol></nav></body>
</html>""",
    "EPUB/text/chapter-01.xhtml": """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="ja">
 <head><title>\u7b2c\u4e00\u7ae0</title><link rel="stylesheet" href="../styles/book.css"/></head>
 <body><section id="chapter-01"><h1>\u7b2c\u4e00\u7ae0\u3000\u51fa\u4f1a\u3044</h1>
 <p>\u300c\u4eca\u65e5\u306f\u826f\u3044\u5929\u6c17\u3060\u306d\u300d\u3068\u5f7c\u5973\u306f\u8a00\u3063\u305f\u3002</p>
 <p><em>\u5f37\u8abf\u3055\u308c\u305f\u8a00\u8449</em>\u3068\u3001\u53e5\u8aad\u70b9\u2014\u2014\u305d\u3057\u3066 English text.</p>
 <p>\u821e\u53f0\u306f<ruby>\u8868\u821e\u53f0<rt>\u304a\u3082\u3066\u3076\u305f\u3044</rt></ruby>\u3060\u3063\u305f\u3002</p>
 <p><a href="chapter-02.xhtml#answer">\u6b21\u306e\u7ae0\u3078</a></p>
 <img src="../images/lantern.svg" alt="lantern"/>
 </section></body>
</html>""",
    "EPUB/text/chapter-02.xhtml": """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="ja">
 <head><title>\u7b2c\u4e8c\u7ae0</title><link rel="stylesheet" href="../styles/book.css"/></head>
 <body><section id="chapter-02"><h1>\u7b2c\u4e8c\u7ae0\u3000\u7b54\u3048</h1>
 <p id="answer">\u540d\u524d\u306f<ruby>\u96ea\u4e43<rt>\u3086\u304d\u306e</rt></ruby>\u3002\u602a\u8a1d\u306a\u9854\u3067\u632f\u308a\u8fd4\u3063\u305f\u3002</p>
 <p>Numbers 123 and Greek text remain ordinary text.</p>
 <p><a href="chapter-01.xhtml#chapter-01">\u7b2c\u4e00\u7ae0\u3078\u623b\u308b</a></p>
 </section></body>
</html>""",
    "EPUB/styles/book.css": "body { line-height: 1.8; }\nem { font-style: italic; }\nimg { width: 4em; }\n",
    "EPUB/images/lantern.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
 <rect width="64" height="64" fill="#fff4cc"/>
 <path d="M20 12h24l-3 40H23z" fill="#d65a31"/>
</svg>""",
}


def build_fixture(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", FIXTURE_FILES["mimetype"], zipfile.ZIP_STORED)
        for name, text in FIXTURE_FILES.items():
            if name != "mimetype":
                archive.writestr(name, text.encode("utf-8"), zipfile.ZIP_DEFLATED)


def _resolve(source, target):
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(source), target.split("#", 1)[0])
    )


def validate_epub(path):
    errors = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = set(archive.namelist())
        if not infos or infos[0].filename != "mimetype":
            errors.append("mimetype is not the first archive entry")
        elif infos[0].compress_type != zipfile.ZIP_STORED:
            errors.append("mimetype is compressed")
        if archive.read("mimetype") != b"application/epub+zip":
            errors.append("mimetype has invalid content")

        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//c:rootfile", CONTAINER_NS)
        if rootfile is None:
            return errors + ["container.xml has no rootfile"]
        package_name = rootfile.attrib["full-path"]
        if package_name not in names:
            return errors + [f"missing package document: {package_name}"]

        package = ET.fromstring(archive.read(package_name))
        package_dir = str(PurePosixPath(package_name).parent)
        manifest = {
            item.attrib["id"]: posixpath.normpath(
                posixpath.join(package_dir, item.attrib["href"])
            )
            for item in package.findall(".//opf:manifest/opf:item", OPF_NS)
        }
        for item_id, item_name in manifest.items():
            if item_name not in names:
                errors.append(f"manifest item {item_id} is missing: {item_name}")
        for itemref in package.findall(".//opf:spine/opf:itemref", OPF_NS):
            if itemref.attrib["idref"] not in manifest:
                errors.append(f"unknown spine idref: {itemref.attrib['idref']}")

        ids_by_doc = {}
        links = []
        for name in sorted(names):
            if not name.endswith((".html", ".xhtml")):
                continue
            root = ET.fromstring(archive.read(name))
            ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                errors.append(f"duplicate IDs in {name}: {duplicates}")
            ids_by_doc[name] = set(ids)
            for element in root.iter():
                for attribute in ("href", "src"):
                    target = element.attrib.get(attribute)
                    if target and "://" not in target and not target.startswith(("mailto:", "data:")):
                        links.append((name, target))
        for source, target in links:
            target_name = _resolve(source, target)
            if target_name not in names:
                errors.append(f"unresolved reference from {source}: {target}")
            elif "#" in target:
                fragment = target.split("#", 1)[1]
                if fragment and fragment not in ids_by_doc.get(target_name, set()):
                    errors.append(f"unresolved fragment from {source}: {target}")
    return errors
