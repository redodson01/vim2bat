" Supports both backgrounds. Uses palette numbers, color names (whose numbers
" depend on the terminal) and a 256-color value with a 16-color fallback.
hi clear
let g:colors_name = 'testdual'

if &background ==# 'dark'
  hi Normal ctermfg=14
  hi Comment ctermfg=DarkBlue cterm=italic
  hi CursorLine ctermbg=0 cterm=NONE
else
  hi Normal ctermfg=10
  hi Comment ctermfg=Blue cterm=italic
  hi CursorLine ctermbg=7 cterm=NONE
endif
if &t_Co >= 256
  hi Type ctermfg=208
else
  hi Type ctermfg=3
endif
hi Constant ctermfg=5
hi String ctermfg=6
hi Identifier ctermfg=4
hi Statement ctermfg=2 cterm=bold
hi PreProc ctermfg=9
hi Special ctermfg=1
hi Underlined ctermfg=13 cterm=underline
hi Error ctermfg=1 cterm=reverse
hi Todo ctermfg=5 cterm=bold
hi Bold cterm=bold
hi Italic cterm=italic
hi BoldItalic cterm=bold,italic
hi Added ctermfg=2
hi Changed ctermfg=3
hi Removed ctermfg=1
