import os
import sys
import collections

import clang.cindex
from clang.cindex import CursorKind

import vim

class Traverser(object):
    def __init__(self):
        self._output = None 
    
    def traverse(self, cursor):
        self._start_traversal(cursor)
        output = self._get_output()
        self._output = None
        return output 

    def _traversal_fn(self, cursor, parent):
        raise NotImplementedError

    def _start_traversal(self, cursor):
        iterate_cursor(cursor, self._traversal_fn)

    def _get_output(self):
        return self._output

class NamespaceTraverser(Traverser):
    def __init__(self, source_file):
        self._source_file = source_file
        self._output = []

    def _traversal_fn(self, cursor, parent):
        if cursor.location is not None and cursor.location.file is not None:
            if cursor.location.file.name == self._source_file:
                if cursor.kind == CursorKind.NAMESPACE:
                    self._output.append(cursor)
                    return True
            else:
                return False
        return True

class FollowingFunctionTraverser(Traverser):
    def __init__(self, source_file, find_fn):
        self._source_file = source_file
        self._find_fn = find_fn
        self._found_fn = False
        self._output = []

    def _traversal_fn(self, cursor, parent):
        if cursor.location.file is not None:
            if cursor.location.file.name == self._source_file:
                if is_cursor_function(cursor) and cursor.lexical_parent.canonical == \
                        self._find_fn.lexical_parent.canonical and self._found_fn:
                    self._output.append(cursor)
                if self._find_fn.canonical == cursor.canonical:
                    self._found_fn = True
            else:
                return False
        return True

class DefinitionTraverser(Traverser):
    def __init__(self, source_file, find_fn):
        self._source_file = source_file
        self._find_fn = find_fn
        self._find_fn_parent = find_fn.semantic_parent.canonical
        self._output = {}

    def _traversal_fn(self, cursor, parent):
        if cursor.location is not None and cursor.location.file is not None:
            if cursor.location.file.name == self._source_file:
                #Avoid functions that are within the lexical scope of the class
                #(so function declarations or inline definitions)
                if is_cursor_function(cursor) and \
                        cursor.lexical_parent.canonical != self._find_fn_parent:
                            name = cursor.spelling
                            if name in self._output:
                               self._output[name].append(cursor)
                            else:
                                self._output[name] = [cursor]
            else:
                return False
        return True

def create_translation_unit(index, source, unsaved_data=[]):
    return index.parse(None, [source] + ['-xc++', '-std=c++11', '-I/usr/lib/clang/3.4/include'], \
            unsaved_data, \
            clang.cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)


def get_cursor_from_location(tu, location):
    cursor = clang.cindex.Cursor.from_location(tu, location)
    return cursor

def get_corresponding_file(file_name, extensions):
    file = file_name.split('.')
    ext = file[len(file)-1]
    file = '.'.join(file[:len(file)-1])

    #If file_name already has a correct extension, just return it
    if ext in extensions:
        return file_name
    #Otherwise, look for a file or open buffer with one of
    #the given extensions
    else:
        for new_ext in extensions:
            new_file = file + new_ext
            if get_buffer_with_name(new_file) or \
                    os.path.exists(new_file):
                return new_file
        return None

def get_header_file(file_name):
    header_ext = ['.hpp', '.hxx', '.h']
    return get_corresponding_file(file_name, header_ext)
def get_source_file(file_name):
    source_ext = ['.cpp', '.cxx', '.c']
    return get_corresponding_file(file_name, source_ext)

def get_buffer_with_name(name):
    for buf in vim.buffers:
        if buf.name == name:
            return buf

def is_cursor_function(cursor):
    if cursor.kind == CursorKind.FUNCTION_DECL or \
            cursor.kind == CursorKind.FUNCTION_TEMPLATE or \
            cursor.kind == CursorKind.CXX_METHOD or \
            cursor.kind == CursorKind.DESTRUCTOR or \
            cursor.kind == CursorKind.CONSTRUCTOR:
        return True
    return False

def is_scope_block(cursor):
    return cursor.kind in [
        clang.cindex.CursorKind.NAMESPACE,
        clang.cindex.CursorKind.UNION_DECL,
        clang.cindex.CursorKind.STRUCT_DECL,
        clang.cindex.CursorKind.ENUM_DECL,
        clang.cindex.CursorKind.CLASS_DECL,
        clang.cindex.CursorKind.UNEXPOSED_DECL,
        clang.cindex.CursorKind.CLASS_TEMPLATE,
        clang.cindex.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION
    ]

