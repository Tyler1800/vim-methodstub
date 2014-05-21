let s:plugin_path = escape(expand('<sfile>:p:h'), '\')

au FileType c,cpp call <SID>ClassTemplateInit()

function! s:ClassTemplateInit()
    python import sys
    execute 'python sys.path.append('' . s:plugin_path . '')'
    execute 'pyfile ' . fnameescape(s:plugin_path) . '/python/methodstub.py'
    command! -buffer -nargs=* GenFnStub python generate_under_cursor(<f-args>)
    command! -buffer -range -nargs=1 GenFnStubRange <line1>,<line2>call <SID>GenFnStubRange(<f-args>)
endfunction

function! s:GenFnStubRange(inline) range abort
    execute 'python generate_range(' . a:firstline . ', ' . a:lastline . ', ' . a:inline . ')'
endfunction
