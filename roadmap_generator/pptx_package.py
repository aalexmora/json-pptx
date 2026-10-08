"""Безопасная сборка PPTX-пакетов из roadmap- и static-шаблонов.

`python-pptx` умеет добавить слайд только с layout из той же презентации. Если
передать layout из другого файла, зависимые master/theme попадут в ZIP, но сам
master не будет зарегистрирован в `presentation.xml`. PowerPoint считает такой
пакет повреждённым и предлагает Repair.

Этот модуль работает на уровне открытого формата OOXML: создаёт пустую оболочку
из roadmap-шаблона и импортирует static-слайды вместе с их деревом зависимостей,
явно регистрируя slide master. Приватный API `python-pptx` здесь не используется.
"""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Iterable, Sequence
from xml.etree import ElementTree as ET

from pptx import Presentation


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

PRESENTATION_XML = "ppt/presentation.xml"
PRESENTATION_RELS = "ppt/_rels/presentation.xml.rels"
CONTENT_TYPES_XML = "[Content_Types].xml"

SLIDE_RELATIONSHIP = f"{R_NS}/slide"
SLIDE_MASTER_RELATIONSHIP = f"{R_NS}/slideMaster"

# Notes и comments не влияют на вид слайда, но требуют отдельных объектов уровня
# презентации (notesMaster/commentAuthors). Не переносим их, чтобы static-слайд
# не создавал незарегистрированные document-level зависимости.
IGNORED_RELATIONSHIP_SUFFIXES = ("/notesSlide", "/comments", "/commentAuthors")


def open_template_shell(template_path: str | Path) -> Presentation:
    """Открывает шаблон без исходных слайдов, сохраняя masters/layouts/themes."""
    entries = _read_archive(Path(template_path).read_bytes())

    presentation = ET.fromstring(entries[PRESENTATION_XML])
    slide_id_list = presentation.find(f"{{{P_NS}}}sldIdLst")
    if slide_id_list is not None:
        slide_id_list.clear()
    entries[PRESENTATION_XML] = _serialize_xml(presentation)

    relationships = ET.fromstring(entries[PRESENTATION_RELS])
    for relationship in list(relationships):
        if relationship.get("Type") == SLIDE_RELATIONSHIP:
            relationships.remove(relationship)
    entries[PRESENTATION_RELS] = _serialize_xml(relationships)

    return Presentation(_write_archive(entries))


def source_slide_count(source_path: str | Path) -> int:
    """Возвращает число слайдов PPTX без загрузки его объектов в целевой пакет."""
    entries = _read_archive(Path(source_path).read_bytes())
    presentation = ET.fromstring(entries[PRESENTATION_XML])
    slide_id_list = presentation.find(f"{{{P_NS}}}sldIdLst")
    return len(slide_id_list) if slide_id_list is not None else 0


def import_static_slides(
    presentation: Presentation,
    imports: Sequence[tuple[int, str | Path]],
) -> Presentation:
    """Вставляет static PPTX в указанные позиции и возвращает валидный пакет.

    Позиция — абсолютный индекс в итоговой последовательности слайдов. Один
    static PPTX может содержать несколько слайдов; они вставляются подряд.
    """
    if not imports:
        return presentation

    target_buffer = io.BytesIO()
    presentation.save(target_buffer)
    target_entries = _read_archive(target_buffer.getvalue())

    for sequence, (position, source_path) in enumerate(imports, start=1):
        source_entries = _read_archive(Path(source_path).read_bytes())
        _import_source_package(
            target_entries,
            source_entries,
            position=position,
            token=f"static{sequence}",
        )

    return Presentation(_write_archive(target_entries))


def _import_source_package(
    target_entries: dict[str, bytes],
    source_entries: dict[str, bytes],
    *,
    position: int,
    token: str,
) -> None:
    source_slides = _presentation_parts(
        source_entries,
        list_tag="sldIdLst",
        item_tag="sldId",
        relationship_type=SLIDE_RELATIONSHIP,
    )
    if not source_slides:
        return

    graph = _dependency_graph(source_entries, source_slides)
    occupied = set(target_entries)
    part_mapping: dict[str, str] = {}
    for source_part in sorted(graph):
        target_part = _allocate_part_name(source_part, occupied, token)
        part_mapping[source_part] = target_part
        occupied.add(target_part)

    for source_part, target_part in part_mapping.items():
        target_entries[target_part] = source_entries[source_part]
        source_rels_name = _relationships_name(source_part)
        if source_rels_name not in source_entries:
            continue
        rewritten = _rewrite_relationships(
            source_entries[source_rels_name],
            source_part=source_part,
            target_part=target_part,
            part_mapping=part_mapping,
        )
        if rewritten is not None:
            target_entries[_relationships_name(target_part)] = rewritten

    _copy_content_types(target_entries, source_entries, part_mapping)

    source_masters = _presentation_parts(
        source_entries,
        list_tag="sldMasterIdLst",
        item_tag="sldMasterId",
        relationship_type=SLIDE_MASTER_RELATIONSHIP,
    )
    mapped_masters = [part_mapping[part] for part in source_masters if part in part_mapping]
    mapped_slides = [part_mapping[part] for part in source_slides]
    _register_imported_parts(
        target_entries,
        masters=mapped_masters,
        slides=mapped_slides,
        position=position,
    )


