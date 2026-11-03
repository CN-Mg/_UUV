"""Transfer the reference's editable run shadow onto the revised titles."""
from copy import deepcopy
from pathlib import Path
import re
import sys
from zipfile import ZipFile

from lxml import etree

reference, candidate, destination = map(Path, sys.argv[1:])
ns = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
with ZipFile(reference) as archive:
    slide = etree.fromstring(archive.read("ppt/slides/slide2.xml"))
    shadow = slide.xpath(
        "//a:r[a:t='4.1.2']/a:rPr/a:effectLst", namespaces=ns
    )[0]

with ZipFile(candidate) as incoming, ZipFile(destination, "x") as outgoing:
    for entry in incoming.infolist():
        data = incoming.read(entry)
        if re.fullmatch(r"ppt/slides/slide[1-4]\.xml", entry.filename):
            slide = etree.fromstring(data)
            title = slide.xpath(
                "//p:sp[p:nvSpPr/p:cNvPr/@name='页面标题']", namespaces=ns
            )[0]
            for run_properties in title.xpath(".//a:rPr", namespaces=ns):
                effect = run_properties.find("a:effectLst", namespaces=ns)
                if effect is not None:
                    run_properties.remove(effect)
                # DrawingML requires effects before the font-family elements.
                font = next(
                    (el for el in run_properties if etree.QName(el).localname in
                     {"highlight", "latin", "ea", "cs", "sym", "hlinkClick", "hlinkMouseOver"}),
                    None,
                )
                if font is None:
                    run_properties.append(deepcopy(shadow))
                else:
                    font.addprevious(deepcopy(shadow))
            data = etree.tostring(slide, encoding="UTF-8", xml_declaration=True)
        outgoing.writestr(entry, data)
