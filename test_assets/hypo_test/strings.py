import ast

from hypothesis.strategies import (
    SearchStrategy,
    booleans,
    composite,
    integers,
    one_of,
    recursive,
    sampled_from
)

from .expressions import Name, Str, Bytes

simple_strings = ['x', 'ab', 'test', 'hello']
simple_strings_with_empty = ['', 'x', 'ab', 'test', 'hello']  # For parts that can be empty


@composite
def format_spec_string(draw) -> str:
    """Generate valid format specification strings"""
    format_specs = [
        '',  # no format spec
        'd',  # integer
        'f',  # float
        '.2f',  # float with precision
        's',  # string
        'x',  # hex
        'o',  # octal
        'b',  # binary
        '010d',  # zero-padded integer
        '.3s',  # truncated string
        '>10',  # right-aligned
        '<10',  # left-aligned
        '^10',  # centered
    ]
    return draw(sampled_from(format_specs))


# region: f-string

@composite
def FormattedValue(draw, expression) -> ast.FormattedValue:
    """Generate FormattedValue nodes for f-strings"""
    value = draw(expression)

    # Conversion: -1 (no conversion), 115 ('s'), 114 ('r'), 97 ('a')
    conversion = draw(sampled_from([-1, 115, 114, 97]))

    format_spec_choice = draw(sampled_from(['none', 'empty_spec', 'string_spec', 'nested']))

    if format_spec_choice == 'none':
        format_spec = None
    elif format_spec_choice == 'empty_spec':
        # Empty format spec: f"{x:}"
        format_spec = ast.JoinedStr(values=[])
    elif format_spec_choice == 'string_spec':
        # Simple string format spec: f"{x:d}", f"{x:.2f}"
        spec_string = draw(format_spec_string())
        if spec_string:  # Only create if non-empty
            format_spec = ast.JoinedStr(values=[ast.Constant(value=spec_string)])
        else:
            format_spec = ast.JoinedStr(values=[])
    else:
        # Nested format spec - but constrain it to realistic patterns
        # Valid nested format specs have patterns like:
        # - f"{x:{width}}" -> format_spec=JoinedStr(values=[FormattedValue])
        # - f"{x:.{prec}f}" -> format_spec=JoinedStr(values=[Constant('.'), FormattedValue, Constant('f')])
        # - f"{x:>{width}}" -> format_spec=JoinedStr(values=[Constant('>'), FormattedValue])

        pattern_choice = draw(sampled_from(['simple_var', 'alignment_var', 'precision_var']))

        if pattern_choice == 'simple_var':
            # Just a variable: {width}
            format_spec = ast.JoinedStr(values=[
                ast.FormattedValue(
                    value=draw(one_of(string_leaves, simple_joined_str(expression), simple_template_str(expression))),
                    conversion=-1,
                    format_spec=None
                )
            ])
        elif pattern_choice == 'alignment_var':
            # Alignment + variable: >{width} or <{width} or ^{width}
            align_char = draw(sampled_from(['>', '<', '^']))
            format_spec = ast.JoinedStr(values=[
                ast.Constant(value=align_char),
                ast.FormattedValue(
                    value=draw(one_of(string_leaves, simple_joined_str(expression), simple_template_str(expression))),
                    conversion=-1,
                    format_spec=None
                )
            ])
        else:  # precision_var
            # Precision pattern: .{prec}f or .{prec}d
            type_char = draw(sampled_from(['f', 'd', 's', 'x']))
            format_spec = ast.JoinedStr(values=[
                ast.Constant(value='.'),
                ast.FormattedValue(
                    value=draw(one_of(string_leaves, simple_joined_str(expression), simple_template_str(expression))),
                    conversion=-1,
                    format_spec=None
                ),
                ast.Constant(value=type_char)
            ])

    return ast.FormattedValue(
        value=value,
        conversion=conversion,
        format_spec=format_spec
    )