def _dependency_graph(entries: dict[str, bytes], roots: Iterable[str]) -> set[str]:
    """Все внутренние parts, достижимые от слайдов (layout/master/theme/media)."""
    visited: set[str] = set()
    pending = list(roots)
    while pending:
        part = pending.pop()
        if part in visited or part not in entries:
            continue
        visited.add(part)
        rels_name = _relationships_name(part)
        if rels_name not in entries:
            continue
        relationships = ET.fromstring(entries[rels_name])
        for relationship in relationships:
            if relationship.get("TargetMode") == "External":
                continue
            relationship_type = relationship.get("Type", "")
            if relationship_type.endswith(IGNORED_RELATIONSHIP_SUFFIXES):
                continue
            target = relationship.get("Target")
            if not target:
                continue
            target_part = _resolve_target(part, target)
            if target_part in entries and target_part not in visited:
                pending.append(target_part)
    return visited


def _rewrite_relationships(
    data: bytes,
    *,
    source_part: str,
    target_part: str,
    part_mapping: dict[str, str],
) -> bytes | None:
    relationships = ET.fromstring(data)
    for relationship in list(relationships):
        if relationship.get("TargetMode") == "External":
            continue
        target = relationship.get("Target")
        if not target:
            relationships.remove(relationship)
            continue
        source_target = _resolve_target(source_part, target)
        mapped_target = part_mapping.get(source_target)
        if mapped_target is None:
            relationships.remove(relationship)
            continue
        relationship.set("Target", _relative_target(target_part, mapped_target))
    if not list(relationships):
        return None
    return _serialize_xml(relationships)


def _copy_content_types(
    target_entries: dict[str, bytes],
    source_entries: dict[str, bytes],
    part_mapping: dict[str, str],
) -> None:
    target_root = ET.fromstring(target_entries[CONTENT_TYPES_XML])
    source_root = ET.fromstring(source_entries[CONTENT_TYPES_XML])

    target_defaults = {
        item.get("Extension"): item
        for item in target_root.findall(f"{{{CT_NS}}}Default")
    }
    source_defaults = {
        item.get("Extension"): item
        for item in source_root.findall(f"{{{CT_NS}}}Default")
    }
    source_overrides = {
        item.get("PartName", "").lstrip("/"): item.get("ContentType", "")
        for item in source_root.findall(f"{{{CT_NS}}}Override")
    }

    for source_part, target_part in part_mapping.items():
        content_type = source_overrides.get(source_part)
        if content_type:
            ET.SubElement(
                target_root,
                f"{{{CT_NS}}}Override",
                PartName=f"/{target_part}",
                ContentType=content_type,
            )
            continue
        extension = Path(source_part).suffix.lstrip(".")
        if extension in target_defaults:
            continue
        default = source_defaults.get(extension)
        if default is not None:
            ET.SubElement(
                target_root,
                f"{{{CT_NS}}}Default",
                Extension=extension,
                ContentType=default.get("ContentType", ""),
            )
            target_defaults[extension] = default

    target_entries[CONTENT_TYPES_XML] = _serialize_xml(target_root)


