let s:plugin_path = escape(expand('<sfile>:p:h'), '\')

au FileType c,cpp call <SID>ClassTemplateInit()

function! s:ClassTemplateInit()
    if !exists('s:methodstub_plugin_loaded')
        python import sys
        execute 'python sys.path.append("' . s:plugin_path . '")'
        execute 'python from methodstub import methodstub'
        execute 'python from methodstub import accessor'
        command! -buffer -nargs=* GenFnStub python methodstub.generate_under_cursor(<f-args>)
        command! -buffer -range -nargs=* GenFnStubRange <line1>,<line2>call <SID>GenFnStubRange(<f-args>)
        command! -buffer -nargs=* GenFieldAccessors python accessor.generate_under_cursor(<f-args>)
        let s:methodstub_plugin_loaded = 1
    endif
endfunction

function! s:GenFnStubRange(inline) range abort
    execute 'python methodstub.generate_range(' . a:firstline . ', ' . a:lastline . ', ' . a:inline . ')'
endfunction
