" Supports only a dark background, and defines 24-bit colors with cterm
" fallbacks, except for Statement, which has only a cterm color.
set background=dark
hi clear
let g:colors_name = 'testhex'

hi Normal guifg=#d0d0d0 guibg=#1c1c1c ctermfg=252 ctermbg=234
hi CursorLine guibg=#303030 ctermbg=236 gui=NONE cterm=NONE
hi Comment guifg=#808080 ctermfg=244 gui=italic cterm=italic
hi Constant guifg=#d75f87 ctermfg=168
hi String guifg=#5faf5f ctermfg=71
hi Identifier guifg=#87afd7 ctermfg=110
hi Statement guifg=NONE guibg=NONE ctermfg=1 cterm=bold
hi PreProc guifg=#d7875f ctermfg=173
hi Type guifg=#5f87af ctermfg=67
hi Special guifg=#d7af87 ctermfg=180
hi Underlined guifg=#87afff ctermfg=111 gui=underline cterm=underline
hi Error guifg=#ff5f5f ctermfg=203
hi Todo guifg=#ffff87 ctermfg=228 gui=bold cterm=bold
hi Bold gui=bold cterm=bold
hi Italic gui=italic cterm=italic
hi BoldItalic gui=bold,italic cterm=bold,italic
hi Added guifg=#5faf5f ctermfg=71
hi Changed guifg=#d7af87 ctermfg=180
hi Removed guifg=#ff5f5f ctermfg=203
