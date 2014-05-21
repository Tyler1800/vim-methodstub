import os
import sys
import collections

import clang.cindex
from clang.cindex import CursorKind

import vim

class FileSet(object):
    '''Provides a single object to store all file information.'''
    def __init__(self, source, header, input, output):
        self.source = source
        self.header = header
        self.input = input
        self.output = output

    def is_input_header(self):
        return self.header == self.input

    def is_output_header(self):
        return self.header == self.output

class Traverser(object):
    '''Defined an interface for classes that need to traverse the AST.'''
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
    '''Traverser that generates a list of namespace
       cursors containing the given function.'''
    def __init__(self, source_file, target_fn):
        self._source_file = source_file
        self._target_fn = target_fn
        self._output = []

    def _traversal_fn(self, cursor, parent):
        if cursor.location is not None and cursor.location.file is not None:
            if cursor.location.file.name == self._source_file:
                if cursor.kind == CursorKind.NAMESPACE:
                    parent = self._target_fn.semantic_parent
                    while parent is not None:
                        if parent.canonical == cursor.canonical:
                            self._output.append(cursor)
                            break
                        parent = parent.semantic_parent
                    return True
            else:
                return False
        return True

class FollowingFunctionTraverser(Traverser):
    '''Traverser that generates a list of all function declarations
       occuring after the given declaration in the same scope.'''
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
    '''Traverser that finds all function definitions in a file.'''
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
    '''Build a translation unit by parsing the file source using
       index index with unsaved_data containing a list of(name, data) tuples
       with the full content of any unsaved buffers.'''
    return index.parse(None, [source] + ['-xc++', '-std=c++11'], \
            unsaved_data, \
            clang.cindex.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)


def get_cursor_from_location(tu, location):
    '''Return a cursor at the given location in the given translation unit.'''
    cursor = clang.cindex.Cursor.from_location(tu, location)
    return cursor

def get_corresponding_file(file_name, extensions):
    '''Find a file with the same name and path but having an extension
       in the list of extensions provided. A name will be returned
       if there is a file on the disk or an open buffer with an appropriate
       name, otherwise None will be returned.'''
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
    '''Return a corresponding file with an extension of
       .hpp, .hxx or .h'''
    header_ext = ['.hpp', '.hxx', '.h']
    return get_corresponding_file(file_name, header_ext)
def get_source_file(file_name):
    '''Return a corresponding file with an extension of
       .cpp, .cxx or .c'''
    source_ext = ['.cpp', '.cxx', '.c']
    return get_corresponding_file(file_name, source_ext)

def get_buffer_with_name(name):
    '''Return an open buffer with the name name, or none
       if no such buffer exists.'''
    for buf in vim.buffers:
        if buf.name == name:
            return buf

def is_cursor_function(cursor):
    '''Return whether the provided cursor is some sort of function.'''
    if cursor.kind == CursorKind.FUNCTION_DECL or \
            cursor.kind == CursorKind.FUNCTION_TEMPLATE or \
            cursor.kind == CursorKind.CXX_METHOD or \
            cursor.kind == CursorKind.DESTRUCTOR or \
            cursor.kind == CursorKind.CONSTRUCTOR:
        return True
    return False

def get_function_cursor_from_location(tu, location):
    '''Return a cursor at the current location that is a function,
       if one exists.'''
    cursor = get_cursor_from_location(tu, location)

    while cursor is not None:
        if is_cursor_function(cursor):
            break
        else:
            cursor = cursor.lexical_parent
    return cursor

def error(str):
    '''Output an error message.'''
    sys.stderr.write(str)

def iterate_cursor(cursor, fn, parent=None):
    '''Iterate all children of cursor, calling fn for each.
       fn may return False to stop recursion into that node's children.'''
    ret = fn(cursor, parent)
    if ret is True:
        for child in cursor.get_children():
            iterate_cursor(child, fn, cursor)

def format_type_name(old_name):
    '''Reformat a type name to remove the space
       between the type and * or &.'''
    new_name = old_name
    for i in range(len(old_name)):
        ch = old_name[i]
        if ch == '*' or ch == '&':
            if i > 0 and old_name[i-1] == ' ':
                new_name = new_name[:i-1] + new_name[i:]
                break
    return new_name

