" Loads despite an error that silent! hides, as plugins use it for optional
" steps.
hi clear
let g:colors_name = 'testsilent'
silent! call NoSuchFunction()
hi Normal ctermfg=7
