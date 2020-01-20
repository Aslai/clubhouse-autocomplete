syn clear gitcommitSummary
syn match gitcommitSummary    "^.\{0,72\}" contained containedin=gitcommitFirstLine nextgroup=gitcommitOverflow contains=@Spell

syn match ticketNumber '\[ch\d*\]'
hi def link ticketNumber Constant  
