Optional. The dashboard downloads ICE's yearly history files itself
(https://www.ice.com/publicdocs/futures/COTHist2026.csv, one per year, from ICE report 122).

Files put here (for example `COTHist2026.csv`, exactly as ICE publishes them) are used first,
which helps if ice.com can't be reached. It reads Brent, Gasoil and Dubai 1st Line, futures
only and futures + options, and ignores any other market. If two files hold the same week,
the one whose name sorts last wins.
