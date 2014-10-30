import os
import sys
import collections

import clang.cindex
from clang.cindex import CursorKind

import vim

import methodstub

class GenerationSettings(object):
    def __init__(self, make_getter, make_setter):
        self.make_getter = make_getter
        self.make_setter = make_setter

class AccessorKind(object):
    GETTER = 0
    SETTER = 1

def is_field_cursor(cursor):
    return cursor.kind == CursorKind.FIELD_DECL

def get_method_name_from_field(field_name):
    method_name = ''
    if field_name.find('m_') == 0:
        method_name = field_name[2:]
    elif field_name.find('_') == 0:
        method_name = field_name[1:]
    elif field_name.rfind('_') == len(field_name) - 1:
        method_name = field_name[:len(field_name)-1]
    #If underscore_delimited_words
    method_name = ''.join([word.title() for word in method_name.split('_')])
    method_name = method_name.title()
    return method_name

def make_fn_decl(tu, field_cursor, kind):
    type = field_cursor.type
    type_name = methodstub.format_type_name(type.spelling)
    method_name = collections.deque()
    method_name.append(get_method_name_from_field(field_cursor.spelling))
    if kind == AccessorKind.GETTER:
        method_name.appendleft('get')
        method_name.append('() const')
    else:
        method_name.appendleft('set')
        method_name.append('({0} value)'.format(type_name))
    method_name.appendleft(type_name + ' ')
    return ''.join(method_name)



def get_field_cursor_from_location(tu, location):
    cursor = methodstub.get_cursor_from_location(tu, location)
    while cursor is not None:
        if is_field_cursor(cursor):
            return cursor
        cursor = cursor.semantic_parent
    return None

def find_field_name_from_line(str):
    for i, ch in enumerate(str):
        if (ch >= 'a' and ch <= 'z') or (ch >= 'A' and ch <= 'Z') \
                or ch == '_':
            return i + 1
    return None

def get_field_cursor_on_line(tu, location, buffer):
    cursor = get_field_cursor_from_location(tu, location)
    if cursor is None:
        pos = find_field_name_from_line(buffer[location.line-1])
        if pos is not None:
            location = clang.cindex.SourceLocation.from_position(tu, \
                    location.file, location.line, pos)
            cursor = get_field_cursor_from_location(tu, location)
    return cursor

def generate_at_location(tu, files, settings, line, col, buffer):
    location = methodstub.source_location_from_position(tu, files.input, \
            line, col)
    cursor = get_field_cursor_on_line(tu, location, buffer)
    print(cursor.kind, cursor.spelling)
    print(dir(cursor))
    print(make_fn_decl(tu, cursor, AccessorKind.GETTER))
    print(make_fn_decl(tu, cursor, AccessorKind.SETTER))

def generate_under_cursor(inline=True, getter=True, setter=False):
    file_name = vim.eval("expand('%')")

    files = methodstub.make_fileset_for_source(file_name, inline)

    unsaved_data = methodstub.build_unsaved_data([files.header, files.source])

    index = clang.cindex.Index.create()
    tu = methodstub.create_translation_unit(index, files.output, unsaved_data)

    _, line, col, _ = vim.eval("getpos('.')")
    line = int(line)
    col = int(col)
    generate_at_location(tu, files, None, line, col, vim.current.buffer)
