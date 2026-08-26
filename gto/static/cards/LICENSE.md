# Where these cards came from

52 card faces, `As.svg` through `2c.svg`.

Taken from **[hayeah/playing-cards-assets](https://github.com/hayeah/playing-cards-assets)**
(MIT, © 2018 Howard Yeh), which is itself a repackaging of
**[vector-playing-cards](https://code.google.com/p/vector-playing-cards/)**,
released into the **public domain**. So the artwork carries no restriction and
the packaging is MIT; the MIT notice is reproduced below because that is all it
asks for.

`back.svg` is not from that set. It is a pattern rather than a card face and was
written here.

## What was changed

The files were renamed to this codebase's own notation - rank letter then suit
letter, `Th.svg`, `As.svg` - so a card can be turned into a URL with no lookup
table. They were then shrunk by about 43%: XML comments and the Inkscape
`<metadata>` blocks removed, and coordinates rounded to one decimal place, which
at a 240-unit viewBox is far finer than a screen can show.

**The namespace declarations were deliberately left in.** An earlier pass
stripped them and orphaned the `sodipodi:` and `inkscape:` prefixes still in use
further down each file, which produces something smaller that does not render.
They are a few hundred bytes.

Every file is checked to still parse as XML after processing.

## MIT License

Copyright (c) 2018 Howard Yeh

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