@composite
def simple_joined_str(draw, expression) -> ast.JoinedStr:
    """Generate simple JoinedStr nodes to avoid infinite recursion"""

    pattern_type = draw(sampled_from([
        'constant_only',  # f"text"
        'formatted_only',  # f"{expr}" or f"{expr1}{expr2}"
        'simple_mixed'  # f"text{expr}" or f"{expr}text"
    ]))

    if pattern_type == 'constant_only':
        return ast.JoinedStr(values=[
            ast.Constant(value=draw(sampled_from(simple_strings)))
        ])

    elif pattern_type == 'formatted_only':
        num_formatted = draw(integers(min_value=1, max_value=2))
        values = []
        for _ in range(num_formatted):
            expr = draw(expression)
            values.append(ast.FormattedValue(
                value=expr,
                conversion=-1,
                format_spec=None
            ))
        return ast.JoinedStr(values=values)

    else:  # simple_mixed
        # Either "text{expr}" or "{expr}text"
        values = []
        if draw(booleans()):
            # "text{expr}"
            const_val = draw(sampled_from(simple_strings_with_empty))
            if const_val:  # Python omits empty string constants
                values.append(ast.Constant(value=const_val))
            values.append(ast.FormattedValue(
                value=draw(expression),
                conversion=-1,
                format_spec=None
            ))
        else:
            # "{expr}text"
            values.append(ast.FormattedValue(
                value=draw(expression),
                conversion=-1,
                format_spec=None
            ))
            const_val = draw(sampled_from(simple_strings_with_empty))
            if const_val:  # Python omits empty string constants
                values.append(ast.Constant(value=const_val))
        return ast.JoinedStr(values=values)


@composite
def JoinedStr(draw, expression) -> ast.JoinedStr:
    """
    Valid patterns:
    - f"" → JoinedStr(values=[])
    - f"text" → JoinedStr(values=[Constant])
    - f"{expr}" → JoinedStr(values=[FormattedValue])
    - f"text{expr}" → JoinedStr(values=[Constant, FormattedValue])
    - f"{expr}text" → JoinedStr(values=[FormattedValue, Constant])
    - f"a{expr}b{expr2}c" → JoinedStr(values=[Constant, FormattedValue, Constant, FormattedValue, Constant])
    """

    pattern_type = draw(sampled_from([
        'empty',  # f""
        'constant_only',  # f"text"
        'formatted_only',  # f"{expr}"
        'mixed'  # f"text{expr}..."
    ]))

    if pattern_type == 'empty':
        return ast.JoinedStr(values=[])

    elif pattern_type == 'constant_only':
        return ast.JoinedStr(values=[
            ast.Constant(value=draw(sampled_from(simple_strings)))
        ])

    elif pattern_type == 'formatted_only':
        num_formatted = draw(integers(min_value=1, max_value=3))
        values = []
        for _ in range(num_formatted):
            values.append(draw(FormattedValue(expression)))
        return ast.JoinedStr(values=values)

    else:  # mixed
        values = []

        starts_with_constant = draw(booleans())
        num_formatted = draw(integers(min_value=1, max_value=2))

        if starts_with_constant:
            const_val = draw(sampled_from(simple_strings_with_empty))
            if const_val:  # Python omits empty string constants
                values.append(ast.Constant(value=const_val))

        for i in range(num_formatted):
            values.append(draw(FormattedValue(expression)))
            # Optionally add a constant after each formatted value (except maybe the last)
            if i < num_formatted - 1 or draw(booleans()):
                const_val = draw(sampled_from(simple_strings_with_empty))
                if const_val:  # Python omits empty string constants
                    values.append(ast.Constant(value=const_val))

        return ast.JoinedStr(values=values)


# endregion


# region: t-string

