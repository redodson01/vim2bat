" Writes $OUTFILE: every highlight group with the foreground color, background
" color (palette slots, or #rrggbb under 'termguicolors') and attributes that
" the colorscheme $SCHEME gives it when 'background' is $BACKGROUND (dark or
" light), or no groups if $SCHEME lacks that background.

" vim2bat's -p and -t options, which override your vimrc.
if $T_CO !=# ''
  let &t_Co = $T_CO
endif
if $TERMGUICOLORS !=# ''
  set termguicolors
endif
let &background = $BACKGROUND
" The standard groups, and the links of the language groups, exist only with
" syntax highlighting on, which a vimrc can leave off.
if !exists('g:syntax_on')
  syntax enable
endif

" Vim on a terminal exits 0 after an error, so any error here makes it exit 1
" instead, but not one that silent! hides. That includes a scheme that fails to
" load, which would leave the colors of whatever scheme your vimrc loaded.
try
  execute 'colorscheme' $SCHEME

  let s:dir = expand('<sfile>:p:h')
  " Language groups exist only once their syntax file has run. They load after
  " the colorscheme because its :hi clear hides them from getcompletion().
  for s:ft in uniq(sort(map(readfile(s:dir . '/loose.tsv'), 'split(v:val, "\t")[0]')))
    let &syntax = s:ft
  endfor

  let s:attrs = ['bold', 'italic', 'underline', 'undercurl', 'strikethrough', 'reverse', 'standout']
  let s:rows = []
  for s:group in filter(getcompletion('', 'highlight'), 'hlexists(v:val)')
    let s:id = synIDtrans(hlID(s:group))
    let s:on = []
    for s:attr in s:attrs
      if synIDattr(s:id, s:attr, 'cterm') == '1'
        call add(s:on, s:attr)
      endif
    endfor
    " With 'termguicolors', Vim draws a group's GUI colors, or its cterm colors
    " if it has none, and always its cterm attributes.
    let s:colors = &termguicolors ? [synIDattr(s:id, 'fg#', 'gui'), synIDattr(s:id, 'bg#', 'gui')] : ['', '']
    if s:colors == ['', '']
      let s:colors = [synIDattr(s:id, 'fg', 'cterm'), synIDattr(s:id, 'bg', 'cterm')]
    endif
    call add(s:rows, join([s:group] + s:colors + [join(s:on, ',')], "\t"))
  endfor
  " A scheme with one background switches 'background' to it.
  call writefile(&background ==# $BACKGROUND ? s:rows : [], $OUTFILE)
catch
  " On Linux, /dev/stderr opens a redirected stderr's file anew, which Vim
  " would truncate without 'a'.
  call writefile([v:exception], '/dev/stderr', 'a')
  cquit
endtry
