# py-terser

Transforms Python projects into its most compact representation.
Fork of [dflook/python-minifier](https://github.com/dflook/python-minifier).

> [!WARNING]
> This project was written in Antigravity CLI. I'm reviewing the code, but use it with caution.

`py-terser` currently supports Python 3.10 to 3.14.

> [!NOTE]
> This is for initial work after forking. Will be moved to [AlphaKR93/packages](https://github.com/AlphaKR93/packages) in the future.

As an example, the following python source:

```python
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import FastAPI
# ...
from terser.hints import preserve_docstring


app = FastAPI()

@preserve_docstring
@app.get("/{path:path}", response_class=StreamingResponse)
async def stream_parsed(
    path: Annotated[str, Path()],
    range_: Annotated[tuple[bool, int | str | None, int | str | None], Depends(...)],
) -> AsyncGenerator[str]:
    """
    Returns parsed Markdown file via streaming response.
    """

    is_single_id, start, end = range_
    markdown = await runtime_dir.resolve(path)
    if not await markdown.is_file():
        raise HTTPException(400)

    composer = Composer()
    frontmatter = FrontmatterProcessor()
    async with await markdown.open('r') as file:
        class StatusFlag(IntFlag):
            INSIDE = auto()
            COMPLETE = auto()
            STRIP_LEADING = auto()

        line = 0
        flag = StatusFlag(0)
        async for content in file:
            if not frontmatter.is_complete:
                if frontmatter.process(content):
                    continue
                raise RuntimeError("Frontmatter was not processed correctly")
            elif line == 0 and frontmatter.has_content:
                if content == "\n":
                    line += 1
                    continue
                raise OSError("File corrupted")

            composed: str = composer.compose(line, content)
            line += 1
            if isinstance(start, int):
                assert isinstance(end, int)
                if start >= line:
                    continue
                elif flag & StatusFlag.INSIDE and line > end:
                    yield composed
                    yield composer.collect()
                    break
                elif not flag & StatusFlag.INSIDE:
                    flag |= StatusFlag.INSIDE
                    continue
            elif isinstance(start, str):
                node = composer.current or composer.parent
                if not isinstance(node, Element):
                    if flag & StatusFlag.COMPLETE:
                        break
                    continue

                assert isinstance(start, int)
                boundary = end if flag & StatusFlag.COMPLETE else start if is_single_id else None
                if not flag & StatusFlag.INSIDE and node._id == start:
                    flag |= StatusFlag.INSIDE | StatusFlag.STRIP_LEADING
                    continue
                elif flag & StatusFlag.INSIDE and not flag & StatusFlag.COMPLETE and node._id == end:
                    flag |= StatusFlag.COMPLETE
                elif flag & StatusFlag.INSIDE and boundary and node._id != boundary and not node._id.startswith(boundary + "."):
                    yield composed
                    for _line in composer.collect().splitlines(keepends=True):
                        if _line.startswith('\t</'):
                            yield _line
                        elif _line and _line[0].isdigit() and _line[-2:] == '\t\n':
                            continue
                        else:
                            break
                    break

                if not flag & StatusFlag.INSIDE:
                    continue

            if line <= 1 and not composed:
                continue

            if flag & StatusFlag.STRIP_LEADING:
                first_tab = composed.find('\t')
                if first_tab > 0 and composed[first_tab:first_tab + 2] == '\t\n':
                    composed = composed[composed.index('\n') + 1:]
                flag &= ~StatusFlag.STRIP_LEADING

            yield composed
        else:
            composer.close()

        yield composer.collect()
```

Becomes:

```py
from collections.abc import AsyncGenerator as D
from typing import Annotated as E
from fastapi import FastAPI as F
# ...
app=F=F()
@F.get('/{path:path}',response_class=J)
async def stream_parsed(path:E[A,I()],range_:E[tuple[bool,P,P],H(...)])->D[A]:
	'''Returns parsed Markdown file via streaming response.'''
	D,E,F=range_;H=await K.resolve(path)
	if not await H.is_file():raise G(400)
	I=L();J=M()
	async with await H.open('r')as K:
		L=M=0
		async for K in K:
			if not M.is_complete:
				if M.process(K):continue
				raise RuntimeError('Frontmatter was not processed correctly')
			if L==0and M.has_content:
				if K=='\n':
					L+=1;continue
				raise OSError('File corrupted')
			K=I.compose(L,K);L+=1
			if O(E,B):
				if E>=L:continue
				if M&1and L>F:
					yield K;yield I.collect();break
				elif not M&1:
					M|=1;continue
			elif O(E,A):
				G=I.current or I.parent
				if not O(G,N):
					if M&2:break
					continue
				H=F if M&2else E if D else C
				if not M&1and G._id==E:
					M|=5;continue
				if M&1and not M&2and G._id==F:M|=2
				elif M&1and H and G._id!=H and not G._id.startswith(H+'.'):
					yield K
					for G in I.collect().splitlines(keepends=True):
						if G.startswith('\t</'):yield G
						elif G and G[0].isdigit() and G[-2:]=='\t\n':continue
						else:break
					break
				if not M&1:continue
			if L<=1and not K:continue
			if M&4:
				G=K.find('\t')
				if G and K[G:G+2]=='\t\n':K=K[K.index('\n')+1:]
			yield K
		else:I.close()
		yield I.collect()
```

## License

Available under the MIT License. Full text is in the [LICENSE.md](LICENSE.md) file.