@composite
def Interpolation(draw, expression) -> 'ast.Interpolation':
    """Generate Interpolation nodes for t-strings"""
    value = draw(expression)

    # Conversion: -1 (no conversion), 115 ('s'), 114 ('r'), 97 ('a')
    conversion = draw(sampled_from([-1, 115, 114, 97]))

    format_spec_choice = draw(sampled_from(['none', 'empty_spec', 'string_spec', 'nested']))

    if format_spec_choice == 'none':
        format_spec = None
    elif format_spec_choice == 'empty_spec':
        # Empty format spec: t"{x:}"
        format_spec = ast.JoinedStr(values=[])
    elif format_spec_choice == 'string_spec':
        # Simple string format spec: t"{x:d}", t"{x:.2f}"
        spec_string = draw(format_spec_string())
        if spec_string:  # Only create if non-empty
            format_spec = ast.JoinedStr(values=[ast.Constant(value=spec_string)])
        else:
            format_spec = ast.JoinedStr(values=[])
    else:
        # Nested format spec - but constrain it to realistic patterns
        # Valid nested format specs have patterns like:
        # - f"{x:{width}}" -> format_spec=JoinedStr(values=[FormattedValue])
        # - f"{x:.{prec}f}" -> format_spec=JoinedStr(values=[Constant('.'), FormattedValue, Constant('f')])
        # - f"{x:>{width}}" -> format_spec=JoinedStr(values=[Constant('>'), FormattedValue])

        # Generate a realistic format spec pattern
        # Use simple_joined_str/simple_template_str to avoid deep nesting
        pattern_choice = draw(sampled_from(['simple_var', 'alignment_var', 'precision_var']))

        if pattern_choice == 'simple_var':
            # Just a variable: {width}
            format_spec = ast.JoinedStr(values=[
                ast.FormattedValue(
                    value=draw(one_of(string_leaves, simple_joined_str(expression), simple_template_str(expression))),
                    conversion=-1,
                    format_spec=None
                )
            ])
        elif pattern_choice == 'alignment_var':
            # Alignment + variable: >{width} or <{width} or ^{width}
            align_char = draw(sampled_from(['>', '<', '^']))
            format_spec = ast.JoinedStr(values=[
                ast.Constant(value=align_char),
                ast.FormattedValue(
                    value=draw(one_of(string_leaves, simple_joined_str(expression), simple_template_str(expression))),
                    conversion=-1,
                    format_spec=None
                )
            ])
        else:  # precision_var
            # Precision pattern: .{prec}f or .{prec}d
            type_char = draw(sampled_from(['f', 'd', 's', 'x']))
            format_spec = ast.JoinedStr(values=[
                ast.Constant(value='.'),
                ast.FormattedValue(
                    value=draw(one_of(string_leaves, simple_joined_str(expression), simple_template_str(expression))),
                    conversion=-1,
                    format_spec=None
                ),
                ast.Constant(value=type_char)
            ])

    return ast.Interpolation(
        value=value,
        str='',  # Empty string is sufficient for our testing purposes
        conversion=conversion,
        format_spec=format_spec
    )


@composite
def simple_template_str(draw, expression) -> 'ast.TemplateStr':
    """Generate simple TemplateStr nodes to avoid infinite recursion"""

    # Simple patterns that avoid consecutive constants
    pattern_type = draw(sampled_from([
        'constant_only',  # t"text"
        'interpolation_only',  # t"{expr}" or t"{expr1}{expr2}"
        'simple_mixed'  # t"text{expr}" or t"{expr}text"
    ]))

    if pattern_type == 'constant_only':
        return ast.TemplateStr(values=[
            ast.Constant(value=draw(sampled_from(simple_strings)))
        ])

    elif pattern_type == 'interpolation_only':
        # 1 or 2 interpolations, no constants
        num_interpolations = draw(integers(min_value=1, max_value=2))
        values = []
        for _ in range(num_interpolations):
            expr = draw(expression)
            values.append(ast.Interpolation(
                value=expr,
                str='',
                conversion=-1,
                format_spec=None
            ))
        return ast.TemplateStr(values=values)

    else:  # simple_mixed
        # Either "text{expr}" or "{expr}text"
        values = []
        if draw(booleans()):
            # "text{expr}"
            const_val = draw(sampled_from(simple_strings_with_empty))
            if const_val:  # Python omits empty string constants
                values.append(ast.Constant(value=const_val))
            values.append(ast.Interpolation(
                value=draw(expression),
                str='',
                conversion=-1,
                format_spec=None
            ))
        else:
            # "{expr}text"
            values.append(ast.Interpolation(
                value=draw(expression),
                str='',
                conversion=-1,
                format_spec=None
            ))
            const_val = draw(sampled_from(simple_strings_with_empty))
            if const_val:  # Python omits empty string constants
                values.append(ast.Constant(value=const_val))
        return ast.TemplateStr(values=values)