def get_function_cursor_from_location(tu, location):
    cursor = get_cursor_from_location(tu, location)

    while cursor is not None:
        if is_cursor_function(cursor):
            break
        else:
            cursor = cursor.lexical_parent
    return cursor

def error(str):
    sys.stderr.write(str)

def iterate_cursor(cursor, fn, parent=None):
    ret = fn(cursor, parent)
    if ret is True:
        for child in cursor.get_children():
            iterate_cursor(child, fn, cursor)

def format_type_name(old_name):
    new_name = old_name
    for i in range(len(old_name)):
        ch = old_name[i]
        if ch == '*' or ch == '&':
            if i > 0 and old_name[i-1] == ' ':
                new_name = new_name[:i-1] + new_name[i:]
                break
    return new_name

def get_args_list(fn_cursor):
    arg_string = []

    #get_args is exposed by clang, but in some rare circumstances wasn't
    #returning arguments that existed, so we do it manually
    for child in fn_cursor.get_children():
        if child.kind == CursorKind.PARM_DECL:
            arg_fragments = []
            type_name = format_type_name(child.type.spelling)
            arg_fragments.append(type_name)
            name = child.spelling
            if name != '':
                arg_fragments.append(name)
            arg_string.append(' '.join(arg_fragments))

    return ', '.join(arg_string)

def get_template_args(cursor):
    template_args = []
    for child in cursor.get_children():
        if child.kind == CursorKind.TEMPLATE_TYPE_PARAMETER:
            template_args.append(child.spelling)

    return template_args


def get_template_declaration(cursor):
    template_string = None 
    template_args = get_template_args(cursor)
    if len(template_args) > 0:
        template_string = 'template<typename '
        template_string += ', typename'.join(template_args) + '>'

    return template_string


def get_member_class_name(cursor):
    cur = cursor.semantic_parent
    name = []
    while cur is not None:
        if cur.kind == CursorKind.CLASS_DECL or \
            cur.kind == CursorKind.CLASS_TEMPLATE:
            name.append(cur.spelling)
        cur = cur.semantic_parent

    out_string = None
    if len(name) > 0:
        out_string = '::'.join(name)
        template_args = get_template_args(cursor.semantic_parent)
        if len(template_args) > 0:
            out_string += '<{0}>'.format(', '.join(template_args))

    return out_string

def strip_template_args(fn_name):
    '''Clang adds <...> args to the spelling of template functions,
       this removes that.'''
    start = fn_name.find('<')
    if start == -1:
        return fn_name
    depth = 0
    end = -1
    for i in range(start, len(fn_name)):
        ch = fn_name[i]
        if ch == '<':
            depth += 1
        elif ch == '>':
            depth -= 1
        if depth == 0:
            end = i
            break
    if end > 0:
        return fn_name[:start] + fn_name[end+1:]
    else:
        return fn_name


def make_function_header(fn_cursor, inline=False):
    args_list = get_args_list(fn_cursor)
    name = strip_template_args(fn_cursor.spelling)

    return_type = fn_cursor.result_type.spelling
    class_template_decl = get_template_declaration(fn_cursor.semantic_parent)
    fn_template_decl = get_template_declaration(fn_cursor)

    fn_header = []
    if class_template_decl:
        fn_header.extend([class_template_decl, '\n'])
    if fn_template_decl:
        fn_header.extend([fn_template_decl, '\n'])

    if inline:
        fn_header.append('inline ')

    #Templated constructors are marked as TEMPLATE_FUNCTION not CONSTRUCTOR.
    #They are rare but we should still detect them manually.
    if fn_cursor.kind != CursorKind.CONSTRUCTOR and \
            fn_cursor.kind != CursorKind.DESTRUCTOR and \
            name != fn_cursor.semantic_parent.spelling:
        fn_header.extend([format_type_name(return_type),  ' '])

    class_name = get_member_class_name(fn_cursor)
    if class_name is not None and class_name != '':
        fn_header.extend([class_name,  "::"])

    fn_header.append('{0}({1})'.format(name, args_list))

    #clang.cindex doesn't seem to expose many specifiers for functions,
    #so try to find them in the token stream.
    depth = 0
    for t in fn_cursor.get_tokens():
        if t.spelling == '{':
            break
        elif t.spelling == '(':
            depth += 1
        elif t.spelling == ')':
            depth -= 1
        elif t.spelling == 'const' and depth == 0:
            fn_header.append(' const')
        elif t.spelling == 'noexcept' and depth == 0:
            fn_header.append(' noexcept')

    return ''.join(fn_header)