def get_args_list(fn_cursor):
    '''Return a string of arguments to the function fn_cursor'''
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
    '''Return a list of the names of each template argument
       to cursor. Cursor can be a function or class.'''
    template_args = []
    for child in cursor.get_children():
        if child.kind == CursorKind.TEMPLATE_TYPE_PARAMETER:
            template_args.append(child.spelling)

    return template_args


def get_template_declaration(cursor):
    '''Return a template declaration string for cursor'''
    template_string = None
    template_args = get_template_args(cursor)
    if len(template_args) > 0:
        template_string = 'template<typename '
        template_string += ', typename'.join(template_args) + '>'

    return template_string


def get_member_class_name(cursor):
    '''Return the full scope string for the parent class or
        classes of cursor.'''
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

def add_function_specifiers(fn_cursor, header):
    '''Find specifier keywords in the token stream and add them
       to the deque header'''
    depth = 0
    for t in fn_cursor.get_tokens():
        if t.spelling == '{':
            break
        elif t.spelling == '(':
            depth += 1
        elif t.spelling == ')':
            depth -= 1
        elif t.spelling == 'const' and depth == 0:
            header.append(' const')
        elif t.spelling == 'noexcept' and depth == 0:
            header.append(' noexcept')
        elif t.spelling == 'constexpr' and depth == 0:
            header.appendleft('constexpr ')

def make_function_header(fn_cursor, inline=False, namespace=''):
    '''Return a header string for the function fn_cursor.
       If inline is True, the function is marked inline in the header.'''
    args_list = get_args_list(fn_cursor)
    name = strip_template_args(fn_cursor.spelling)

    return_type = fn_cursor.result_type.spelling
    class_template_decl = get_template_declaration(fn_cursor.semantic_parent)
    fn_template_decl = get_template_declaration(fn_cursor)

    fn_header = collections.deque()

    if namespace != '':
        fn_header.append(namespace)
        fn_header.append('::')

    class_name = get_member_class_name(fn_cursor)
    if class_name is not None and class_name != '':
        fn_header.extend([class_name, "::"])

    fn_header.append('{0}({1})'.format(name, args_list))

    #Templated constructors are marked as TEMPLATE_FUNCTION not CONSTRUCTOR.
    #They are rare but we should still detect them manually.
    if fn_cursor.kind != CursorKind.CONSTRUCTOR and \
            fn_cursor.kind != CursorKind.DESTRUCTOR and \
            name != fn_cursor.semantic_parent.spelling:
        fn_header.appendleft(format_type_name(return_type)  + ' ')

    #clang.cindex doesn't seem to expose many specifiers for functions,
    #so try to find them in the token stream.
    add_function_specifiers(fn_cursor, fn_header)

    if inline:
        fn_header.appendleft('inline ')

    if fn_template_decl:
        fn_header.appendleft(fn_template_decl + '\n')
    if class_template_decl:
        fn_header.appendleft(class_template_decl + '\n')


    return ''.join(fn_header)

def find_defined_functions(tu, file, target_fn):
    '''Return a dictionary of functions defined in the same scope
       as target_fn. The dictionary has keys containing the names
       of each functions and values that are lists of all overloads
       of the function with that name.'''
    traverser = DefinitionTraverser(file, target_fn)
    fn_dict = traverser.traverse(tu.cursor)
    return fn_dict

def get_definition_for_function(definitions, cursor):
    '''Find the definition for function cursor in definitions if
       it exists.'''
    name = cursor.spelling
    if name in definitions:
        cur_list = definitions[name]
        for cur in cur_list:
            if cur.canonical == cursor.canonical:
                return cur
    return None


def find_closest_function_definition(tu, target_fn, fn_list, definitions):
    '''Find the first function in fn_list that has a definition in
       definitions'''
    if len(fn_list) > 0:
        for fn in fn_list:
            out = get_definition_for_function(definitions, fn)
            if out:
                return out
    return None

