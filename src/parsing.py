"""Shared HTML and XML parsing helpers."""
from __future__ import annotations

from html.parser import HTMLParser
import re
from dataclasses import dataclass, field
from typing import Any
import xml.etree.ElementTree as ET


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Any] = field(default_factory=list)

    def all(self, tag: str | None = None, cls: str | None = None, **attrs):
        for child in self.children:
            if isinstance(child, Node):
                if ((tag is None or child.tag == tag)
                        and (cls is None or cls in child.attrs.get('class', '').split())
                        and all(child.attrs.get(k) == v for k, v in attrs.items())):
                    yield child
                yield from child.all(tag, cls, **attrs)

    def first(self, tag: str | None = None, cls: str | None = None, **attrs):
        return next(self.all(tag, cls, **attrs), None)

    def text(self) -> str:
        if self.tag in ('script', 'style', 'svg'):
            return ''
        return ' '.join(c.text() if isinstance(c, Node) else c for c in self.children)


class Document(HTMLParser):
    VOID = set('area base br col embed hr img input link meta param source track wbr'.split())

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: v or '' for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def text(node: Node | None) -> str:
    return re.sub(r'\s+', ' ', node.text()).strip() if node else ''


def plain(value: str | None) -> str:
    return text(Document(value or '').root)


def number(value: str) -> int | None:
    match = re.search(r'([\d,]+(?:\.\d+)?)\s*([kKmM]?)', value)
    if not match:
        return None
    factor = {'k': 1000, 'm': 1_000_000}.get(match[2].lower(), 1)
    return int(float(match[1].replace(',', '')) * factor)


def xml_text(node: ET.Element, name: str) -> str:
    found = node.find('{*}' + name)
    return ''.join(found.itertext()).strip() if found is not None else ''