def find_closest_function_definition(tu, out_file, target_fn, fn_list):
    if len(fn_list) > 0:
        traverser = DefinitionTraverser(out_file, target_fn)
        fn_dict = traverser.traverse(tu.cursor)
        
        for fn in fn_list:
            name = fn.spelling
            if name in fn_dict:
                cur_list = fn_dict[name]
                for cur in cur_list:
                    if cur.canonical == fn.canonical:
                        return cur
    return None

def get_innermost_containing_namespace(cursor):
    cur = cursor
    while cur is not None:
        if cur.kind == CursorKind.NAMESPACE:
            return cur
        cur = cur.semantic_parent
    return None


def get_output_location(tu, fn_cursor, out_file, header_file):
    parent = fn_cursor.semantic_parent
    inner_namespace = get_innermost_containing_namespace(parent)

    traverser = FollowingFunctionTraverser(header_file, fn_cursor)
    fn_list = traverser.traverse(parent)

    line = 0

    #Try to put the new function above the function below it in the header
    fn_def = find_closest_function_definition(tu, out_file, fn_cursor, fn_list)
    if fn_def:
        line = fn_def.extent.start.line

    #Otherwise, put it at the bottom of the innermost namespace
    if line == 0:
        traverser = NamespaceTraverser(out_file)
        namespace_list = traverser.traverse(tu.cursor)
        
        inner_namespace = None
        if len(namespace_list) > 0:
            inner_namespace = namespace_list[len(namespace_list) -1]

        line = 0
        if inner_namespace:
            line = inner_namespace.extent.end.line

    #If neither works, just put it at the end, which -1 represents

    return (inner_namespace, line - 1)

def generate_method_stub(tu, cursor, out_file, header_file):
    namespace, line = get_output_location(tu, cursor, out_file, header_file)
    inline = False
    if out_file == header_file:
        inline = True
    header_string = make_function_header(cursor, inline=inline)
    
    fn_string = '\n'.join([header_string, '{', ' ', '}', ' '])

    return (fn_string, line)

def write_method(fn_string, buffer, line):
    if line < 0:
        line = len(buffer)
    buffer[line:line] = fn_string.split('\n')
    command = 'normal! {0}G'.format(line + 3)
    vim.command(command)

def source_location_from_position(tu, file_name, line, col):
    file = clang.cindex.File.from_name(tu, file_name)
    location = clang.cindex.SourceLocation.from_position(tu, file, line, col)
    return location

def get_function_cursor_on_line(tu, location, buffer):
    cursor = get_function_cursor_from_location(tu, location)
    if cursor is None:
        pos = find_fn_name_from_line(buffer[location.line-1])
        if pos:
            location = clang.cindex.SourceLocation.from_position(tu,\
                    location.file, location.line, pos)
            cursor = get_function_cursor_from_location(tu, location)

    return cursor

def build_unsaved_data(files):
    unsaved_data = []

    for file in files:
        if file:
            buf = get_buffer_with_name(file)
            if buf is not None:
                unsaved_data.append((file, '\n'.join(buf)))

    return unsaved_data

def generate_under_cursor(force_inline=False):
    file_name = vim.eval("expand('%')")
    _, line, col, _ = vim.eval("getpos('.')")
    line = int(line)
    col = int(col)

    name = os.path.abspath(file_name)

    header_file = get_header_file(name)
    source_file = get_source_file(name)

    #TODO: This should probably be made to work
    if source_file == name:
        error("Unable to implement a method in the source file.")
        return

    unsaved_data = build_unsaved_data([header_file, source_file])

    if source_file and not force_inline:
        parse_file_name = source_file
    else:
        parse_file_name = header_file

    index = clang.cindex.Index.create()
    tu = create_translation_unit(index, parse_file_name, unsaved_data)

    location = source_location_from_position(tu, name, line, col)

    cursor = get_function_cursor_on_line(tu, location, vim.current.buffer)

    if cursor is None:
        error('Unable to find a function at the location specified')
        return

    buffer = get_buffer_with_name(parse_file_name)
    if buffer is not vim.current.buffer:
        if buffer is None:
            vim.command('e {0}'.format(source_file))
            buffer = vim.current.buffer
        else:
            vim.command('b! {0}'.format(source_file))

    function_body, line = generate_method_stub(tu, cursor, \
            parse_file_name, header_file)
    write_method(function_body, buffer, line)

def find_fn_name_from_line(str):
    last_parenthesis = str.rfind(')')
    i = last_parenthesis
    depth = 0
    while i > 0:
        if str[i] == ')':
            depth += 1
        elif str[i] == '(':
            depth -= 1
        if depth == 0:
            return i - 1
        i -= 1
    return None
    