def get_namespaces(cursor):
    '''Return a list of all namespaces cursor belongs to'''
    namespaces = []
    cur = cursor
    while cur is not None:
        if cur.kind == CursorKind.NAMESPACE:
            namespaces.append(cur)
        cur = cur.semantic_parent
    return namespaces[::-1]

def get_lexical_namespaces(tu, cursor, source_file):
    '''Return a list of all namespaces cursor is enclosed by
       within the file source_file'''
    traverser = NamespaceTraverser(source_file, cursor)
    namespace_list = traverser.traverse(tu.cursor)
    return namespace_list


def get_following_declarations(header_file, fn_cursor):
    '''Get all function declarations in the same scope but below
       fn_cursor.'''
    traverser = FollowingFunctionTraverser(header_file, fn_cursor)
    return traverser.traverse(fn_cursor.semantic_parent)


def get_output_location(tu, fn_cursor, files, above_def, namespaces):
    '''Return the line at which to insert the function definition'''
    parent = fn_cursor.semantic_parent

    line = 0

    #Try to put the new function above the function below it in the header
    if above_def is not None:
        line = above_def.extent.start.line - 1

    #Otherwise, put it at the bottom of the innermost namespace
    if line == 0:
        inner_namespace = None
        if len(namespaces) > 0:
            inner_namespace = namespaces[len(namespaces)-1]

        if inner_namespace:
            line = inner_namespace.extent.end.line - 1

    #If neither works, just put it at the end, is represented by -1
    if line == 0:
        line = -1

    return line

def build_namespace_scope_resolution(namespaces, lexical_namespaces):
    '''Return a string needed to resolve a symbol belonging to namespaces
       that is located within lexical_namespaces inside the source'''
    #lexical_depth is how many lexical_namespaces match namespaces
    lexical_depth = 0
    for i in range(0, len(lexical_namespaces)):
        if i >= len(namespaces):
            break
        if namespaces[i].canonical == lexical_namespaces[i].canonical:
            lexical_depth += 1
        else:
            break

    namespace_parts = []
    for i in range(lexical_depth, len(namespaces)):
        namespace_parts.append(namespaces[i].spelling)
    return '::'.join(namespace_parts)


def generate_method_stub(tu, cursor, files, force=False):
    '''Return a tuple of a string containing the function definition
       and a line number to insert it for the function cursor.'''

    definitions = find_defined_functions(tu, files.output, cursor)
    definition = get_definition_for_function(definitions, cursor)

    if definition and not force:
        error("'{0}' is already defined at {1}:{2}".format(
            cursor.displayname, definition.location.file, \
            definition.location.line))
        return None

    decl_list = get_following_declarations(files.header, cursor)
    next_def = find_closest_function_definition(tu, cursor, \
            decl_list, definitions)

    namespaces = get_namespaces(cursor)
    lexical_namespaces = get_lexical_namespaces(tu, cursor, files.output)

    namespace_str = build_namespace_scope_resolution(namespaces, lexical_namespaces)

    inline = False
    if files.is_output_header():
        inline = True
    header_string = make_function_header(cursor, inline=inline, \
            namespace=namespace_str)


    line = get_output_location(tu, cursor, files, next_def, lexical_namespaces)

    fn_string = '\n'.join([header_string, '{', ' ', '}', ' '])

    return (fn_string, line)

def write_method(fn_string, buffer, line, above_endif=False):
    '''Write the function definition in fn_string to buffer
       at the line line and jump to the middle of the definition'''
    if line <= 0:
        #For headers, we need to manually search for #endif at the bottom
        line = len(buffer)
        if above_endif:
            for i in range(len(buffer) - 1, 1, -1):
                if buffer[i].find('#endif') >= 0:
                    line = i
                    break

    lines = fn_string.split('\n')
    buffer[line:line] = lines
    command = 'normal! {0}G'.format(line + len(lines) - 2)
    vim.command(command)

def source_location_from_position(tu, file_name, line, col):
    '''Return a clang SourceLocation object for the given location'''
    file = clang.cindex.File.from_name(tu, file_name)
    location = clang.cindex.SourceLocation.from_position(tu, file, line, col)
    return location

