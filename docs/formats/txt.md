# Supplementary bank TXT

Project format from `docs/contracts.md`, §4. A UTF-8 `.txt` file accompanies
each statement in the same directory with the same base name. It contains
one line per transaction in statement order, in the form `<line_no>|<free text>`.
The fixture uses LF. Split on the first pipe to preserve the text after it.

Line numbers start at one and count GPC `075` or STA `:61:` records. The text
for an invoice payment includes the synthetic supplier name and invoice number.
Other transactions may carry a short description. A statement with no
transactions has an empty companion file.

Example: `1|Solar Novak s.r.o. invoice 202600014`.