@composite
def TemplateStr(draw, expression) -> 'ast.TemplateStr':
    """Generate TemplateStr nodes (t-strings) that mirror Python parser output

    Valid patterns follow same rules as f-strings but with Interpolation instead of FormattedValue:
    - t"" → TemplateStr(values=[])
    - t"text" → TemplateStr(values=[Constant])
    - t"{expr}" → TemplateStr(values=[Interpolation])
    - t"text{expr}" → TemplateStr(values=[Constant, Interpolation])
    - t"{expr}text" → TemplateStr(values=[Interpolation, Constant])

    Key insight: Never consecutive Constants (Python parser merges them)
    """
    # Choose pattern type (same as JoinedStr)
    pattern_type = draw(sampled_from([
        'empty',  # t""
        'constant_only',  # t"text"
        'interpolation_only',  # t"{expr}"
        'mixed'  # t"text{expr}..."
    ]))

    if pattern_type == 'empty':
        return ast.TemplateStr(values=[])

    elif pattern_type == 'constant_only':
        # Just a single string constant
        return ast.TemplateStr(values=[
            ast.Constant(value=draw(sampled_from(simple_strings)))
        ])

    elif pattern_type == 'interpolation_only':
        # One or more interpolations, no constants
        num_interpolations = draw(integers(min_value=1, max_value=3))
        values = []
        for _ in range(num_interpolations):
            values.append(draw(Interpolation(expression)))
        return ast.TemplateStr(values=values)

    else:  # mixed
        # Generate realistic mixed pattern: alternating constants and interpolations
        # Never adjacent constants
        values = []

        # Start with constant or interpolation
        starts_with_constant = draw(booleans())

        # Number of interpolations (at least 1)
        num_interpolations = draw(integers(min_value=1, max_value=2))

        if starts_with_constant:
            const_val = draw(sampled_from(simple_strings_with_empty))
            if const_val:  # Python omits empty string constants
                values.append(ast.Constant(value=const_val))

        # Add alternating interpolations and constants
        for i in range(num_interpolations):
            values.append(draw(Interpolation(expression)))
            # Optionally add a constant after each interpolation (except maybe the last)
            if i < num_interpolations - 1 or draw(booleans()):
                const_val = draw(sampled_from(simple_strings_with_empty))
                if const_val:  # Python omits empty string constants
                    values.append(ast.Constant(value=const_val))

        return ast.TemplateStr(values=values)


# endregion


@composite
def mixed_string_expression(draw, expression) -> ast.AST:
    """Generate expressions that can include f-strings, t-strings, regular strings, and bytes"""
    return draw(one_of(Str(), Bytes(), JoinedStr(expression), TemplateStr(expression)))


string_leaves = one_of(
    sampled_from([
        ast.Constant(value=''),
        ast.Constant(value='hello'),
        ast.Constant(value=42),
        ast.Constant(value=3.14),
        ast.Constant(value=True),
        ast.Constant(value=None),
    ]),
    Str(),
    Bytes(),
    Name(),
)


def string_expression() -> SearchStrategy:
    """Expression strategy focused on string operations and literals"""
    return recursive(
        string_leaves,
        lambda expression: one_of(
            mixed_string_expression(expression),
            JoinedStr(expression),
            TemplateStr(expression),
        ),
        max_leaves=30
    )


@composite
def StringExpression(draw) -> ast.Expression:
    """An eval expression focused on string formatting"""
    e = draw(string_expression())
    return ast.Expression(e)
