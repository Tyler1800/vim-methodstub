let s:plugin_path = escape(expand('<sfile>:p:h'), '\')

au FileType c,cpp call <SID>ClassTemplateInit()

function! s:ClassTemplateInit()
    python import sys
    execute 'python sys.path.append('' . s:plugin_path . '')'
    execute 'pyfile ' . fnameescape(s:plugin_path) . '/python/methodstub.py'
    command! -buffer -nargs=* GenFnStub python generate_under_cursor()
endfunction