def _register_imported_parts(
    entries: dict[str, bytes],
    *,
    masters: Sequence[str],
    slides: Sequence[str],
    position: int,
) -> None:
    presentation = ET.fromstring(entries[PRESENTATION_XML])
    relationships = ET.fromstring(entries[PRESENTATION_RELS])

    used_relationship_ids = {item.get("Id", "") for item in relationships}
    next_relationship_number = _next_relationship_number(used_relationship_ids)

    def add_relationship(relationship_type: str, part: str) -> str:
        nonlocal next_relationship_number
        while f"rId{next_relationship_number}" in used_relationship_ids:
            next_relationship_number += 1
        relationship_id = f"rId{next_relationship_number}"
        next_relationship_number += 1
        used_relationship_ids.add(relationship_id)
        ET.SubElement(
            relationships,
            f"{{{REL_NS}}}Relationship",
            Id=relationship_id,
            Type=relationship_type,
            Target=posixpath.relpath(part, "ppt"),
        )
        return relationship_id

    master_list = presentation.find(f"{{{P_NS}}}sldMasterIdLst")
    if master_list is None:
        master_list = ET.Element(f"{{{P_NS}}}sldMasterIdLst")
        presentation.insert(0, master_list)
    used_master_ids = {
        int(item.get("id", "2147483647"))
        for item in master_list
        if item.get("id", "").isdigit()
    }
    next_master_id = max(used_master_ids, default=2147483647) + 1
    for master in masters:
        relationship_id = add_relationship(SLIDE_MASTER_RELATIONSHIP, master)
        while next_master_id in used_master_ids:
            next_master_id += 1
        ET.SubElement(
            master_list,
            f"{{{P_NS}}}sldMasterId",
            {"id": str(next_master_id), f"{{{R_NS}}}id": relationship_id},
        )
        used_master_ids.add(next_master_id)
        next_master_id += 1

    slide_list = presentation.find(f"{{{P_NS}}}sldIdLst")
    if slide_list is None:
        slide_list = ET.Element(f"{{{P_NS}}}sldIdLst")
        children = list(presentation)
        master_index = children.index(master_list)
        presentation.insert(master_index + 1, slide_list)
    used_slide_ids = {
        int(item.get("id", "255"))
        for item in slide_list
        if item.get("id", "").isdigit()
    }
    next_slide_id = max(used_slide_ids, default=255) + 1
    insert_at = min(max(position, 0), len(slide_list))
    for offset, slide in enumerate(slides):
        relationship_id = add_relationship(SLIDE_RELATIONSHIP, slide)
        while next_slide_id in used_slide_ids:
            next_slide_id += 1
        slide_id = ET.Element(
            f"{{{P_NS}}}sldId",
            {"id": str(next_slide_id), f"{{{R_NS}}}id": relationship_id},
        )
        slide_list.insert(insert_at + offset, slide_id)
        used_slide_ids.add(next_slide_id)
        next_slide_id += 1

    entries[PRESENTATION_XML] = _serialize_xml(presentation)
    entries[PRESENTATION_RELS] = _serialize_xml(relationships)


def _presentation_parts(
    entries: dict[str, bytes],
    *,
    list_tag: str,
    item_tag: str,
    relationship_type: str,
) -> list[str]:
    presentation = ET.fromstring(entries[PRESENTATION_XML])
    relationships = ET.fromstring(entries[PRESENTATION_RELS])
    targets = {
        item.get("Id", ""): _resolve_target(PRESENTATION_XML, item.get("Target", ""))
        for item in relationships
        if item.get("Type") == relationship_type
    }
    result: list[str] = []
    container = presentation.find(f"{{{P_NS}}}{list_tag}")
    if container is None:
        return result
    for item in container.findall(f"{{{P_NS}}}{item_tag}"):
        relationship_id = item.get(f"{{{R_NS}}}id", "")
        target = targets.get(relationship_id)
        if target:
            result.append(target)
    return result


def _allocate_part_name(source: str, occupied: set[str], token: str) -> str:
    if source not in occupied and _relationships_name(source) not in occupied:
        return source
    directory, filename = posixpath.split(source)
    match = re.match(r"^(.*?)(\d+)?(\.[^.]+)$", filename)
    if match is None:
        stem, extension = filename, ""
    else:
        stem, extension = match.group(1), match.group(3)
    number = 1
    while True:
        candidate = posixpath.join(directory, f"{stem}_{token}_{number}{extension}")
        if candidate not in occupied and _relationships_name(candidate) not in occupied:
            return candidate
        number += 1


def _relationships_name(part: str) -> str:
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _resolve_target(source_part: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _relative_target(source_part: str, target_part: str) -> str:
    return posixpath.relpath(target_part, posixpath.dirname(source_part))


def _next_relationship_number(ids: set[str]) -> int:
    numbers = [
        int(match.group(1))
        for relationship_id in ids
        if (match := re.fullmatch(r"rId(\d+)", relationship_id)) is not None
    ]
    return max(numbers, default=0) + 1


def _read_archive(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        return {
            item.filename: archive.read(item.filename)
            for item in archive.infolist()
            if not item.is_dir()
        }


def _write_archive(entries: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    buffer.seek(0)
    return buffer


def _serialize_xml(element: ET.Element) -> bytes:
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)
