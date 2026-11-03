"""Replace the first slide's layout while keeping every other package part."""
from copy import deepcopy
from pathlib import Path
import sys
from zipfile import ZipFile

from lxml import etree

source, donor, output = map(Path, sys.argv[1:])
first_slide = "ppt/slides/slide1.xml"
ns = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
with ZipFile(source) as original, ZipFile(donor) as revised:
    original_xml = etree.fromstring(original.read(first_slide))
    revised_xml = etree.fromstring(revised.read(first_slide))
    original_tree = original_xml.find(".//p:spTree", ns)
    revised_tree = revised_xml.find(".//p:spTree", ns)
    title = original_tree.xpath("./p:sp[p:nvSpPr/p:cNvPr/@name='页面标题']", namespaces=ns)[0]
    picture = original_tree.find("p:pic", ns)
    for element in list(original_tree)[2:]:
        if element not in (title, picture):
            original_tree.remove(element)

    # Reuse the original title and embedded image. Moving the existing image
    # keeps its relationship, aspect ratio, crop, and source data.
    transform = picture.find("p:spPr/a:xfrm", ns)
    transform.find("a:off", ns).attrib.update({"x": str(64*9525), "y": str(301*9525)})
    size = transform.find("a:ext", ns)
    height = round(int(size.get("cy")) * 179*9525 / int(size.get("cx")))
    size.attrib.update({"cx": str(179*9525), "cy": str(height)})
    generated = [deepcopy(shape) for shape in list(revised_tree)[2:]]
    used_ids = [int(node.get("id")) for node in original_tree.xpath(".//p:cNvPr", namespaces=ns)]
    for offset, shape in enumerate(generated, start=max(used_ids)+1):
        for properties in shape.xpath(".//p:cNvPr", namespaces=ns):
            properties.set("id", str(offset))
        original_tree.append(shape)
    original_tree.remove(picture)
    original_tree.append(picture)
    first_slide_xml = etree.tostring(original_xml, encoding="UTF-8", xml_declaration=True)
    with ZipFile(output, "x") as archive:
        for entry in original.infolist():
            archive.writestr(entry, first_slide_xml if entry.filename == first_slide else original.read(entry))
