"""Every unsupported construct must fail with a clear, located,
actionable message. This is the M5 error-triage guarantee.
"""

import pytest

from expressnode import CompileError, compile

# (source, substring the message must contain)
CASES = [
    ("import math\ndef f(): return 1.0", "Imports aren't allowed"),
    ("from math import sin\ndef f(): return 1.0", "Imports aren't allowed"),
    ("class C: pass", "isn't compileable"),
    ("async def f(): return 1.0", "isn't compileable"),
    ("def f():\n for i in range(3): pass\n return 1.0",
     "for loops aren't supported"),
    ("def f():\n while True: break\n return 1.0",
     "while loops aren't supported"),
    ("def f():\n try:\n  return 1.0\n except: return 0.0",
     "Exception handling"),
    ("def f(x):\n if x>0: return 1.0\n return 0.0",
     "`if` statements aren't supported"),
    ("def f():\n a=1.0\n a+=1.0\n return a", "Augmented assignment"),
    ("def f(): return min(*[1.0,2.0])", "unpacking"),
    ("def f(): return mix(0.0,1.0,t=0.5)", "Keyword arguments"),
    ("def f(P): return P.normalize()", "simple name"),
    ("def f():\n a,b=1.0,2.0\n return a+b", "simple name"),
    ("def f(): return nope", "Unknown name"),
    ("def f(): return frobnicate(1.0)", "Unknown function"),
    ("def f(x): return 0.0 < x < 1.0", "Chained comparisons"),
    ("def f(): return sin(vec3(0.0,0.0,0.0))", "No matching signature"),
    ("def f(): return attr('x','matrix')", "Unknown attribute dtype"),
    ("def f(): return obj('Cube','mass')", "Unknown object field"),
    ("def f():\n n='a'\n return attr(n)", "string literal"),
    ("", "No entry function"),
    ("def f(:\n return 1\n", "Syntax error"),
]


@pytest.mark.parametrize("source,needle", CASES)
def test_clear_message(source, needle):
    with pytest.raises(CompileError) as exc:
        compile(source)
    assert needle in exc.value.message, (
        f"message {exc.value.message!r} lacks {needle!r}"
    )


@pytest.mark.parametrize("source,_n", CASES)
def test_error_is_located(source, _n):
    """Every error carries a source span (line/col) except the two whole
    -program cases (empty source / no entry) which legitimately have none."""
    with pytest.raises(CompileError) as exc:
        compile(source)
    e = exc.value
    if e.message.startswith("No entry function"):
        return
    assert e.span is not None, f"{source!r} -> error without a span"
    assert e.span.line >= 1


def test_str_includes_location_and_caret():
    with pytest.raises(CompileError) as exc:
        compile("def f():\n    return unknown_name\n")
    text = str(exc.value)
    assert "line 2" in text
    assert "^" in text  # the caret underline is rendered


def test_unknown_name_hints_builtins():
    with pytest.raises(CompileError) as exc:
        compile("def f(): return P_x")
    assert exc.value.hint and "Built-in variables" in exc.value.hint
