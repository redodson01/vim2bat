" Writes $OUTFILE: for each non-blank character of $TARGET, its line, its
" character index, the color (palette slot, or #rrggbb under 'termguicolors')
" the colorscheme $SCHEME shows it in after 'background' is set to $BACKGROUND,
" and the chain of links from its syntax item to the group that colors it. The
" first line is the filetype.

" See vim-groups.vim.
if $T_CO !=# ''
  let &t_Co = $T_CO
endif
if $TERMGUICOLORS !=# ''
  set termguicolors
endif
let &background = $BACKGROUND
if !exists('g:syntax_on')
  syntax enable
endif
try | execute 'colorscheme' $SCHEME | catch | call writefile([v:exception], '/dev/stderr', 'a') | cquit | endtry

let s:chains = {}
function s:Chain(name) abort
  if !has_key(s:chains, a:name)
    let l:chain = [a:name]
    while 1
      let l:next = matchstr(execute('highlight ' . l:chain[-1]), 'links to \zs\S\+')
      if l:next ==# '' || index(l:chain, l:next, 0, v:true) >= 0
        break
      endif
      call add(l:chain, l:next)
    endwhile
    let s:chains[a:name] = join(l:chain, '>')
  endif
  return s:chains[a:name]
endfunction

" As in vim-groups.vim.
let s:fgs = {}
function s:Fg(id) abort
  if !has_key(s:fgs, a:id)
    let l:colors = &termguicolors ? [synIDattr(a:id, 'fg#', 'gui'), synIDattr(a:id, 'bg#', 'gui')] : ['', '']
    let s:fgs[a:id] = l:colors == ['', ''] ? synIDattr(a:id, 'fg', 'cterm') : l:colors[0]
  endif
  return s:fgs[a:id]
endfunction

let s:rows = []
" As in vim-groups.vim, but $OUTFILE is still written after an error, so that
" vim2bat compare compares what there is and reports the error.
try
  execute 'edit' fnameescape($TARGET)
  " Highlight each line as Vim would after scrolling down from the top.
  syntax sync fromstart
  call add(s:rows, '#ft=' . &filetype)
  let s:normal = s:Fg(synIDtrans(hlID('Normal')))
  for s:lnum in range(1, line('$'))
    let s:col = 1
    let s:idx = 0
    for s:char in split(getline(s:lnum), '\zs')
      " synID() misses a match that starts on a blank unless it visits that
      " column too.
      let s:id = synID(s:lnum, s:col, 1)
      if s:char !~# '\s'
        let s:fg = s:Fg(synIDtrans(s:id))
        let s:name = synIDattr(s:id, 'name')
        call add(s:rows, join([s:lnum, s:idx, s:fg ==# '' ? s:normal : s:fg, s:name ==# '' ? '' : s:Chain(s:name)], "\t"))
      endif
      let s:col += len(s:char)
      " split() keeps composing characters with their base character. Count
      " each one, as vim2bat compare does.
      let s:idx += strchars(s:char)
    endfor
  endfor
catch
  call writefile([v:exception], '/dev/stderr', 'a')
  let s:failed = 1
endtry
call writefile(s:rows, $OUTFILE)
if exists('s:failed')
  cquit
endif