def find_fn_name_from_line(str):
    '''Try to find the last character of the function name
       on the line provided. This position can be used to get the
       function cursor for the line.'''
    i = len(str) - 1
    depth = 0
    found_one = False
    while i >= 0:
        if str[i] == ')':
            found_one = True
            depth += 1
        elif str[i] == '(':
            found_one = True
            depth -= 1
        elif str[i] == '}':
            depth += 1
        elif str[i] == '{':
            depth -= 1
        if depth == 0 and found_one:
            return i - 1
        i -= 1
    return None

def get_function_cursor_on_line(tu, location, buffer):
    '''Return the function cursor on the line of location, using
       the location as a heuristic and resorting to using
       find_fn_name_from_line if location doesn't have a function cursor'''
    cursor = get_function_cursor_from_location(tu, location)
    if cursor is None:
        pos = find_fn_name_from_line(buffer[location.line-1])
        if pos:
            location = clang.cindex.SourceLocation.from_position(tu,\
                    location.file, location.line, pos)
            cursor = get_function_cursor_from_location(tu, location)

    return cursor

def build_unsaved_data(files):
    '''Return a list of unsaved file data for create_translation_unit
       from the list of files provided.'''
    unsaved_data = []

    for file in files:
        if file:
            buf = get_buffer_with_name(file)
            if buf is not None:
                unsaved_data.append((file, '\n'.join(buf)))

    return unsaved_data

def make_fn_definition(tu, cursor, files, force=False):
    '''Generate and write the function definition for a function cursor'''
    buffer = get_buffer_with_name(files.output)

    body_and_loc = generate_method_stub(tu, cursor, files, force)

    if body_and_loc is not None:
        if buffer is not vim.current.buffer:
            if buffer is None:
                vim.command('e {0}'.format(files.output))
                buffer = vim.current.buffer
            else:
                vim.command('b! {0}'.format(files.output))
        function_body, line = body_and_loc
        write_method(function_body, buffer, line, files.is_output_header)

def generate_over_range(index, files, start_line, end_line, force=False):
    '''Generate declarations for all functions on lines between start_line
       and end_line'''
    in_buf = get_buffer_with_name(files.input)
    unsaved_data = build_unsaved_data([files.header, files.source])
    tu = create_translation_unit(index, files.output, unsaved_data)
    for line in range(start_line, end_line+1):
        location = source_location_from_position(tu, files.input, line, 1)
        cursor = get_function_cursor_on_line(tu, location, in_buf)
        if cursor:
            make_fn_definition(tu, cursor, files, force)
            unsaved_data = build_unsaved_data([files.header, files.source])
            tu = create_translation_unit(index, files.output, unsaved_data)

def generate_at_location(tu, files, line, col, force=False):
    '''Generate a declaration for the provided line'''
    location = source_location_from_position(tu, files.input, line, col)
    cursor = get_function_cursor_on_line(tu, location, vim.current.buffer)

    if cursor is None:
        error('Unable to find a function at the location specified')
        return

    make_fn_definition(tu, cursor, files, force)

def make_fileset_for_source(source_file, force_inline):
    file_name = os.path.abspath(source_file)
    header_file = get_header_file(file_name)
    source_file = get_source_file(file_name)

    if source_file and not force_inline:
        parse_file = source_file
    else:
        parse_file = header_file

    files = FileSet(source_file, header_file, file_name, parse_file)
    return files


def generate_under_cursor(force_inline=False, force_generation=False):
    '''Entry point from vim. Get the position of the cursor
       and name of the current buffer and use those to generate
       the function definitions'''
    file_name = vim.eval("expand('%')")

    files = make_fileset_for_source(file_name, force_inline)

    unsaved_data = build_unsaved_data([files.header, files.source])

    index = clang.cindex.Index.create()
    tu = create_translation_unit(index, files.output, unsaved_data)

    _, line, col, _ = vim.eval("getpos('.')")
    line = int(line)
    col = int(col)
    generate_at_location(tu, files, line, col, force_generation)

def generate_range(start_line, end_line, force_inline=False, \
        force_generation=False):
    file_name = vim.eval("expand('%')")

    files = make_fileset_for_source(file_name, force_inline)

    index = clang.cindex.Index.create()

    generate_over_range(index, files, start_line, end_line, force_generation)
